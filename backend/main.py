"""HTTP chat host and LLM orchestration client for the reliability MCP server."""

from __future__ import annotations

import asyncio
import concurrent.futures
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


class LlmConfigUpdate(BaseModel):
    """Runtime LLM endpoint override.

    NOTE: must stay at module level. FastAPI resolves endpoint annotations
    from module globals (this file uses `from __future__ import annotations`,
    so annotations are strings); a class nested inside create_app() is
    invisible there and the parameter silently degrades to a query param,
    which made provider switching a no-op (422 on PUT, stale tests on POST).
    """

    provider: str | None = None
    baseUrl: str | None = None
    apiKey: str | None = None
    model: str | None = None
    temperature: float | None = None
    systemPrompt: str | None = None


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

# Provider presets mirrored from the MDLithe chat settings so the frontend can
# offer Ollama / LM Studio / llama.cpp / Unsloth / LiteRT-LM / OpenAI / custom
# endpoints without the user hand-editing .env for every switch.
PROVIDER_DEFAULTS: dict[str, str] = {
    "ollama": "http://localhost:11434",
    "lmstudio": "http://localhost:1234",
    "llamacpp": "http://localhost:8080",
    "unsloth": "http://127.0.0.1:8888",
    "openai": "https://api.openai.com/v1",
    "litert": "http://localhost:9379",
    "custom": "",
}

_KNOWN_ENDPOINT_SUFFIXES = (
    "/v1/chat/completions",
    "/v1/completions",
    "/v1/models",
    "/chat/completions",
    "/api/chat",
    "/api/tags",
    "/completion",
)

# Runtime overrides set via PUT /api/llm/config (in-memory; env remains default).
_LLM_CONFIG_OVERRIDE: dict[str, Any] = {}


def normalize_base_url(raw: str | None) -> str:
    """Reduce a pasted endpoint URL to its root (no doubled /v1/... segments)."""
    base = (raw or "").strip().rstrip("/")
    lowered = base.lower()
    for suffix in _KNOWN_ENDPOINT_SUFFIXES:
        if lowered.endswith(suffix) and len(base) > len(suffix):
            base = base[: -len(suffix)].rstrip("/")
            break
    return base


def openai_api_base(base: str) -> str:
    """Return the OpenAI-compatible root, guaranteeing exactly one /v1."""
    base = (base or "").strip().rstrip("/")
    if re.search(r"/v1$", base, re.IGNORECASE):
        return base
    return f"{base}/v1"


def resolve_llm_provider() -> str:
    override = str(_LLM_CONFIG_OVERRIDE.get("provider") or "").strip().lower()
    if override in PROVIDER_DEFAULTS:
        return override
    env_provider = (os.getenv("LLM_PROVIDER") or "").strip().lower()
    if env_provider in PROVIDER_DEFAULTS:
        return env_provider
    # Infer Ollama when the base URL is its default port without /v1.
    base = (os.getenv("LLM_API_BASE") or "")
    if ":11434" in base:
        return "ollama"
    return "custom"


def llm_api_base() -> str | None:
    override = normalize_base_url(str(_LLM_CONFIG_OVERRIDE.get("baseUrl") or ""))
    if override:
        return override
    value = normalize_base_url(os.getenv("LLM_API_BASE"))
    return value or None


def llm_openai_base() -> str | None:
    base = llm_api_base()
    return openai_api_base(base) if base else None


def llm_api_key() -> str:
    override = _LLM_CONFIG_OVERRIDE.get("apiKey")
    if isinstance(override, str) and override:
        return override
    return os.getenv("LLM_API_KEY", "dummy") or "dummy"


def llm_temperature() -> float:
    override = _LLM_CONFIG_OVERRIDE.get("temperature")
    if isinstance(override, (int, float)):
        return float(override)
    try:
        return float(os.getenv("LLM_TEMPERATURE", "0.1"))
    except ValueError:
        return 0.1


def llm_system_prompt_extra() -> str:
    override = _LLM_CONFIG_OVERRIDE.get("systemPrompt")
    if isinstance(override, str) and override.strip():
        return override.strip()
    return (os.getenv("LLM_SYSTEM_PROMPT") or "").strip()


def llm_config_snapshot() -> dict[str, Any]:
    base = llm_api_base() or ""
    provider = resolve_llm_provider()
    if not base:
        base = PROVIDER_DEFAULTS.get(provider, "")
    model = _LLM_CONFIG_OVERRIDE.get("model") or preferred_llm_model()
    return {
        "provider": provider,
        "baseUrl": base,
        "openaiBase": openai_api_base(base) if base else "",
        "hasApiKey": bool(llm_api_key() and llm_api_key() != "dummy"),
        "model": model,
        "temperature": llm_temperature(),
        "systemPrompt": llm_system_prompt_extra(),
        "configured": bool(base),
    }


def preferred_llm_model() -> str | None:
    override = str(_LLM_CONFIG_OVERRIDE.get("model") or "").strip()
    if override:
        return override
    value = (os.getenv("LLM_MODEL") or "").strip()
    return value or None


