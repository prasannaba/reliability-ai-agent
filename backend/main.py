"""HTTP chat host and LLM orchestration client for the reliability MCP server."""

import os
import re
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from llama_index.core import Settings
from llama_index.core.agent.workflow import ReActAgent
from llama_index.core.tools import FunctionTool
from llama_index.core.workflow import Context
from llama_index.llms.openai_like import OpenAILike
from pydantic import BaseModel, Field

from .mcp_client import ReliabilityMCPClient

STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)


def infer_latest_image_url(
    response_content: str,
    static_dir: Path | None = None,
    base_url: str | None = None,
) -> str | None:
    """Return an image URL only when the response names an existing plot."""
    if not response_content:
        return None

    static_dir = static_dir or STATIC_DIR
    base_url = base_url or os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")
    if not static_dir.exists():
        return None

    for filename in re.findall(r"([A-Za-z0-9_.-]+\.png)", response_content):
        candidate = static_dir / filename
        if candidate.is_file():
            return f"{base_url.rstrip('/')}/static/{candidate.name}"
    return None


def extract_response_text(response_object: object) -> str:
    """Extract natural-language text from common LlamaIndex response shapes."""
    if response_object is None:
        return ""
    if isinstance(response_object, str):
        return response_object.strip()

    for attribute in ("content", "response", "output", "result"):
        value = getattr(response_object, attribute, None)
        if isinstance(value, str) and value:
            return value.strip()
        content = getattr(value, "content", None)
        if isinstance(content, str) and content:
            return content.strip()
        if value is not None:
            return str(value).strip()
    return str(response_object).strip()


def normalize_response_content(response_content: str) -> str:
    """Add context when an agent returns only a generated plot filename."""
    text = str(response_content or "").strip()
    if re.fullmatch(r"[A-Za-z0-9_.-]+\.png", text):
        return f"I created the Weibull plot for the supplied failure data: {text}"
    return text


class ChatRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=20_000)


class ChatResponse(BaseModel):
    content: str
    image_url: str | None = None


def build_agent(mcp_client: ReliabilityMCPClient) -> ReActAgent:
    Settings.llm = OpenAILike(
        model=os.getenv("LLM_MODEL", "gemma"),
        api_base=os.getenv("LLM_API_BASE", "http://localhost:8080/v1"),
        api_key=os.getenv("LLM_API_KEY", "dummy"),
        is_chat_model=True,
        is_function_calling_model=True,
    )
    tools = [
        FunctionTool.from_defaults(async_fn=mcp_client.search_reliability_knowledge),
        FunctionTool.from_defaults(async_fn=mcp_client.analyze_weibull),
        FunctionTool.from_defaults(async_fn=mcp_client.calculate_b_life),
    ]
    return ReActAgent(
        tools=tools,
        system_prompt=(
            "You are an expert in reliability engineering and mathematics. Use the MCP-backed "
            "tools for knowledge-base questions, Weibull analysis, and B-life calculations. "
            "When a plot is created, mention its filename and summarize beta, eta, goodness of "
            "fit, and practical meaning. For warranty questions, compare B10, B20, and B30. "
            "Use LaTeX for mathematics and answer directly with technically rigorous Markdown."
        ),
    )


def create_app() -> FastAPI:
    mcp_client = ReliabilityMCPClient()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await mcp_client.start()
        app.state.agent = build_agent(mcp_client)
        app.state.agent_context = Context(app.state.agent)
        yield
        await mcp_client.close()

    app = FastAPI(title="Reliability Agent", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[os.getenv("FRONTEND_ORIGIN", "http://localhost:4200")],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "mcp": "connected"}

    @app.post("/api/chat", response_model=ChatResponse)
    async def chat_endpoint(request: ChatRequest) -> ChatResponse:
        try:
            response_object = await app.state.agent.run(user_msg=request.prompt, ctx=app.state.agent_context)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Agent inference failed: {exc}") from exc

        content = normalize_response_content(extract_response_text(response_object))
        return ChatResponse(content=content, image_url=infer_latest_image_url(content))

    return app


app = create_app()


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
