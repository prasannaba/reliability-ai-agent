"""HTTP chat host and LLM orchestration client for pluggable MCP domains.

Generic host: it serves whatever domain ``ACTIVE_DOMAIN`` selects (see
``src.host.domain_registry``). No reliability/physics specifics live here —
the system prompt, MCP server list, and knowledge locations all come from
the active domain's ``domain.yaml`` / ``prompt.md`` /
``config/mcp_servers.<domain>.json``.
"""

from __future__ import annotations

import asyncio
import base64
import concurrent.futures
import contextvars
import hashlib
import hmac
import ipaddress
import json
import logging
import os
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import uvicorn
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from llama_index.core import Settings
from llama_index.core.agent.workflow import ReActAgent
from llama_index.core.workflow import Context
from llama_index.llms.openai_like import OpenAILike
from pydantic import BaseModel, Field

from src.common.credential_store import (
    delete_api_key as _store_delete_key,
)
from src.common.credential_store import (
    get_api_key as _store_get_key,
)
from src.common.credential_store import (
    migrate_legacy_key as _store_migrate_key,
)
from src.common.credential_store import (
    set_api_key as _store_set_key,
)
from src.common.markdown_math import patch_markdown_math
from src.common.rate_limit import RateLimitMiddleware
from src.host.domain_registry import get_active_domain
from src.host.mcp_pool import (
    MultiMCPClient,
    ReliabilityMCPClient,  # noqa: F401  (back-compat re-export)
)
from src.knowledge.base import (
    SUPPORTED_SUFFIXES,
    GenericKnowledgeBase,
    ReliabilityKnowledgeBase,  # noqa: F401  (back-compat re-export)
)

BACKEND_DIR = Path(__file__).resolve().parents[2]
STATIC_DIR = BACKEND_DIR / "static"
UI_DIR = STATIC_DIR / "ui"
STATIC_DIR.mkdir(exist_ok=True)
load_dotenv(BACKEND_DIR.parent / ".env")


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


def active_system_prompt() -> str:
    """System prompt of the active domain (``domains/<name>/prompt.md``)."""
    return get_active_domain().system_prompt