def pick_listed_model(models: list[str], preferred: str | None = None) -> str | None:
    if preferred and preferred in models:
        return preferred
    return models[0] if models else None


def parse_openai_model_ids(payload: object) -> list[str]:
    if not isinstance(payload, dict):
        if isinstance(payload, list):
            return [
                str(item).strip()
                if isinstance(item, str)
                else str(item.get("id") or item.get("name") or "").strip()
                for item in payload
                if (isinstance(item, str) and item.strip())
                or (isinstance(item, dict) and (item.get("id") or item.get("name")))
            ]
        return []
    ids: list[str] = []
    data = payload.get("data")
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and (item.get("id") or item.get("name")):
                ids.append(str(item.get("id") or item.get("name")))
            elif isinstance(item, str) and item.strip():
                ids.append(item.strip())
    if ids:
        return ids
    # Ollama native shape: {"models": [{"name": "llama3.1:8b", ...}]}
    extra = payload.get("models")
    if isinstance(extra, list):
        out: list[str] = []
        for item in extra:
            if isinstance(item, dict) and (item.get("name") or item.get("id")):
                out.append(str(item.get("name") or item.get("id")))
            elif isinstance(item, str) and item.strip():
                out.append(item.strip())
        if out:
            return out
    return []


def _http_get_json(url: str, timeout_seconds: float) -> Any:
    request = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {llm_api_key()}"},
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def _probe_all(
    urls: list[str],
    timeout_seconds: float,
    stop_when: Any = None,
) -> tuple[dict[str, Any], dict[str, str]]:
    """GET every candidate URL concurrently; return {url: payload} successes and {url: error}.

    Probes used to run sequentially, so one hanging candidate (slow Ollama
    cloud handshake, half-open server) stalled the settings dialog for
    6-20s+. Racing keeps total latency near the fastest responder, bounded
    by a single timeout for dead hosts. `stop_when(url, ok, payload)` ends
    the race early once a decisive (usually top-priority) answer arrives,
    without waiting for slow stragglers.
    """
    successes: dict[str, Any] = {}
    errors: dict[str, str] = {}

    def _get(url: str) -> tuple[str, bool, Any]:
        try:
            return (url, True, _http_get_json(url, timeout_seconds))
        except Exception as exc:  # noqa: BLE001 - collected below
            return (url, False, str(exc)[:200])

    pool = concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(urls)))
    try:
        futures = [pool.submit(_get, url) for url in urls]
        try:
            for future in concurrent.futures.as_completed(futures, timeout=timeout_seconds):
                url, ok, payload = future.result()
                if ok:
                    successes[url] = payload
                else:
                    errors[url] = payload
                if stop_when is not None and stop_when(url, ok, payload):
                    break
        except TimeoutError:
            pass
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    return successes, errors


def fetch_llm_models(timeout_seconds: float = 3.0) -> list[str]:
    """List models, racing OpenAI-compatible, Ollama-native, and /props endpoints."""
    base = llm_api_base()
    if not base:
        raise RuntimeError(LLM_UNCONFIGURED)
    api_base = openai_api_base(base)
    models_url = f"{api_base}/models"
    tags_url = f"{base}/api/tags"
    props_url = f"{base}/props"
    successes, errors = _probe_all([models_url, tags_url, props_url], timeout_seconds)

    # Priority 1: standard OpenAI-compatible listing (LM Studio, llamacpp,
    # vLLM, Ollama /v1/models, OpenAI, LiteRT-LM, Unsloth).
    if models_url in successes:
        ids = parse_openai_model_ids(successes[models_url])
        if ids:
            return ids
    # Priority 2: Ollama native listing.
    if tags_url in successes:
        ids = parse_openai_model_ids(successes[tags_url])
        if ids:
            return ids
    # Priority 3: llama.cpp single-model servers expose /props with model_path.
    if props_url in successes and isinstance(successes[props_url], dict):
        props = successes[props_url]
        candidate = (
            (props.get("default_generation_settings") or {}).get("model")
            or (str(props.get("model_path") or "").split("/")[-1].split("\\")[-1])
            or props.get("model")
        )
        if isinstance(candidate, str) and candidate.strip():
            return [candidate.strip()]
    first_error = errors.get(models_url) or errors.get(tags_url) or errors.get(props_url) or "unknown error"
    raise RuntimeError(
        f"No models at {base} ({models_url}, {tags_url}). "
        f"Is the LLM server running? {first_error}"
    )


def test_llm_connection(timeout_seconds: float = 3.0) -> tuple[bool, str]:
    """Probe listing/health endpoints concurrently; mirrors MDLithe testConnection logic."""
    base = llm_api_base()
    if not base:
        return False, LLM_UNCONFIGURED
    api_base = openai_api_base(base)
    candidates = [f"{api_base}/models", f"{base}/api/tags", f"{base}/health", f"{base}/props", base]
    successes, errors = _probe_all(candidates, timeout_seconds)
    for url in candidates:
        if url in successes:
            return True, f"Connected to {url}"
    last_error = errors.get(candidates[0], "")
    return False, f"Could not reach {base}. Is the server running? {last_error}"


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
    api_base = llm_openai_base()
    if not api_base:
        raise RuntimeError(LLM_UNCONFIGURED)
    return OpenAILike(
        model=model,
        api_base=api_base,
        api_key=llm_api_key(),
        is_chat_model=True,
        is_function_calling_model=True,
        temperature=llm_temperature(),
    )


