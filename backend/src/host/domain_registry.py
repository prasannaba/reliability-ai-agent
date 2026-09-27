"""Domain registry: resolve the active pluggable domain without code changes.

The FastAPI host never imports ``src.domains.*`` directly. It asks this
module which domain is active (``ACTIVE_DOMAIN`` env var, default
``reliability``) and receives everything it needs:

- ``system_prompt`` — loaded from ``domains/<name>/prompt.md``
- ``servers_config`` — ``backend/config/mcp_servers.<name>.json``
- knowledge-base locations (collection, kb dir, index dir) from ``domain.yaml``

Adding a domain (e.g. physics) = new folder under ``src/domains/`` + new
JSON in ``backend/config/`` + ``ACTIVE_DOMAIN=<name>``. No host edits.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
DOMAINS_DIR = BACKEND_DIR / "src" / "domains"
CONFIG_DIR = BACKEND_DIR / "config"

DEFAULT_DOMAIN = "reliability"

_GENERIC_FALLBACK_PROMPT = (
    "You are a helpful engineering assistant. "
    "Never invent numeric results: always call the available MCP tools for "
    "computations and cite tool output. "
    "Use LaTeX for mathematics and answer in technically rigorous Markdown."
)


def active_domain_name() -> str:
    """Explicitly selected domain only — defaults to reliability, never guesses."""
    return (os.getenv("ACTIVE_DOMAIN") or DEFAULT_DOMAIN).strip().lower() or DEFAULT_DOMAIN


def domain_dir(name: str) -> Path:
    return DOMAINS_DIR / name


def servers_config_path(name: str | None = None) -> Path:
    """MCP server list for a domain; ``MCP_SERVERS_CONFIG`` env wins when set."""
    override = (os.getenv("MCP_SERVERS_CONFIG") or "").strip()
    if override:
        return Path(override)
    return CONFIG_DIR / f"mcp_servers.{name or active_domain_name()}.json"


def _parse_manifest(path: Path) -> dict[str, str]:
    """Minimal flat ``key: value`` reader for ``domain.yaml`` (no dep needed)."""
    values: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return values
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        key, _, value = stripped.partition(":")
        values[key.strip()] = value.strip().strip("\"'")
    return values


@dataclass
class DomainInfo:
    """Everything the generic host needs to serve one domain."""

    name: str
    title: str
    mcp_server: str
    collection: str
    knowledge_dir: Path
    index_dir: Path
    system_prompt: str
    servers_config: Path
    server_module: str
    extra: dict[str, str] = field(default_factory=dict)


def get_active_domain(name: str | None = None) -> DomainInfo:
    """Load the domain manifest + prompt. Unknown names fall back gracefully."""
    domain = (name or active_domain_name()).strip().lower() or DEFAULT_DOMAIN
    manifest = _parse_manifest(domain_dir(domain) / "domain.yaml")
    prompt_file = domain_dir(domain) / "prompt.md"
    try:
        system_prompt = prompt_file.read_text(encoding="utf-8").strip()
    except OSError:
        system_prompt = ""
    collection = manifest.get("collection") or f"{domain}_knowledge"
    knowledge_dirname = manifest.get("knowledge_dir") or "knowledge-base"
    index_dirname = manifest.get("index_dir") or ".rag"
    return DomainInfo(
        name=domain,
        title=manifest.get("title") or f"{domain.title()} Copilot",
        mcp_server=manifest.get("mcp_server") or f"{domain}-engineering",
        collection=collection,
        knowledge_dir=(BACKEND_DIR.parent / knowledge_dirname)
        if knowledge_dirname.startswith("../")
        else (
            BACKEND_DIR / knowledge_dirname
            if knowledge_dirname != "knowledge-base"
            else BACKEND_DIR.parent / "knowledge-base"
        ),
        index_dir=BACKEND_DIR / index_dirname,
        system_prompt=system_prompt or _GENERIC_FALLBACK_PROMPT,
        servers_config=servers_config_path(domain),
        server_module=f"src.domains.{domain}.server",
        extra=manifest,
    )


def list_domains() -> list[str]:
    """Domain names available under ``src/domains/`` (have a server.py)."""
    if not DOMAINS_DIR.is_dir():
        return [DEFAULT_DOMAIN]
    return sorted(path.name for path in DOMAINS_DIR.iterdir() if (path / "server.py").is_file())