#: Back-compat constant: resolves to the active domain's prompt at import time
#: (reliability by default — identical text to the historical constant).
SYSTEM_PROMPT = get_active_domain().system_prompt


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

    SECURITY: `apiKey` is write-only and write-through — it is forwarded to
    the backend credential manager (encrypted at rest, 0600) and NEVER
    persisted in `.llm_config.json`, NEVER returned by any endpoint, and
    NEVER stored in browser localStorage/sessionStorage (frontend keeps it
    in React memory only). Send `""` to revoke the stored key.
    """

    provider: str | None = Field(default=None, max_length=64)
    baseUrl: str | None = Field(default=None, max_length=2048)
    apiKey: str | None = Field(default=None, max_length=4096)
    model: str | None = Field(default=None, max_length=512)
    temperature: float | None = None
    systemPrompt: str | None = Field(default=None, max_length=4000)


class ChatResponse(BaseModel):
    content: str
    image_url: str | None = None


_FINAL_ANSWER = re.compile(r"(?:^|\n)\s*(?:Final\s+Answer|Answer)\s*:\s*", re.IGNORECASE)
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
                # Only a ReAct trace splits here: we are already inside one
                # (mode == "thought"), the prefix opens with "Thought:", or
                # there is no prefix at all. Otherwise this is plain answer
                # text that merely mentions "Answer:" — fall through and emit
                # it as tokens below.
                if (
                    self.mode == "thought"
                    or _THOUGHT_HEAD.search(thought)
                    or not thought.strip()
                ):
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

# Runtime overrides set via PUT /api/llm/config. Persisted to
# backend/.llm_config.json (gitignored) so the user's explicit provider choice
# survives restarts; env vars remain the fallback default.
# SECURITY: this dict must NEVER contain `apiKey` — secrets live only in
# credential_store (.llm_secret.enc, 0600). Any legacy `apiKey` found on disk
# is migrated into the store on load and stripped from the JSON.
_LLM_CONFIG_OVERRIDE: dict[str, Any] = {}

_RUNTIME_CONFIG_PATH = BACKEND_DIR / ".llm_config.json"

_PROVIDER_REQUIRED = (
    "No LLM provider selected. Choose a provider in Settings "
    "(or set LLM_PROVIDER in .env)."
)


def _load_runtime_config() -> None:
    try:
        payload = json.loads(_RUNTIME_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if isinstance(payload, dict):
        for key in ("provider", "baseUrl", "model", "temperature", "systemPrompt"):
            value = payload.get(key)
            if value is not None:
                _LLM_CONFIG_OVERRIDE[key] = value
        # One-time migration: a key saved by older versions in plaintext JSON
        # moves into the encrypted credential store, then is stripped.
        legacy_key = payload.get("apiKey")
        if isinstance(legacy_key, str) and legacy_key.strip():
            try:
                _store_migrate_key(legacy_key)
            except Exception:  # noqa: BLE001 - migration must not crash boot
                logging.getLogger(__name__).exception("API key migration failed")
            _LLM_CONFIG_OVERRIDE.pop("apiKey", None)
            _save_runtime_config()


def _save_runtime_config() -> None:
    # Defense in depth: never let a secret slip into the JSON snapshot even
    # if a caller accidentally puts one in the override dict.
    _LLM_CONFIG_OVERRIDE.pop("apiKey", None)
    try:
        _RUNTIME_CONFIG_PATH.write_text(
            json.dumps(_LLM_CONFIG_OVERRIDE, indent=2), encoding="utf-8"
        )
        try:
            _RUNTIME_CONFIG_PATH.chmod(0o600)
        except OSError:
            pass
    except OSError:
        pass


_load_runtime_config()


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


def resolve_llm_provider() -> str | None:
    """Explicitly selected provider only — there is no implicit default.

    Precedence: Settings choice (PUT /api/llm/config, persisted) > LLM_PROVIDER
    env var > None (unselected). LLM_API_BASE alone does not select a provider.
    """
    override = str(_LLM_CONFIG_OVERRIDE.get("provider") or "").strip().lower()
    if override in PROVIDER_DEFAULTS:
        return override
    env_provider = (os.getenv("LLM_PROVIDER") or "").strip().lower()
    if env_provider in PROVIDER_DEFAULTS:
        return env_provider
    return None


def is_provider_selected() -> bool:
    return resolve_llm_provider() is not None


def _apply_docker_host_alias(base: str) -> str:
    """Map loopback hosts to the Docker host gateway inside containers.

    The LLM runs on the user's machine, not in this container, so a saved or
    configured localhost/127.0.0.1 URL would otherwise point at the container
    itself. Only exact loopback hosts are rewritten; LAN/cloud URLs pass
    through untouched. No provider or URL is ever defaulted here.
    """
    if os.getenv("DOCKER_CONTAINER") and base:
        base = re.sub(r"://localhost(?=[/:]|$)", "://host.docker.internal", base)
        base = re.sub(r"://127\.0\.0\.1(?=[/:]|$)", "://host.docker.internal", base)
    return base


def llm_api_base() -> str | None:
    override = normalize_base_url(str(_LLM_CONFIG_OVERRIDE.get("baseUrl") or ""))
    if override:
        return _apply_docker_host_alias(override)
    value = normalize_base_url(os.getenv("LLM_API_BASE"))
    return _apply_docker_host_alias(value) if value else None


def llm_openai_base() -> str | None:
    base = llm_api_base()
    return openai_api_base(base) if base else None


# --- Request identity: single-user today, per-user ready for cloud ---
# The active user id rides a ContextVar set per request (see _user_context
# middleware). Single-user runs always resolve "local". Cloud deploys set
# AUTH_MODE=proxy-header so an ingress sidecar (Azure Easy Auth) supplies the
# identity; secrets are then namespaced per user in the credential store.
current_user: contextvars.ContextVar[str] = contextvars.ContextVar("llm_user", default="local")


def llm_api_key(user: str | None = None) -> str:
    """Resolve the LLM key without ever exposing it to callers.

    Precedence: per-user encrypted credential store (Settings save) >
    LLM_API_KEY env var > "dummy". The in-memory `_LLM_CONFIG_OVERRIDE`
    dict NEVER holds the key (legacy copies are migrated on load).
    """
    uid = user if user is not None else current_user.get()
    try:
        stored = _store_get_key(uid)
    except Exception:  # noqa: BLE001 - a corrupt store must not crash chat
        stored = ""
    if stored:
        return stored
    return os.getenv("LLM_API_KEY", "dummy") or "dummy"


def llm_has_api_key(user: str | None = None) -> bool:
    key = llm_api_key(user)
    return bool(key and key != "dummy")


def _auth_mode() -> str:
    return (os.getenv("AUTH_MODE") or "single").strip().lower()


def resolve_user_id(request: Request) -> str:
    """Map a request to a stable user id for secret namespacing.

    - AUTH_MODE=single (default): always "local".
    - AUTH_MODE=proxy-header: trust TRUST_PROXY_USER_HEADER only when the
      direct peer is loopback (ingress sidecar on the same host strips any
      client-supplied value). Anything else falls back to "local" so a
      spoofed header can never mint someone else's namespace — worst case it
      is ignored. Supports Azure Easy Auth's X-MS-CLIENT-PRINCIPAL (base64
      JSON with userId/claims) or a plain upstream user id header.
    """
    if _auth_mode() != "proxy-header":
        return "local"
    header_name = (os.getenv("TRUST_PROXY_USER_HEADER") or "X-MS-CLIENT-PRINCIPAL").strip()
    peer = (request.client.host if request.client else "") or ""
    try:
        if not ipaddress.ip_address(peer).is_loopback:
            logging.getLogger(__name__).warning(
                "Ignoring proxy user header from non-loopback peer %s", peer
            )
            return "local"
    except ValueError:
        return "local"
    raw = (request.headers.get(header_name) or "").strip()
    if not raw:
        return "local"
    identity = raw
    try:
        padded = raw + "=" * (-len(raw) % 4)
        payload = json.loads(base64.b64decode(padded).decode("utf-8"))
        if isinstance(payload, dict):
            claims = payload.get("claims") or []
            oid = next(
                (
                    str(c.get("val") or "")
                    for c in claims
                    if isinstance(c, dict)
                    and str(c.get("typ") or "").lower().endswith(("objectidentifier", "/oid", "oid"))
                ),
                "",
            )
            identity = oid or str(payload.get("userId") or raw)
    except Exception:  # noqa: BLE001 - plain (non-Easy-Auth) header value
        identity = raw
    if not identity.strip():
        return "local"
    return "proxy:" + hashlib.sha256(identity.strip().encode("utf-8")).hexdigest()[:32]


# --- Write-auth (P0): optional APP_TOKEN gate for secret/config mutation ---
_bearer_scheme = HTTPBearer(auto_error=False)


def app_token_configured() -> bool:
    return bool((os.getenv("APP_TOKEN") or "").strip())


def require_write_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> None:
    """Enforce `Authorization: Bearer <APP_TOKEN>` on mutating endpoints, but
    only when APP_TOKEN is configured. Local single-user runs (no token set)
    keep working; any network-shared deployment MUST set APP_TOKEN and bind
    behind TLS. Uses hmac.compare_digest to avoid timing leaks."""
    expected = (os.getenv("APP_TOKEN") or "").strip()
    if not expected:
        return
    provided = (credentials.credentials if credentials else "").strip()
    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Unauthorized (bad or missing app token)")


# Hosts that must never be reachable as an LLM backend (cloud metadata).
_BLOCKED_BASE_HOSTS = frozenset(
    {
        "169.254.169.254",
        "100.100.100.200",  # Alibaba Cloud metadata
        "metadata.google.internal",
        "metadata.goog",
        "instance-data",  # EC2 historically
    }
)

# Resolved IPs that are always denied, even with ALLOW_PRIVATE_LLM=true.
_ALWAYS_DENIED_NETS = tuple(
    ipaddress.ip_network(net)
    for net in (
        "169.254.169.254/32",  # AWS/GCP/Azure IMDS
        "100.100.100.200/32",  # Alibaba IMDS
        "0.0.0.0/8",  # unspecified (routes to localhost)
        "224.0.0.0/4",  # multicast
        "240.0.0.0/4",  # reserved
        "::/128",  # unspecified v6
        "ff00::/8",  # multicast v6
    )
)


def allow_private_llm() -> bool:
    """Local-first default: loopback/LAN LLM servers (Ollama, llama.cpp)
    keep working out of the box. Cloud deployments MUST set
    ALLOW_PRIVATE_LLM=false so a stored base URL can never point the
    backend at internal infrastructure."""
    return (os.getenv("ALLOW_PRIVATE_LLM", "true") or "").strip().lower() in ("1", "true", "yes")


def _resolve_host_ips(host: str) -> set[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """Numeric fast-path (no DNS) plus getaddrinfo fallback. Raises on
    unresolvable hosts so validation fails closed."""
    cleaned = host.strip().strip("[]")
    try:
        return {ipaddress.ip_address(cleaned)}
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(cleaned, None, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ValueError(f"Cannot resolve LLM host: {cleaned}") from exc
    ips: set[ipaddress.IPv4Address | ipaddress.IPv6Address] = set()
    for info in infos:
        try:
            ips.add(ipaddress.ip_address(info[4][0]))
        except ValueError:
            continue
    if not ips:
        raise ValueError(f"Cannot resolve LLM host: {cleaned}")
    return ips


def _check_host_allowed(host: str) -> None:
    """Raise HTTPException(400) when `host` is not an acceptable LLM target."""
    lowered = host.strip().lower().strip("[]")
    if not lowered or lowered in _BLOCKED_BASE_HOSTS:
        raise HTTPException(status_code=400, detail="baseUrl host is not allowed")
    try:
        ips = _resolve_host_ips(lowered)
    except ValueError:
        raise HTTPException(status_code=400, detail="baseUrl host does not resolve") from None
    for ip in ips:
        if any(ip in net for net in _ALWAYS_DENIED_NETS):
            raise HTTPException(status_code=400, detail="baseUrl host is not allowed")
        if (
            not allow_private_llm()
            and (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved)
        ):
            raise HTTPException(
                status_code=400,
                detail="baseUrl targets a private/internal address (set ALLOW_PRIVATE_LLM=true for local LLMs)",
            )


def validate_base_url(raw: str | None) -> str:
    """Normalize + guard a user-supplied LLM base URL.

    Rejects non-http(s) schemes, unresolvable hosts, cloud metadata
    endpoints, and (unless ALLOW_PRIVATE_LLM=true) any resolved
    private/loopback/link-local address. DNS is resolved here at
    configuration time; fetch-time re-checks scheme + metadata host
    (see _assert_fetch_allowed) as defense-in-depth against rebinding.
    """
    base = normalize_base_url(raw)
    if not base:
        return base
    try:
        parts = urllib.parse.urlsplit(base)
    except ValueError:
        raise HTTPException(status_code=400, detail="baseUrl must be an http(s) URL") from None
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        raise HTTPException(status_code=400, detail="baseUrl must be an http(s) URL")
    _check_host_allowed(parts.hostname)
    return base


def _assert_fetch_allowed(url: str) -> None:
    """Cheap fetch-time guard (no DNS): scheme + literal metadata hosts.

    Called on every outbound LLM probe so a base URL that changed meaning
    after validation (DNS rebinding) still cannot reach metadata over a
    literal IP. Full DNS policy lives in validate_base_url.
    """
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError as exc:
        raise RuntimeError(f"Refusing to fetch invalid LLM URL: {url}") from exc
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        raise RuntimeError(f"Refusing to fetch non-http(s) LLM URL: {url}")
    if parts.hostname.strip().lower().strip("[]") in _BLOCKED_BASE_HOSTS:
        raise RuntimeError(f"Refusing to fetch blocked LLM host: {parts.hostname}")


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
    if not base and provider:
        base = PROVIDER_DEFAULTS.get(provider, "")
    model = _LLM_CONFIG_OVERRIDE.get("model") or preferred_llm_model()
    return {
        "provider": provider,
        "baseUrl": base,
        "openaiBase": openai_api_base(base) if base else "",
        # Boolean only — the secret itself is never serialized to any client.
        "hasApiKey": llm_has_api_key(),
        "model": model,
        "temperature": llm_temperature(),
        "systemPrompt": llm_system_prompt_extra(),
        "configured": provider is not None and bool(base),
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


_MAX_PROBE_BYTES = 1_000_000


def _http_get_json(url: str, timeout_seconds: float, api_key: str | None = None) -> Any:
    _assert_fetch_allowed(url)  # fetch-time SSRF guard (no DNS; see validate_base_url)
    key = api_key if api_key is not None else llm_api_key()
    request = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {key}"},
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        raw = response.read(_MAX_PROBE_BYTES + 1)
        if len(raw) > _MAX_PROBE_BYTES:
            raise ValueError("LLM probe response too large")
        return json.loads(raw.decode("utf-8"))


def _probe_all(
    urls: list[str],
    timeout_seconds: float,
    stop_when: Any = None,
    probe_key: str | None = None,
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
            return (url, True, _http_get_json(url, timeout_seconds, api_key=probe_key))
        except Exception as exc:  # noqa: BLE001 - collected below
            return (url, False, f"{type(exc).__name__}: probe failed")

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


def fetch_llm_models(
    timeout_seconds: float = 3.0,
    api_key: str | None = None,
    base: str | None = None,
) -> list[str]:
    """List models, racing OpenAI-compatible, Ollama-native, and /props endpoints.

    The key is resolved in the caller's (async request) context and passed
    explicitly into the probe pool: worker threads do NOT inherit the
    request's ContextVar user, so falling back to llm_api_key() down there
    would silently use the wrong user's secret in multi-user mode.
    `base` overrides the configured endpoint (used by the connection-test
    probe so it can list a candidate URL without persisting it).
    """
    resolved = normalize_base_url(base) if base else llm_api_base()
    if not resolved:
        raise RuntimeError(LLM_UNCONFIGURED)
    # Candidate probes from Settings carry the raw typed URL (e.g. localhost
    # from the provider defaults). Inside a container that points at the
    # container itself, so map loopback to the Docker host gateway exactly
    # like llm_api_base() does for the saved config. Idempotent on hosts.
    resolved = _apply_docker_host_alias(resolved)
    key = api_key if api_key is not None else llm_api_key()
    api_base = openai_api_base(resolved)
    models_url = f"{api_base}/models"
    tags_url = f"{resolved}/api/tags"
    props_url = f"{resolved}/props"
    successes, errors = _probe_all(
        [models_url, tags_url, props_url], timeout_seconds, probe_key=key
    )

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
    # Generic to callers: exception text may contain paths/host internals.
    raise RuntimeError(
        f"No models at {resolved} ({models_url}, {tags_url}). Is the LLM server running?"
    )


def test_llm_connection(
    timeout_seconds: float = 3.0,
    base_override: str | None = None,
    key_override: str | None = None,
) -> tuple[bool, str]:
    """Probe listing/health endpoints concurrently; mirrors MDLithe testConnection logic.

    `base_override`/`key_override` allow probing a candidate config WITHOUT
    persisting it (used by POST /api/llm/test so a pasted key is transient).
    Error strings are generic on purpose — no exception text, paths, or key
    material is ever returned to the caller.
    """
    base = base_override if base_override is not None else llm_api_base()
    if not base:
        return False, LLM_UNCONFIGURED
    # Same Docker loopback mapping as fetch_llm_models: candidate probes must
    # reach the host gateway when the backend runs in a container. Idempotent.
    base = _apply_docker_host_alias(base)
    # Resolve here (request context): pool threads don't inherit ContextVars.
    key = key_override if key_override is not None else llm_api_key()
    api_base = openai_api_base(base)
    candidates = [f"{api_base}/models", f"{base}/api/tags", f"{base}/health", f"{base}/props", base]
    successes, _errors = _probe_all(candidates, timeout_seconds, probe_key=key)
    for url in candidates:
        if url in successes:
            return True, f"Connected to {url}"
    return False, f"Could not reach {base}. Is the server running?"


async def fetch_llm_models_cached() -> list[str]:
    """Reuse /v1/models for a few seconds so status + chat do not block twice."""
    global _models_cache
    base = llm_api_base() or ""
    # Cache is namespaced by (base, key-hash): asyncio.to_thread propagates
    # the request ContextVar, but the shared cache must not leak one user's
    # listing to another when keys differ.
    key_hash = hashlib.sha256(llm_api_key().encode("utf-8")).hexdigest()[:16]
    cache_key = f"{base}\x00{key_hash}"
    now = time.monotonic()
    if _models_cache and _models_cache[1] == cache_key and now - _models_cache[0] < _MODELS_TTL_SECONDS:
        return _models_cache[2]
    key = llm_api_key()
    models = await asyncio.to_thread(fetch_llm_models, 3.0, key)
    _models_cache = (now, cache_key, models)
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


def _domain_kb() -> GenericKnowledgeBase:
    """KB handle for the active domain (collection/index namespaced per domain)."""
    domain = get_active_domain()
    return GenericKnowledgeBase(
        knowledge_base_dir=domain.knowledge_dir,
        index_dir=domain.index_dir,
        collection_name=domain.collection,
    )


# Back-compat: historical module-level name used by older imports/tests.
KNOWLEDGE_BASE_DIR = get_active_domain().knowledge_dir

_KB_SINGLETON: GenericKnowledgeBase | None = None
_KB_SINGLETON_DOMAIN: str | None = None


def _kb_instance() -> GenericKnowledgeBase:
    """Reuse one KB instance so the embedder is not reloaded per chat request."""
    global _KB_SINGLETON, _KB_SINGLETON_DOMAIN
    domain = get_active_domain()
    if _KB_SINGLETON is None or _KB_SINGLETON_DOMAIN != domain.name:
        _KB_SINGLETON = GenericKnowledgeBase(
            knowledge_base_dir=domain.knowledge_dir,
            index_dir=domain.index_dir,
            collection_name=domain.collection,
        )
        _KB_SINGLETON_DOMAIN = domain.name
    return _KB_SINGLETON


def _format_kb_matches(matches: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for match in matches:
        source = str(match.get("source") or "knowledge-base")
        content = str(match.get("content") or "").strip()
        if content:
            parts.append(f"[{source}] {content}")
    return "\n\n".join(parts)


async def retrieve_kb_context(prompt: str, max_results: int = 3) -> str:
    """Deterministic RAG: fetch KB matches for the raw user prompt.

    This runs even when the LLM would not call search_reliability_knowledge
    on its own (e.g. "Who is Prasanna?"). Returns "" when nothing matches
    or the index is unavailable, so callers can fall back to the raw prompt.
    """
    query = (prompt or "").strip()
    if not query:
        return ""
    try:
        result = await asyncio.to_thread(_kb_instance().search, query, max_results)
    except Exception:
        return ""
    if not isinstance(result, dict):
        return ""
    matches = result.get("matches") or []
    if not isinstance(matches, list) or not matches:
        return ""
    return _format_kb_matches(matches)


def build_augmented_prompt(prompt: str, kb_context: str) -> str:
    """Combine the user question with retrieved KB context for the agent."""
    if not kb_context:
        return prompt
    return (
        f"User question: {prompt}\n\n"
        "Local knowledge-base context (use it and cite its [source] in your answer):\n"
        f"{kb_context}"
    )


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


async def build_agent(mcp_client: MultiMCPClient, model: str) -> ReActAgent:
    Settings.llm = _openai_like(model)
    extra = llm_system_prompt_extra()
    base = active_system_prompt()
    prompt = base if not extra else f"{base}\n\nAdditional operator instructions: {extra}"
    return ReActAgent(
        tools=await mcp_client.llama_tools(),
        system_prompt=prompt,
    )


def create_app() -> FastAPI:
    domain = get_active_domain()
    mcp_client = MultiMCPClient(extra_config_path=domain.servers_config)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await mcp_client.start()
        app.state.llm_model = None
        app.state.agent = None
        app.state.agent_context = None
        yield
        await mcp_client.close()

    app = FastAPI(title=f"{domain.title} Agent", lifespan=lifespan)
    allowed_origins = [
        origin.strip()
        for origin in os.getenv(
            "FRONTEND_ORIGIN",
            "http://localhost:4200,http://localhost:8000,http://127.0.0.1:8000",
        ).split(",")
        if origin.strip()
    ]
    if "*" in allowed_origins:
        raise RuntimeError("FRONTEND_ORIGIN must list explicit origins; '*' is not allowed.")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept"],
    )

    @app.middleware("http")
    async def _security_headers(request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        # No inline-script reliance in served UI; keep CSP tight.
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data: blob:; "
            "style-src 'self' 'unsafe-inline'; script-src 'self'; "
            "connect-src 'self'; frame-ancestors 'none'"
        )
        return response

    @app.middleware("http")
    async def _user_context(request: Request, call_next):  # type: ignore[no-untyped-def]
        # Bind request identity for the whole call (endpoints + llm_api_key
        # resolution + asyncio.to_thread fan-out). Reset afterwards so a
        # reused task never leaks one user's namespace into another.
        token = current_user.set(resolve_user_id(request))
        try:
            return await call_next(request)
        finally:
            current_user.reset(token)

    # In-memory per-IP rate limits (see rate_limit.py). Independent per
    # worker; cloud perimeters should ALSO limit at the ingress/gateway.
    app.add_middleware(RateLimitMiddleware)

    # Fail-open warning (not crash): an operator-set env base URL bypasses
    # the PUT-time validator, so check it once here at startup.
    _env_base = (os.getenv("LLM_API_BASE") or "").strip()
    if _env_base:
        try:
            validate_base_url(_env_base)
        except HTTPException:
            logging.getLogger(__name__).warning(
                "LLM_API_BASE=%r violates SSRF policy; LLM calls may fail. "
                "Fix the URL or set ALLOW_PRIVATE_LLM=true for local LLMs.",
                _env_base,
            )

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    async def apply_chat_model(model: str | None) -> None:
        if not is_provider_selected():
            raise HTTPException(status_code=503, detail=_PROVIDER_REQUIRED)
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
                logging.getLogger(__name__).warning("LLM model listing failed: %s", exc)
                raise HTTPException(
                    status_code=503,
                    detail="LLM server unreachable. Check the endpoint and try again.",
                ) from exc
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
            # Hash, not the secret itself — never keep raw key in app.state.
            hashlib.sha256(llm_api_key().encode("utf-8")).hexdigest(),
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
        return {"status": "ok", "mcp": "connected", "domain": domain.name}

    @app.get("/api/domains")
    async def list_domains() -> dict[str, Any]:
        """Domains available under ``src/domains/`` and which one is active."""
        try:
            from src.host.domain_registry import list_domains as _available
        except ImportError:
            from domain_registry import list_domains as _available  # type: ignore[no-redef]
        return {"active": domain.name, "domains": _available(), "title": domain.title}

    @app.get("/api/mcp/tools")
    async def list_mcp_tools() -> dict[str, Any]:
        """Tool inventory of every connected MCP server (proves pluggability)."""
        tools = await mcp_client.list_tools()
        return {
            "domain": domain.name,
            "count": len(tools),
            "tools": [
                {
                    "name": getattr(tool, "name", ""),
                    "description": getattr(tool, "description", "") or "",
                }
                for tool in tools
            ],
        }

    @app.get("/api/models")
    async def list_models() -> dict[str, Any]:
        base = llm_api_base()
        snapshot = llm_config_snapshot()
        if not is_provider_selected():
            return {
                "configured": False,
                "models": [],
                "current": None,
                "base": "",
                "provider": None,
                "providers": PROVIDER_DEFAULTS,
                "error": _PROVIDER_REQUIRED,
            }
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
            logging.getLogger(__name__).warning("LLM model listing failed: %s", exc)
            return {
                "configured": True,
                "models": [],
                "current": None,
                "base": base,
                "provider": snapshot["provider"],
                "providers": PROVIDER_DEFAULTS,
                "error": f"No models at {base}. Is the LLM server running?",
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

    @app.put("/api/llm/config", dependencies=[Depends(require_write_auth)])
    async def put_llm_config(update: LlmConfigUpdate) -> dict[str, Any]:
        global _models_cache
        # Request identity comes from the _user_context middleware ContextVar
        # ("local" in single-user mode, per-user id in cloud proxy-header mode).
        user = current_user.get()
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
            _LLM_CONFIG_OVERRIDE["baseUrl"] = validate_base_url(update.baseUrl)
        if update.apiKey is not None:
            # Write-through to the per-user credential manager. Empty revokes.
            # The key NEVER enters _LLM_CONFIG_OVERRIDE or the JSON file.
            candidate = update.apiKey.strip()
            if not candidate:
                _store_delete_key(user)
            else:
                if len(candidate) > 4096:
                    raise HTTPException(status_code=400, detail="apiKey too long")
                _store_set_key(candidate, user)
            del candidate
        if update.model is not None:
            _LLM_CONFIG_OVERRIDE["model"] = update.model.strip()[:512]
            os.environ["LLM_MODEL"] = update.model.strip()[:512]
        if update.temperature is not None:
            if not 0.0 <= update.temperature <= 2.0:
                raise HTTPException(status_code=400, detail="temperature must be 0..2")
            _LLM_CONFIG_OVERRIDE["temperature"] = float(update.temperature)
        if update.systemPrompt is not None:
            _LLM_CONFIG_OVERRIDE["systemPrompt"] = update.systemPrompt.strip()[:4000]
        _models_cache = None
        app.state.llm_fingerprint = None
        _save_runtime_config()
        snapshot = llm_config_snapshot()
        return {**snapshot, "providers": PROVIDER_DEFAULTS}

    @app.delete("/api/llm/secret", dependencies=[Depends(require_write_auth)])
    async def delete_llm_secret() -> dict[str, Any]:
        """Explicit revoke: forget the stored key. GET never had it."""
        _store_delete_key(current_user.get())
        app.state.llm_fingerprint = None
        snapshot = llm_config_snapshot()
        return {**snapshot, "providers": PROVIDER_DEFAULTS}

    @app.post("/api/llm/test", dependencies=[Depends(require_write_auth)])
    async def test_llm_config(update: LlmConfigUpdate | None = None) -> dict[str, Any]:
        # Probe a candidate config WITHOUT persisting anything. A pasted
        # apiKey is used transiently for this probe only and never stored
        # (use PUT to save). Nothing secret is echoed back.
        candidate_base: str | None = None
        candidate_key: str | None = None
        candidate_provider: str | None = None
        try:
            if update is not None:
                if update.provider:
                    candidate_provider = update.provider.strip().lower()[:64]
                    if candidate_provider not in PROVIDER_DEFAULTS:
                        raise HTTPException(
                            status_code=400, detail=f"Unknown provider: {update.provider}"
                        )
                if update.baseUrl is not None:
                    candidate_base = validate_base_url(update.baseUrl)
                if update.apiKey is not None:
                    candidate_key = update.apiKey.strip()[:4096] or None
            provider = candidate_provider or resolve_llm_provider()
            if provider is None:
                return {"ok": False, "message": _PROVIDER_REQUIRED, "models": []}
            base = candidate_base or llm_api_base()
            if not base:
                return {"ok": False, "message": LLM_UNCONFIGURED, "models": []}
            key = candidate_key or llm_api_key()
            ok, message = await asyncio.to_thread(
                test_llm_connection, 3.0, base, key
            )
            models: list[str] = []
            # List against the probed base with the probed key (candidate key
            # when pasted, otherwise the saved key) so provider switches,
            # refresh, and typed keys populate the model list immediately.
            # Called directly (not via the cache) so an explicitly typed
            # candidate base URL lists its own models and a transient key is
            # never persisted or used to poison the shared cache.
            if ok:
                try:
                    models = await asyncio.to_thread(fetch_llm_models, 3.0, key, base)
                except Exception:  # noqa: BLE001 - connection ok, listing failed
                    models = []
            return {"ok": ok, "message": message, "models": models}
        finally:
            candidate_key = None

    @app.get("/api/knowledge/status")
    async def knowledge_status() -> dict[str, Any]:
        knowledge_base = _domain_kb()
        # Reconcile the index first: without this the endpoint serves whatever
        # the manifest happened to contain (stale after files are added or
        # removed), e.g. "0 files" while documents exist on disk.
        warnings = await asyncio.to_thread(knowledge_base.ensure_index)
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
            "index_warnings": warnings,
        }

    @app.post("/api/knowledge/upload", dependencies=[Depends(require_write_auth)])
    async def knowledge_upload(file: UploadFile = File(...)) -> dict[str, Any]:
        filename = Path(file.filename or "").name
        suffix = Path(filename).suffix.casefold()
        if not filename or suffix not in SUPPORTED_SUFFIXES:
            raise HTTPException(status_code=400, detail="Unsupported document type")
        # 10 MB streaming cap: never buffer an unbounded upload in RAM.
        _MAX_UPLOAD_BYTES = 10 * 1024 * 1024
        kb_dir = get_active_domain().knowledge_dir
        kb_dir.mkdir(parents=True, exist_ok=True)
        destination = kb_dir / filename
        size = 0
        try:
            with destination.open("wb") as handle:
                while True:
                    chunk = await file.read(1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > _MAX_UPLOAD_BYTES:
                        handle.close()
                        try:
                            destination.unlink()
                        except OSError:
                            pass
                        raise HTTPException(status_code=413, detail="File too large (max 10 MB)")
                    handle.write(chunk)
        finally:
            await file.close()
        return {
            "source": filename,
            "indexed": False,
            "message": "Saved. It will be indexed automatically (status refresh or next search).",
        }

    @app.post("/api/chat", response_model=ChatResponse)
    async def chat_endpoint(request: ChatRequest) -> ChatResponse:
        try:
            await apply_chat_model(request.model)
            kb_context = await retrieve_kb_context(request.prompt)
            response_object = await app.state.agent.run(
                user_msg=build_augmented_prompt(request.prompt, kb_context),
                ctx=app.state.agent_context,
            )
        except HTTPException:
            raise
        except Exception as exc:
            logging.getLogger(__name__).exception("Agent inference failed")
            raise HTTPException(
                status_code=502, detail="Agent inference failed (see server logs)"
            ) from exc

        raw = extract_response_text(response_object)
        _thought, answer = split_thinking_from_answer(raw)
        content = normalize_response_content(answer or ("" if _thought else raw))
        return ChatResponse(content=content, image_url=infer_latest_image_url(content))

    @app.post("/api/chat/stream")
    async def chat_stream(request: ChatRequest) -> StreamingResponse:
        async def generate() -> AsyncIterator[str]:
            try:
                await apply_chat_model(request.model)
                kb_context = await retrieve_kb_context(request.prompt)
                async for event in stream_agent_events(
                    app.state.agent,
                    app.state.agent_context,
                    build_augmented_prompt(request.prompt, kb_context),
                    emit_thinking=request.thinking,
                ):
                    yield _sse(event)
            except HTTPException as exc:
                yield _sse({"type": "error", "message": str(exc.detail)})
            except Exception:
                logging.getLogger(__name__).exception("Agent stream failed")
                yield _sse({"type": "error", "message": "Agent inference failed (see server logs)"})

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


def main() -> None:
    """Serve the chat host (``python -m src.host.app`` from ``backend/``)."""
    # Default to loopback. Set HOST=0.0.0.0 only behind an authenticated TLS
    # reverse proxy, and set APP_TOKEN in that case.
    if app_token_configured() is False and (os.getenv("HOST", "127.0.0.1") == "0.0.0.0"):
        logging.getLogger(__name__).warning(
            "Binding 0.0.0.0 without APP_TOKEN: config/upload endpoints are "
            "unauthenticated on the network. Set APP_TOKEN in .env."
        )
    uvicorn.run(
        app,
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
    )


if __name__ == "__main__":
    main()