async def build_agent(mcp_client: ReliabilityMCPClient, model: str) -> ReActAgent:
    Settings.llm = _openai_like(model)
    extra = llm_system_prompt_extra()
    prompt = SYSTEM_PROMPT if not extra else f"{SYSTEM_PROMPT}\n\nAdditional operator instructions: {extra}"
    return ReActAgent(
        tools=await mcp_client.llama_tools(),
        system_prompt=prompt,
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
        fingerprint = (
            chosen,
            llm_api_base(),
            llm_temperature(),
            llm_system_prompt_extra(),
            llm_api_key(),
        )
        if getattr(app.state, "llm_fingerprint", None) == fingerprint and getattr(
            app.state, "agent", None
        ):
            return
        app.state.agent = await build_agent(mcp_client, chosen)
        app.state.agent_context = Context(app.state.agent)
        app.state.llm_model = chosen
        app.state.llm_fingerprint = fingerprint

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "mcp": "connected"}

    @app.get("/api/models")
    async def list_models() -> dict[str, Any]:
        base = llm_api_base()
        snapshot = llm_config_snapshot()
        if not base:
            return {
                "configured": False,
                "models": [],
                "current": None,
                "base": "",
                "provider": snapshot["provider"],
                "providers": PROVIDER_DEFAULTS,
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
                "provider": snapshot["provider"],
                "providers": PROVIDER_DEFAULTS,
                "error": f"No models at {base}. Is the LLM server running? {exc}",
            }
        current = pick_listed_model(models, preferred_llm_model())
        return {
            "configured": True,
            "models": models,
            "current": current,
            "base": base,
            "provider": snapshot["provider"],
            "providers": PROVIDER_DEFAULTS,
        }

    @app.get("/api/llm/config")
    async def get_llm_config() -> dict[str, Any]:
        snapshot = llm_config_snapshot()
        return {**snapshot, "providers": PROVIDER_DEFAULTS}

    @app.put("/api/llm/config")
    async def put_llm_config(update: LlmConfigUpdate) -> dict[str, Any]:
        global _models_cache
        if update.provider is not None:
            provider = update.provider.strip().lower()
            if provider not in PROVIDER_DEFAULTS:
                raise HTTPException(status_code=400, detail=f"Unknown provider: {update.provider}")
            _LLM_CONFIG_OVERRIDE["provider"] = provider
            if update.baseUrl is None and provider in PROVIDER_DEFAULTS and PROVIDER_DEFAULTS[provider]:
                # Switch base URL to the provider default unless explicitly given.
                current = normalize_base_url(str(_LLM_CONFIG_OVERRIDE.get("baseUrl") or ""))
                if not current:
                    _LLM_CONFIG_OVERRIDE["baseUrl"] = PROVIDER_DEFAULTS[provider]
        if update.baseUrl is not None:
            _LLM_CONFIG_OVERRIDE["baseUrl"] = normalize_base_url(update.baseUrl)
        if update.apiKey is not None:
            _LLM_CONFIG_OVERRIDE["apiKey"] = update.apiKey
        if update.model is not None:
            _LLM_CONFIG_OVERRIDE["model"] = update.model.strip()
            os.environ["LLM_MODEL"] = update.model.strip()
        if update.temperature is not None:
            if not 0.0 <= update.temperature <= 2.0:
                raise HTTPException(status_code=400, detail="temperature must be 0..2")
            _LLM_CONFIG_OVERRIDE["temperature"] = float(update.temperature)
        if update.systemPrompt is not None:
            _LLM_CONFIG_OVERRIDE["systemPrompt"] = update.systemPrompt
        _models_cache = None
        app.state.llm_fingerprint = None
        snapshot = llm_config_snapshot()
        return {**snapshot, "providers": PROVIDER_DEFAULTS}

    @app.post("/api/llm/test")
    async def test_llm_config(update: LlmConfigUpdate | None = None) -> dict[str, Any]:
        # Optionally probe a candidate config without saving it.
        global _LLM_CONFIG_OVERRIDE
        saved = dict(_LLM_CONFIG_OVERRIDE)
        try:
            if update is not None:
                if update.provider:
                    _LLM_CONFIG_OVERRIDE["provider"] = update.provider.strip().lower()
                if update.baseUrl is not None:
                    _LLM_CONFIG_OVERRIDE["baseUrl"] = normalize_base_url(update.baseUrl)
                if update.apiKey is not None:
                    _LLM_CONFIG_OVERRIDE["apiKey"] = update.apiKey
            ok, message = await asyncio.to_thread(test_llm_connection)
            models: list[str] = []
            if ok:
                try:
                    models = await fetch_llm_models_cached()
                except Exception:  # noqa: BLE001 - connection ok, listing failed
                    models = []
            return {"ok": ok, "message": message, "models": models}
        finally:
            _LLM_CONFIG_OVERRIDE = saved

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
