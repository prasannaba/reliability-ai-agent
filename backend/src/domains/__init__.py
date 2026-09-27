"""Pluggable domain MCP servers (reliability, physics, ...).

Each domain is a self-contained package with its own MCP ``server.py``,
``prompt.md`` system prompt, and ``domain.yaml`` manifest. The FastAPI host
never imports a domain directly — it discovers the active one through
``src.host.domain_registry`` (``ACTIVE_DOMAIN`` env var).
"""
