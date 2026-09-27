"""Shared, domain-agnostic backend utilities (credentials, rate limits, math)."""

from src.common.credential_store import (
    delete_api_key,
    get_api_key,
    has_api_key,
    migrate_legacy_key,
    set_api_key,
)
from src.common.markdown_math import patch_markdown_math
from src.common.rate_limit import RateLimiter, RateLimitMiddleware

__all__ = [
    "RateLimiter",
    "RateLimitMiddleware",
    "delete_api_key",
    "get_api_key",
    "has_api_key",
    "migrate_legacy_key",
    "patch_markdown_math",
    "set_api_key",
]
