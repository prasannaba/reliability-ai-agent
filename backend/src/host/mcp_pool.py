"""Persistent multi-server MCP client (stdio + SSE + streamable HTTP).

Domain-agnostic: the host connects to whatever MCP servers the active domain
config lists (``backend/config/mcp_servers.<domain>.json`` or the
``MCP_SERVERS_CONFIG`` env override). Entries may be local subprocesses
(``{"command", "args", "cwd"}``) or remote HTTP endpoints
(``{"url", "transport": "streamable-http" | "sse"}``) — the latter is how
Open Web UI / Unsloth Studio style hosts consume the same domain servers.
"""

from __future__ import annotations

import json
import os
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import BaseModel, Field, create_model

BACKEND_DIR = Path(__file__).resolve().parents[2]
CONFIG_DIR = BACKEND_DIR / "config"


def default_servers_config() -> Path:
    """Config file for the active domain (``ACTIVE_DOMAIN``, default reliability)."""
    override = (os.getenv("MCP_SERVERS_CONFIG") or "").strip()
    if override:
        return Path(override)
    domain = (os.getenv("ACTIVE_DOMAIN") or "reliability").strip().lower() or "reliability"
    return CONFIG_DIR / f"mcp_servers.{domain}.json"


DEFAULT_SERVERS_CONFIG = CONFIG_DIR / "mcp_servers.reliability.json"


JSON_TYPE_MAP = {
    "string": str,
    "number": float,
    "integer": int,
    "boolean": bool,
    "array": list,
    "object": dict,
}


