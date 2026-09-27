"""Generic FastAPI host — domain-agnostic, driven by the domain registry."""

from src.host.domain_registry import get_active_domain

__all__ = ["get_active_domain"]
