"""Persistent stdio client for local reliability MCP servers."""

from __future__ import annotations

import json
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import BaseModel, Field, create_model

BACKEND_DIR = Path(__file__).resolve().parent
DEFAULT_SERVERS_CONFIG = BACKEND_DIR / "mcp_servers.json"


JSON_TYPE_MAP = {
    "string": str,
    "number": float,
    "integer": int,
    "boolean": bool,
    "array": list,
    "object": dict,
}


class ReliabilityMCPClient:
    def __init__(self, server_path: Path | None = None, extra_config_path: Path | None = None) -> None:
        self.server_path = server_path or Path(__file__).with_name("mcp_server.py")
        self.extra_config_path = extra_config_path or DEFAULT_SERVERS_CONFIG
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

    async def _open_session(self, stack: AsyncExitStack, command: str, args: list[str], cwd: str | None) -> ClientSession:
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

    async def start(self) -> None:
        if self._sessions:
            return

        stack = AsyncExitStack()
        try:
            primary = await self._open_session(
                stack,
                sys.executable,
                [str(self.server_path)],
                str(self.server_path.parent),
            )
            self._sessions["reliability-engineering"] = primary

            for name, spec in self._extra_servers().items():
                command = spec.get("command")
                if not command:
                    continue
                args = [str(value) for value in spec.get("args") or []]
                cwd = spec.get("cwd") or str(self.server_path.parent)
                self._sessions[str(name)] = await self._open_session(stack, str(command), args, str(cwd))

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
        """Calculate Weibull B-life for a failure percentile between 0 and 100."""
        return await self.call_tool(
            "calculate_b_life",
            {"beta": beta, "eta": eta, "percentage": percentage},
        )

    async def analyze_weibull(self, failure_times: list[float], title: str = "Weibull Probability Plot") -> str:
        """Fit Weibull failure data, create a plot, and return fit statistics."""
        return await self.call_tool("analyze_weibull", {"failure_times": failure_times, "title": title})

    async def search_reliability_knowledge(self, query: str, max_results: int = 3) -> str:
        """Search local reliability and organizational documentation."""
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
        schema = getattr(tool, "input_schema", None) or getattr(tool, "inputSchema", None) or {
            "type": "object",
            "properties": {},
        }
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