class MultiMCPClient:
    """Maintain one :class:`ClientSession` per configured MCP server.

    ``ReliabilityMCPClient`` remains as a deprecated alias so existing
    imports keep working.
    """

    def __init__(
        self, server_path: Path | None = None, extra_config_path: Path | None = None
    ) -> None:
        self.server_path = server_path or (
            BACKEND_DIR / "src" / "domains" / "reliability" / "server.py"
        )
        self.extra_config_path = extra_config_path or default_servers_config()
        self._stack: AsyncExitStack | None = None
        self._sessions: dict[str, ClientSession] = {}
        self._tool_sessions: dict[str, ClientSession] = {}
        self._llama_tools_cache: list[Any] | None = None

    def _extra_servers(self) -> dict[str, dict[str, Any]]:
        if not self.extra_config_path.exists():
            return {}
        try:
            payload = json.loads(self.extra_config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        servers = payload.get("mcpServers") or payload.get("servers") or {}
        return servers if isinstance(servers, dict) else {}

    def _expand(self, value: str) -> str:
        """Expand ``${PYTHON}`` (current interpreter), ``${BACKEND_DIR}`` and
        ``${ENV_VAR}`` placeholders so configs stay portable across machines."""
        result = value.replace("${PYTHON}", sys.executable).replace(
            "${BACKEND_DIR}", str(BACKEND_DIR)
        )
        return os.path.expandvars(result)

    async def _open_stdio_session(
        self, stack: AsyncExitStack, command: str, args: list[str], cwd: str | None
    ) -> ClientSession:
        read_stream, write_stream = await stack.enter_async_context(
            stdio_client(
                StdioServerParameters(
                    command=command,
                    args=args,
                    cwd=cwd,
                )
            )
        )
        session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
        await session.initialize()
        return session

    async def _open_http_session(
        self, stack: AsyncExitStack, url: str, transport: str
    ) -> ClientSession:
        transport = (transport or "streamable-http").strip().lower()
        if transport == "sse":
            from mcp.client.sse import sse_client

            streams = await stack.enter_async_context(sse_client(url))
        else:
            from mcp.client.streamable_http import streamable_http_client

            streams = await stack.enter_async_context(streamable_http_client(url))
        read_stream, write_stream = streams[0], streams[1]
        session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
        await session.initialize()
        return session

    async def _open_session(
        self, stack: AsyncExitStack, command: str, args: list[str], cwd: str | None
    ) -> ClientSession:
        return await self._open_stdio_session(stack, command, args, cwd)

    async def start(self) -> None:
        if self._sessions:
            return

        stack = AsyncExitStack()
        try:
            extra = self._extra_servers()
            if extra:
                # Config-driven mode: every entry in
                # config/mcp_servers.<domain>.json is a server, either a
                # local subprocess (command/args/cwd) or a remote endpoint
                # (url + transport). This is what makes the host pluggable:
                # swapping domains is a config change, not a code change.
                for name, spec in extra.items():
                    url = spec.get("url")
                    if url:
                        self._sessions[str(name)] = await self._open_http_session(
                            stack,
                            self._expand(str(url)),
                            str(spec.get("transport") or "streamable-http"),
                        )
                        continue
                    command = spec.get("command")
                    if not command:
                        continue
                    args = [self._expand(str(value)) for value in spec.get("args") or []]
                    cwd = spec.get("cwd") or str(self.server_path.parent)
                    self._sessions[str(name)] = await self._open_stdio_session(
                        stack, self._expand(str(command)), args, self._expand(str(cwd))
                    )
            else:
                # Legacy fallback: single local domain server over stdio.
                primary = await self._open_stdio_session(
                    stack,
                    sys.executable,
                    [str(self.server_path)],
                    str(self.server_path.parent),
                )
                self._sessions["domain-primary"] = primary

            for session in self._sessions.values():
                listed = await session.list_tools()
                for tool in listed.tools:
                    self._tool_sessions.setdefault(tool.name, session)
        except BaseException:
            await stack.aclose()
            self._sessions = {}
            self._tool_sessions = {}
            self._llama_tools_cache = None
            raise

        self._stack = stack

    async def close(self) -> None:
        if self._stack is not None:
            await self._stack.aclose()
        self._stack = None
        self._sessions = {}
        self._tool_sessions = {}
        self._llama_tools_cache = None

    async def list_tools(self) -> list[Any]:
        tools: list[Any] = []
        for session in self._sessions.values():
            listed = await session.list_tools()
            tools.extend(listed.tools)
        return tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        session = self._tool_sessions.get(name)
        if session is None:
            raise RuntimeError(f"Unknown MCP tool {name!r}")

        result = await session.call_tool(name, arguments)
        is_error = getattr(result, "is_error", None)
        if is_error is None:
            is_error = getattr(result, "isError", False)
        if is_error:
            message = " ".join(block.text for block in result.content if hasattr(block, "text"))
            raise RuntimeError(message or f"MCP tool {name!r} failed")
        structured = getattr(result, "structured_content", None)
        if structured is None:
            structured = getattr(result, "structuredContent", None)
        if structured is not None:
            return json.dumps(structured, default=str)
        return "\n".join(block.text for block in result.content if hasattr(block, "text"))

    async def calculate_b_life(self, beta: float, eta: float, percentage: float) -> str:
        """Deprecated reliability convenience wrapper; prefer ``call_tool``."""
        return await self.call_tool(
            "calculate_b_life",
            {"beta": beta, "eta": eta, "percentage": percentage},
        )

    async def search_reliability_knowledge(self, query: str, max_results: int = 3) -> str:
        """Deprecated reliability convenience wrapper; prefer ``call_tool``."""
        return await self.call_tool(
            "search_reliability_knowledge",
            {"query": query, "max_results": max_results},
        )

    async def llama_tools(self) -> list[Any]:
        if self._llama_tools_cache is not None:
            return self._llama_tools_cache
        from llama_index.core.tools import FunctionTool

        tools: list[Any] = []
        for tool in await self.list_tools():
            tools.append(self._to_llama_tool(FunctionTool, tool))
        self._llama_tools_cache = tools
        return tools

    def _to_llama_tool(self, function_tool: Any, tool: Any) -> Any:
        name = str(tool.name)
        description = str(getattr(tool, "description", None) or name)
        schema = (
            getattr(tool, "input_schema", None)
            or getattr(tool, "inputSchema", None)
            or {
                "type": "object",
                "properties": {},
            }
        )
        model = _model_from_json_schema(name, schema)

        async def _fn(**kwargs: Any) -> str:
            return await self.call_tool(name, kwargs)

        _fn.__name__ = name
        _fn.__doc__ = description
        return function_tool.from_defaults(
            async_fn=_fn,
            name=name,
            description=description,
            fn_schema=model,
        )


def _annotation_for(spec: dict[str, Any]) -> Any:
    json_type = spec.get("type")
    if json_type == "array":
        items = spec.get("items") or {}
        inner = _annotation_for(items) if items else Any
        return list[inner]
    if isinstance(json_type, list) and json_type:
        return JSON_TYPE_MAP.get(json_type[0], Any)
    return JSON_TYPE_MAP.get(json_type, Any)


def _model_from_json_schema(name: str, schema: dict[str, Any]) -> type[BaseModel]:
    properties = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    fields: dict[str, Any] = {}
    for key, spec in properties.items():
        annotation = _annotation_for(spec if isinstance(spec, dict) else {})
        description = spec.get("description", "") if isinstance(spec, dict) else ""
        if key in required:
            fields[key] = (annotation, Field(..., description=description))
        else:
            default = spec.get("default") if isinstance(spec, dict) else None
            fields[key] = (annotation, Field(default, description=description))
    model_name = f"{''.join(part.title() for part in name.split('_'))}Input"
    return create_model(model_name, **fields)  # type: ignore[arg-type]


#: Back-compat alias — the client is domain-agnostic; new code should use
#: :class:`MultiMCPClient`.
ReliabilityMCPClient = MultiMCPClient
