"""HTTP chat host and LLM orchestration client for the reliability MCP server."""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
import urllib.error
import urllib.request
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from llama_index.core import Settings
from llama_index.core.agent.workflow import ReActAgent
from llama_index.core.workflow import Context
from llama_index.llms.openai_like import OpenAILike
from pydantic import BaseModel, Field

try:
    from .mcp_client import ReliabilityMCPClient
except ImportError:  # Support the documented `python main.py` launch from backend/.
    from mcp_client import ReliabilityMCPClient

try:
    from .markdown_math import patch_markdown_math
except ImportError:
    from markdown_math import patch_markdown_math

try:
    from .knowledge_base import KNOWLEDGE_BASE_DIR, SUPPORTED_SUFFIXES, ReliabilityKnowledgeBase
except ImportError:
    from knowledge_base import KNOWLEDGE_BASE_DIR, SUPPORTED_SUFFIXES, ReliabilityKnowledgeBase

STATIC_DIR = Path(__file__).parent / "static"
UI_DIR = STATIC_DIR / "ui"
STATIC_DIR.mkdir(exist_ok=True)
load_dotenv(Path(__file__).resolve().parent.parent / ".env")


_PNG_NAME = re.compile(r"([A-Za-z0-9_.-]+\.png)")
_MODELS_TTL_SECONDS = 20.0
_models_cache: tuple[float, str, list[str]] | None = None


def infer_latest_image_url(
    response_content: str,
    static_dir: Path | None = None,
    base_url: str | None = None,
) -> str | None:
    """Return an image URL only when the response names an existing plot."""
    if not response_content or ".png" not in response_content:
        return None

    static_dir = static_dir or STATIC_DIR
    if base_url is None:
        base_url = os.getenv("PUBLIC_BASE_URL", "")
    if not static_dir.exists():
        return None

    for filename in _PNG_NAME.findall(response_content):
        candidate = static_dir / filename
        if candidate.is_file():
            prefix = base_url.rstrip("/")
            return f"{prefix}/static/{candidate.name}" if prefix else f"/static/{candidate.name}"
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
    return patch_markdown_math(text)


SYSTEM_PROMPT = (
    "You are a Reliability Copilot: a local assistant for reliability engineering. "
    "Never invent numeric lives (MTBF, B10/B20/B30, β, η). Always call MCP tools "
    "(analyze_weibull, calculate_b_life, calculate_mtbf, export_reliability_report) "
    "for those quantities. If a tool cannot be run, say you cannot give a number. "
    "Use search_reliability_knowledge for procedures and handbook questions. "
    "When a plot is created, mention its filename and summarize β, η, sample "
    "(failures vs suspensions), method (RRY or MLE), bounds if present, and meaning. "
    "For warranty questions, compare B10/B20/B30 to the warranty period using tool output. "
    "This product complements commercial solvers such as ReliaSoft Weibull++; do not claim to replace them. "
    "Use LaTeX for mathematics and answer in technically rigorous Markdown."
)


class ChatRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=20_000)
    model: str | None = Field(default=None, max_length=512)
    thinking: bool = True


class ChatResponse(BaseModel):
    content: str
    image_url: str | None = None


_FINAL_ANSWER = re.compile(r"(?:^|\n)\s*Final Answer\s*:\s*", re.IGNORECASE)
_THOUGHT_HEAD = re.compile(r"\A\s*Thought\s*:", re.IGNORECASE)
_THINK_TAG = re.compile(r"<think>(.*?)</think>", re.IGNORECASE | re.DOTALL)
_THINK_OPEN = re.compile(r"<think>", re.IGNORECASE)
_THINK_CLOSE = re.compile(r"</think>", re.IGNORECASE)


def split_thinking_from_answer(text: str) -> tuple[str, str]:
    """Move ReAct / <think> traces out of the visible reply.

    Only a leading ``Thought:`` (or ``<think>`` tags) counts as reasoning.
    Reliability markdown often contains ``Observation:`` or ``Action:`` and
    must stay in the answer.
    """
    raw = str(text or "")
    tagged = [chunk.strip() for chunk in _THINK_TAG.findall(raw) if chunk.strip()]
    rest = _THINK_TAG.sub("", raw)
    match = _FINAL_ANSWER.search(rest)
    prefix = rest[: match.start()] if match else ""
    if match and _THOUGHT_HEAD.search(prefix):
        return _join_thoughts(*tagged, prefix.strip()), rest[match.end() :].strip()
    if _THOUGHT_HEAD.search(rest):
        return _join_thoughts(*tagged, rest.strip()), ""
    return _join_thoughts(*tagged), rest.strip()


def _join_thoughts(*parts: str) -> str:
    return "\n\n".join(part.strip() for part in parts if part and part.strip())


