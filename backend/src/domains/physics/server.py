"""Physics-engineering MCP server — proves the host is domain-agnostic.

Same shape as the reliability server: tool implementations in ``tools/``,
``register(mcp)`` plugins in ``plugins/``, prompt in ``prompt.md``, manifest
in ``domain.yaml``. Serve it standalone over HTTP for external hosts::

    python -m src.domains.physics.server --transport streamable-http --port 8002

then point the FastAPI host at it with ``ACTIVE_DOMAIN=physics`` (see
``backend/config/mcp_servers.physics.json``) — no host code changes.
"""

from __future__ import annotations

import argparse
import importlib
import os
import pkgutil
import sys
from pathlib import Path
from typing import Any


def _bootstrap_sys_path() -> None:
    """Make ``src.*`` importable however this file is launched.

    The host spawns this file as ``python .../physics/server.py`` with
    ``cwd=backend/`` — the script directory alone is not enough for absolute
    ``src.*`` imports, and ``cwd`` is not on ``sys.path`` for script runs.
    """
    backend_dir = Path(__file__).resolve().parents[3]
    for candidate in (str(backend_dir.parent), str(backend_dir)):
        if candidate not in sys.path:
            sys.path.insert(0, candidate)


_bootstrap_sys_path()

from mcp.server.mcpserver import MCPServer  # noqa: E402

from src.domains.physics.tools import kinematics as _kinematics  # noqa: E402
from src.domains.physics.tools import knowledge_tool as _knowledge  # noqa: E402

mcp = MCPServer("physics-engineering")


def load_plugins(server: Any) -> None:
    """Load ``register(mcp)`` hooks from this domain's ``plugins/`` package."""
    import src.domains.physics.plugins as plugins

    prefix = plugins.__name__ + "."
    for module_info in pkgutil.iter_modules(plugins.__path__):
        if module_info.name.startswith("_"):
            continue
        module = importlib.import_module(prefix + module_info.name)
        register = getattr(module, "register", None)
        if callable(register):
            register(server)


@mcp.tool()
def projectile_motion(v0: float, angle_deg: float, g: float = 9.81) -> dict[str, float]:
    """Projectile range/height/flight-time for launch speed v0 (m/s) at angle_deg.

    Vacuum, flat ground, no drag.
    """
    return _kinematics.projectile_motion(v0, angle_deg, g)


@mcp.tool()
def kinetic_energy(mass_kg: float, velocity_ms: float) -> dict[str, float]:
    """Classical kinetic energy (J) for mass_kg at velocity_ms."""
    return _kinematics.kinetic_energy(mass_kg, velocity_ms)


@mcp.tool()
def search_physics_knowledge(query: str, max_results: int = 3) -> dict[str, Any]:
    """Hybrid-search local physics notes (Markdown, text, PDF, Word, PowerPoint)."""
    return _knowledge.search_knowledge(query, max_results)


load_plugins(mcp)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Physics MCP server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default=os.getenv("MCP_TRANSPORT", "stdio"),
        help="MCP transport (default: stdio; use sse/streamable-http for Open Web UI etc.)",
    )
    parser.add_argument("--host", default=os.getenv("MCP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("MCP_PORT", "8002")))
    parser.add_argument(
        "--path",
        default=os.getenv("MCP_PATH", "/mcp"),
        help="HTTP mount path for the streamable-http transport",
    )
    return parser.parse_args(argv)


def run(
    transport: str = "stdio", host: str = "127.0.0.1", port: int = 8002, path: str = "/mcp"
) -> None:
    if transport == "stdio":
        mcp.run(transport="stdio")
    elif transport == "sse":
        # Clients must use the FULL path below — bare http://host:port/ 404s.
        print(f"Physics MCP (SSE): http://{host}:{port}{path}", flush=True)
        mcp.run(transport="sse", host=host, port=port, sse_path=path)
    else:
        # Clients must use the FULL path below — bare http://host:port/ 404s.
        print(f"Physics MCP (streamable HTTP): http://{host}:{port}{path}", flush=True)
        mcp.run(transport="streamable-http", host=host, port=port, streamable_http_path=path)


def ensure_repo_root_on_path() -> None:
    """Allow ``python backend/src/domains/physics/server.py`` direct launches."""
    root = Path(__file__).resolve().parents[4]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


if __name__ == "__main__":
    ensure_repo_root_on_path()
    args = parse_args()
    run(transport=args.transport, host=args.host, port=args.port, path=args.path)
