"""Persistent stdio client for the local reliability MCP server."""

import json
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class ReliabilityMCPClient:
    def __init__(self, server_path: Path | None = None) -> None:
        self.server_path = server_path or Path(__file__).with_name("mcp_server.py")
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None

    async def start(self) -> None:
        if self._session is not None:
            return

        stack = AsyncExitStack()
        try:
            read_stream, write_stream = await stack.enter_async_context(
                stdio_client(
                    StdioServerParameters(
                        command=sys.executable,
                        args=[str(self.server_path)],
                        cwd=str(self.server_path.parent),
                    )
                )
            )
            session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
            await session.initialize()
        except BaseException:
            await stack.aclose()
            raise

        self._stack = stack
        self._session = session

    async def close(self) -> None:
        if self._stack is not None:
            await self._stack.aclose()
        self._stack = None
        self._session = None

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        if self._session is None:
            raise RuntimeError("MCP client has not been started")

        result = await self._session.call_tool(name, arguments)
        if result.isError:
            message = " ".join(block.text for block in result.content if hasattr(block, "text"))
            raise RuntimeError(message or f"MCP tool {name!r} failed")
        if result.structuredContent is not None:
            return json.dumps(result.structuredContent, default=str)
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