class StreamThoughtSplitter:
    """Classify streamed tokens as thinking vs answer without waiting for the full reply."""

    def __init__(self) -> None:
        self.mode = "unknown"
        self.buffer = ""
        self._in_think_tag = False

    def feed(self, delta: str) -> list[tuple[str, str]]:
        if not delta:
            return []
        if self.mode == "answer" and not self._in_think_tag:
            return [("token", delta)]

        self.buffer += delta
        events: list[tuple[str, str]] = []

        while self.buffer:
            if self._in_think_tag:
                close = _THINK_CLOSE.search(self.buffer)
                if not close:
                    events.append(("thought", self.buffer))
                    self.buffer = ""
                    break
                events.append(("thought", self.buffer[: close.start()]))
                self.buffer = self.buffer[close.end() :]
                self._in_think_tag = False
                continue

            open_tag = _THINK_OPEN.search(self.buffer)
            if open_tag:
                if open_tag.start() > 0:
                    prefix = self.buffer[: open_tag.start()]
                    events.extend(self._classify_prefix(prefix))
                self.buffer = self.buffer[open_tag.end() :]
                self._in_think_tag = True
                continue

            final = _FINAL_ANSWER.search(self.buffer)
            if final:
                thought = self.buffer[: final.start()]
                answer = self.buffer[final.end() :]
                if thought.strip():
                    events.append(("thought", thought))
                self.buffer = ""
                self.mode = "answer"
                if answer:
                    events.append(("token", answer))
                break

            if self.mode == "thought":
                events.append(("thought", self.buffer))
                self.buffer = ""
                break

            if self.mode == "unknown":
                if _THOUGHT_HEAD.search(self.buffer):
                    self.mode = "thought"
                    events.append(("thought", self.buffer))
                    self.buffer = ""
                    break
                if "\n" in self.buffer or len(self.buffer) >= 80:
                    self.mode = "answer"
                    events.append(("token", self.buffer))
                    self.buffer = ""
                    break
                break
            break
        return [(kind, text) for kind, text in events if text]

    def flush(self) -> list[tuple[str, str]]:
        leftover = self.buffer
        self.buffer = ""
        if not leftover:
            return []
        if self.mode == "thought" or self._in_think_tag:
            return [("thought", leftover)]
        thought, answer = split_thinking_from_answer(leftover)
        out: list[tuple[str, str]] = []
        if thought:
            out.append(("thought", thought))
        if answer:
            out.append(("token", answer))
        elif leftover and not thought:
            out.append(("token", leftover))
        return out

    def _classify_prefix(self, prefix: str) -> list[tuple[str, str]]:
        if not prefix:
            return []
        if self.mode == "thought" or _THOUGHT_HEAD.search(prefix):
            self.mode = "thought"
            return [("thought", prefix)]
        self.mode = "answer"
        return [("token", prefix)]


LLM_UNCONFIGURED = (
    "LLM endpoint is not configured. Set LLM_API_BASE in the repo-root .env file "
    "(copy from .env.example), for example LLM_API_BASE=http://127.0.0.1:8080/v1"
)


def llm_api_base() -> str | None:
    value = (os.getenv("LLM_API_BASE") or "").strip().rstrip("/")
    return value or None


def preferred_llm_model() -> str | None:
    value = (os.getenv("LLM_MODEL") or "").strip()
    return value or None


def pick_listed_model(models: list[str], preferred: str | None = None) -> str | None:
    if preferred and preferred in models:
        return preferred
    return models[0] if models else None


def parse_openai_model_ids(payload: object) -> list[str]:
    if not isinstance(payload, dict):
        return []
    ids: list[str] = []
    data = payload.get("data")
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and item.get("id"):
                ids.append(str(item["id"]))
            elif isinstance(item, str) and item.strip():
                ids.append(item.strip())
    if ids:
        return ids
    extra = payload.get("models")
    if isinstance(extra, list):
        return [str(item) for item in extra if isinstance(item, str) and item.strip()]
    return []


def fetch_llm_models(timeout_seconds: float = 3.0) -> list[str]:
    """List models from the OpenAI-compatible server in LLM_API_BASE."""
    base = llm_api_base()
    if not base:
        raise RuntimeError(LLM_UNCONFIGURED)
    url = f"{base}/models"
    request = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {os.getenv('LLM_API_KEY', 'dummy')}"},
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return parse_openai_model_ids(payload)


async def fetch_llm_models_cached() -> list[str]:
    """Reuse /v1/models for a few seconds so status + chat do not block twice."""
    global _models_cache
    base = llm_api_base() or ""
    now = time.monotonic()
    if _models_cache and _models_cache[1] == base and now - _models_cache[0] < _MODELS_TTL_SECONDS:
        return _models_cache[2]
    models = await asyncio.to_thread(fetch_llm_models)
    _models_cache = (now, base, models)
    return models


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, default=str)}\n\n"


