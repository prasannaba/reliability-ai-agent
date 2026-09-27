"""Reliability-engineering MCP server — standalone and pluggable.

Tool implementations live in ``tools/``; this module only registers them on
the MCP server, loads ``plugins/``, and selects the transport.

Transports (all via the installed ``mcp`` package):

- ``stdio`` (default) — spawned by the FastAPI host for local dev, or by any
  MCP-compatible client.
- ``sse`` / ``streamable-http`` — long-running HTTP server for external
  hosts (Open Web UI, Unsloth Studio, ...), e.g.::

      python -m src.domains.reliability.server --transport streamable-http --port 8001
      # tools available at http://localhost:8001/mcp

Run from ``backend/`` so ``src.*`` imports resolve::

    python -m src.domains.reliability.server --transport streamable-http --port 8001
    # tools available at http://localhost:8001/mcp
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import pkgutil
import sys
from pathlib import Path
from typing import Any


def _bootstrap_sys_path() -> None:
    """Make ``src.*`` importable however this file is launched.

    The host spawns this file as ``python .../reliability/server.py`` with
    ``cwd=backend/`` — the script directory alone is not enough for absolute
    ``src.*`` imports, and ``cwd`` is not on ``sys.path`` for script runs.
    """
    backend_dir = Path(__file__).resolve().parents[3]
    for candidate in (str(backend_dir.parent), str(backend_dir)):
        if candidate not in sys.path:
            sys.path.insert(0, candidate)


_bootstrap_sys_path()

from mcp.server.mcpserver import (  # noqa: E402
    Image,
    MCPServer,
)
from mcp_types import CallToolResult, ContentBlock, TextContent  # noqa: E402

from src.domains.reliability.tools import blife as _blife  # noqa: E402
from src.domains.reliability.tools import knowledge_tool as _knowledge  # noqa: E402
from src.domains.reliability.tools import report as _report  # noqa: E402
from src.domains.reliability.tools import weibull as _weibull  # noqa: E402
from src.domains.reliability.tools._common import STATIC_DIR  # noqa: E402

mcp = MCPServer("reliability-engineering")


def _plot_image_block(filename: str) -> ContentBlock | None:
    """Read a plot PNG from the static dir as an MCP image block (or None)."""
    name = Path(filename).name
    if not name or not name.endswith(".png"):
        return None
    path = STATIC_DIR / name
    if not path.is_file():
        return None
    try:
        return Image(path=path).to_image_content()
    except OSError:
        return None


def load_plugins(server: Any) -> None:
    """Load ``register(mcp)`` hooks from this domain's ``plugins/`` package."""
    import src.domains.reliability.plugins as plugins

    prefix = plugins.__name__ + "."
    for module_info in pkgutil.iter_modules(plugins.__path__):
        if module_info.name.startswith("_"):
            continue
        module = importlib.import_module(prefix + module_info.name)
        register = getattr(module, "register", None)
        if callable(register):
            register(server)


@mcp.tool()
def calculate_b_life(beta: float, eta: float, percentage: float) -> int:
    """Calculate Weibull B-life for a failure percentile between 0 and 100."""
    return _blife.calculate_b_life(beta, eta, percentage)


@mcp.tool()
def analyze_weibull(
    failure_times: list[float],
    title: str = "Weibull Probability Plot",
    censored_times: list[float] | None = None,
    method: str = "rry",
    confidence: float = 0.9,
) -> CallToolResult:
    """Fit 2-parameter Weibull data, plot probability paper, and return statistics.

    Use censored_times for right-censored suspensions. method is 'rry' (default,
    median ranks + rank regression on Y) or 'mle'. confidence is the two-sided
    bootstrap interval on the line and on B10/B20 (for example 0.9).

    Returns the stats dict as structured content plus the plot PNG as an MCP
    image block, so generic clients (Unsloth Studio, Claude Desktop, VS Code)
    render the graph instead of just JSON.
    """
    result = _weibull.analyze_weibull(
        failure_times,
        title=title,
        censored_times=censored_times,
        method=method,
        confidence=confidence,
    )
    content: list[ContentBlock] = [
        TextContent(type="text", text=json.dumps(result, indent=2, default=str))
    ]
    image = _plot_image_block(str(result.get("file") or ""))
    if image is not None:
        content.append(image)
    return CallToolResult(content=content, structured_content=result)


@mcp.tool()
def export_reliability_report(
    failure_times: list[float],
    question: str = "",
    censored_times: list[float] | None = None,
    method: str = "rry",
    confidence: float = 0.9,
    warranty_hours: float | None = None,
    knowledge_query: str | None = None,
) -> CallToolResult:
    """Build a one-page markdown report from tool-computed Weibull results and optional KB cites.

    Returns the report payload as structured content, the markdown as text,
    and the plot PNG as an MCP image block for generic clients.
    """
    result = _report.export_reliability_report(
        failure_times,
        question=question,
        censored_times=censored_times,
        method=method,
        confidence=confidence,
        warranty_hours=warranty_hours,
        knowledge_query=knowledge_query,
    )
    content: list[ContentBlock] = [TextContent(type="text", text=str(result.get("markdown") or ""))]
    analysis = result.get("analysis") or {}
    image = _plot_image_block(str(analysis.get("file") or ""))
    if image is not None:
        content.append(image)
    return CallToolResult(content=content, structured_content=result)


@mcp.tool()
def search_reliability_knowledge(query: str, max_results: int = 3) -> dict[str, Any]:
    """Hybrid-search local Markdown, text, PDF, Word, and PowerPoint documents."""
    return _knowledge.search_knowledge(query, max_results)


load_plugins(mcp)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reliability MCP server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default=os.getenv("MCP_TRANSPORT", "stdio"),
        help="MCP transport (default: stdio; use sse/streamable-http for Open Web UI etc.)",
    )
    parser.add_argument("--host", default=os.getenv("MCP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("MCP_PORT", "8001")))
    parser.add_argument(
        "--path",
        default=os.getenv("MCP_PATH", "/mcp"),
        help="HTTP mount path for the streamable-http transport",
    )
    return parser.parse_args(argv)


def run(
    transport: str = "stdio", host: str = "127.0.0.1", port: int = 8001, path: str = "/mcp"
) -> None:
    if transport == "stdio":
        mcp.run(transport="stdio")
    elif transport == "sse":
        # Clients must use the FULL path below — bare http://host:port/ 404s.
        print(f"Reliability MCP (SSE): http://{host}:{port}{path}", flush=True)
        mcp.run(transport="sse", host=host, port=port, sse_path=path)
    else:
        # Clients must use the FULL path below — bare http://host:port/ 404s.
        print(f"Reliability MCP (streamable HTTP): http://{host}:{port}{path}", flush=True)
        mcp.run(transport="streamable-http", host=host, port=port, streamable_http_path=path)


def ensure_repo_root_on_path() -> None:
    """Allow ``python backend/src/domains/reliability/server.py`` direct launches."""
    root = Path(__file__).resolve().parents[4]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


if __name__ == "__main__":
    ensure_repo_root_on_path()
    args = parse_args()
    run(transport=args.transport, host=args.host, port=args.port, path=args.path)