def _event_tool_name(event: object) -> str | None:
    for attribute in ("tool_name", "tool_id", "name"):
        value = getattr(event, attribute, None)
        if isinstance(value, str) and value:
            return value
    return None


def _event_delta(event: object) -> str:
    for attribute in ("delta", "response", "content"):
        value = getattr(event, attribute, None)
        if isinstance(value, str) and value:
            return value
    return ""


async def stream_agent_events(
    agent: ReActAgent,
    context: Context,
    prompt: str,
    emit_thinking: bool = True,
) -> AsyncIterator[dict[str, Any]]:
    handler = agent.run(user_msg=prompt, ctx=context)
    stream_events = getattr(handler, "stream_events", None)
    thought_parts: list[str] = []
    image_url: str | None = None
    splitter = StreamThoughtSplitter()

    def _emit(kind: str, text: str) -> dict[str, Any] | None:
        if kind == "thought":
            thought_parts.append(text)
            if emit_thinking:
                return {"type": "thought", "text": text}
            return None
        accumulated_holder.append(text)
        return {"type": "token", "text": text}

    accumulated_holder: list[str] = []

    if not callable(stream_events):
        response_object = await handler
        raw = extract_response_text(response_object)
        thought, answer = split_thinking_from_answer(raw)
        if emit_thinking and thought:
            yield {"type": "thought", "text": thought}
        content = normalize_response_content(answer or ("" if thought else raw))
        yield {"type": "token", "text": content}
        yield {
            "type": "done",
            "content": content,
            "image_url": infer_latest_image_url(content),
        }
        return

    async for event in handler.stream_events():
        event_name = type(event).__name__
        tool_name = _event_tool_name(event)
        thought = getattr(event, "thought", None) or getattr(event, "reasoning", None)
        extra = getattr(event, "additional_kwargs", None)
        if isinstance(extra, dict):
            thought = thought or extra.get("reasoning_content") or extra.get("reasoning")
        if isinstance(thought, str) and thought.strip() and emit_thinking:
            yield {"type": "thought", "text": thought.strip()}
        if "ToolCall" in event_name and "Result" not in event_name:
            if emit_thinking:
                yield {"type": "tool_start", "name": tool_name or "tool"}
            continue
        if "ToolCallResult" in event_name or event_name.endswith("ToolResult"):
            output = getattr(event, "tool_output", None) or getattr(event, "content", None)
            output_text = output if isinstance(output, str) else json.dumps(output, default=str)
            image_url = infer_latest_image_url(output_text) or image_url
            if emit_thinking:
                yield {"type": "tool_end", "name": tool_name or "tool"}
            if image_url:
                yield {"type": "image", "url": image_url}
            continue
        delta = _event_delta(event)
        if delta:
            for kind, text in splitter.feed(delta):
                payload = _emit(kind, text)
                if payload:
                    yield payload

    for kind, text in splitter.flush():
        payload = _emit(kind, text)
        if payload:
            yield payload

    response_object = await handler
    raw = extract_response_text(response_object) or "".join(accumulated_holder)
    thought, answer = split_thinking_from_answer(raw)
    streamed_thought = "".join(thought_parts)
    if emit_thinking and thought and not streamed_thought.strip():
        yield {"type": "thought", "text": thought}
    content = normalize_response_content(answer or ("" if thought else raw))
    image_url = infer_latest_image_url(content) or image_url
    yield {"type": "done", "content": content, "image_url": image_url}


def _openai_like(model: str) -> OpenAILike:
    base = llm_api_base()
    if not base:
        raise RuntimeError(LLM_UNCONFIGURED)
    return OpenAILike(
        model=model,
        api_base=base,
        api_key=os.getenv("LLM_API_KEY", "dummy"),
        is_chat_model=True,
        is_function_calling_model=True,
    )


async def build_agent(mcp_client: ReliabilityMCPClient, model: str) -> ReActAgent:
    Settings.llm = _openai_like(model)
    return ReActAgent(
        tools=await mcp_client.llama_tools(),
        system_prompt=SYSTEM_PROMPT,
    )


def create_app() -> FastAPI:
    mcp_client = ReliabilityMCPClient()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await mcp_client.start()
        app.state.llm_model = None
        app.state.agent = None
        app.state.agent_context = None
        yield
        await mcp_client.close()

    app = FastAPI(title="Reliability Agent", lifespan=lifespan)
    allowed_origins = [
        origin.strip()
        for origin in os.getenv(
            "FRONTEND_ORIGIN",
            "http://localhost:4200,http://localhost:8000,http://127.0.0.1:8000",
        ).split(",")
        if origin.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    async def apply_chat_model(model: str | None) -> None:
        if not llm_api_base():
            raise HTTPException(status_code=503, detail=LLM_UNCONFIGURED)
        chosen = (model or "").strip()
        if not chosen:
            try:
                listed = await fetch_llm_models_cached()
            except (
                urllib.error.URLError,
                TimeoutError,
                OSError,
                json.JSONDecodeError,
                RuntimeError,
            ) as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            chosen = pick_listed_model(listed, preferred_llm_model()) or ""
        if not chosen:
            raise HTTPException(
                status_code=503,
                detail=f"No models at {llm_api_base()}. Start the LLM server or check LLM_API_BASE in .env.",
            )
        if getattr(app.state, "llm_model", None) == chosen and getattr(app.state, "agent", None):
            return
        app.state.agent = await build_agent(mcp_client, chosen)
        app.state.agent_context = Context(app.state.agent)
        app.state.llm_model = chosen

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "mcp": "connected"}

    @app.get("/api/models")
    async def list_models() -> dict[str, Any]:
        base = llm_api_base()
        if not base:
            return {
                "configured": False,
                "models": [],
                "current": None,
                "base": "",
                "error": LLM_UNCONFIGURED,
            }
        try:
            models = await fetch_llm_models_cached()
        except (
            urllib.error.URLError,
            TimeoutError,
            OSError,
            json.JSONDecodeError,
            RuntimeError,
        ) as exc:
            return {
                "configured": True,
                "models": [],
                "current": None,
                "base": base,
                "error": f"No models at {base}. Is the LLM server running? {exc}",
            }
        current = pick_listed_model(models, preferred_llm_model())
        return {"configured": True, "models": models, "current": current, "base": base}

    @app.get("/api/knowledge/status")
    async def knowledge_status() -> dict[str, Any]:
        knowledge_base = ReliabilityKnowledgeBase()
        manifest = knowledge_base._read_manifest()
        indexed = manifest.get("files") or {}
        files = []
        for path in knowledge_base._documents():
            source = path.relative_to(knowledge_base.knowledge_base_dir).as_posix()
            info = indexed.get(source) or {}
            files.append(
                {
                    "source": source,
                    "chunks": info.get("chunks"),
                    "indexed": source in indexed,
                }
            )
        return {
            "embedding_model": knowledge_base.embedding_model_name,
            "files": files,
            "chunk_count": sum(int(item.get("chunks") or 0) for item in indexed.values()),
        }

    @app.post("/api/knowledge/upload")
    async def knowledge_upload(file: UploadFile = File(...)) -> dict[str, Any]:
        filename = Path(file.filename or "").name
        suffix = Path(filename).suffix.casefold()
        if not filename or suffix not in SUPPORTED_SUFFIXES:
            raise HTTPException(status_code=400, detail="Unsupported document type")
        KNOWLEDGE_BASE_DIR.mkdir(parents=True, exist_ok=True)
        destination = KNOWLEDGE_BASE_DIR / filename
        destination.write_bytes(await file.read())
        return {
            "source": filename,
            "indexed": False,
            "message": "Saved. The next knowledge search will embed this file.",
        }

    @app.post("/api/chat", response_model=ChatResponse)
    async def chat_endpoint(request: ChatRequest) -> ChatResponse:
        try:
            await apply_chat_model(request.model)
            response_object = await app.state.agent.run(
                user_msg=request.prompt, ctx=app.state.agent_context
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Agent inference failed: {exc}") from exc

        raw = extract_response_text(response_object)
        _thought, answer = split_thinking_from_answer(raw)
        content = normalize_response_content(answer or ("" if _thought else raw))
        return ChatResponse(content=content, image_url=infer_latest_image_url(content))

    @app.post("/api/chat/stream")
    async def chat_stream(request: ChatRequest) -> StreamingResponse:
        async def generate() -> AsyncIterator[str]:
            try:
                await apply_chat_model(request.model)
                async for event in stream_agent_events(
                    app.state.agent,
                    app.state.agent_context,
                    request.prompt,
                    emit_thinking=request.thinking,
                ):
                    yield _sse(event)
            except HTTPException as exc:
                yield _sse({"type": "error", "message": str(exc.detail)})
            except Exception as exc:
                yield _sse({"type": "error", "message": f"Agent inference failed: {exc}"})

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/{full_path:path}", response_model=None)
    async def serve_ui(full_path: str):
        if not UI_DIR.exists() or not (UI_DIR / "index.html").exists():
            return {
                "status": "ok",
                "ui": "not built",
                "hint": "Run scripts/build_ui.ps1, then restart the backend.",
            }
        candidate = (UI_DIR / full_path).resolve()
        ui_root = UI_DIR.resolve()
        if full_path and candidate.is_file() and ui_root in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(UI_DIR / "index.html")

    return app


app = create_app()


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
