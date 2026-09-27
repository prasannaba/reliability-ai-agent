"""In-memory sliding-window rate limiting for /api/*.

Scope (by design, single-file):
- Per-client-IP buckets; no shared state, so each uvicorn worker enforces
  independently. Good enough for a single-user app and small cloud deploys.
  For large multi-user / multi-replica deployments, enforce limits at the
  ingress / API gateway (Azure Front Door, Application Gateway) instead —
  this middleware is defense-in-depth, not the perimeter.
- Two scopes: `api` (all /api/ traffic, generous) and `sensitive`
  (PUT /api/llm/config, POST /api/llm/test, DELETE /api/llm/secret,
  POST /api/knowledge/upload — the SSRF/secret-mutation surface).
- Never trust X-Forwarded-For here (client-spoofable); keying uses the direct
  peer IP. Behind a proxy the granularity degrades to the proxy IP — set
  limits at the proxy in that case.
"""

from __future__ import annotations

import collections
import os
import time
from collections.abc import Callable

from starlette.types import ASGIApp, Receive, Scope, Send


class RateLimiter:
    """Sliding-window counter. `check` returns (allowed, retry_after_secs)."""

    def __init__(
        self,
        max_requests: int,
        window_seconds: float = 60.0,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.max_requests = max(1, max_requests)
        self.window = max(1.0, window_seconds)
        self._clock = clock or time.monotonic
        self._hits: dict[str, collections.deque[float]] = {}

    def check(self, key: str) -> tuple[bool, float]:
        now = self._clock()
        cutoff = now - self.window
        bucket = self._hits.get(key)
        if bucket is None:
            bucket = self._hits[key] = collections.deque()
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        if len(bucket) >= self.max_requests:
            retry = max(0.0, bucket[0] + self.window - now)
            return False, retry
        bucket.append(now)
        # Opportunistic cleanup so idle IPs don't accumulate forever.
        if len(self._hits) > 4096:
            stale = [k for k, b in self._hits.items() if not b or b[-1] <= cutoff]
            for k in stale[:1024]:
                del self._hits[k]
        return True, 0.0

    def reset(self) -> None:
        self._hits.clear()


_SENSITIVE_ROUTES = frozenset(
    {
        ("PUT", "/api/llm/config"),
        ("POST", "/api/llm/test"),
        ("DELETE", "/api/llm/secret"),
        ("POST", "/api/knowledge/upload"),
    }
)


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


class RateLimitMiddleware:
    """ASGI middleware (no body buffering — safe in front of SSE streams)."""

    def __init__(
        self,
        app: ASGIApp,
        api: RateLimiter | None = None,
        sensitive: RateLimiter | None = None,
    ) -> None:
        self.app = app
        self.api = api or RateLimiter(_env_int("RATE_LIMIT_API_PER_MIN", 120))
        self.sensitive = sensitive or RateLimiter(
            _env_int("RATE_LIMIT_SENSITIVE_PER_MIN", 10)
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope.get("path", "").startswith("/api/"):
            await self.app(scope, receive, send)
            return
        client = scope.get("client")
        ip = client[0] if client else "unknown"
        allowed, retry_after = self.api.check(f"api:{ip}")
        if allowed and (scope.get("method"), scope.get("path")) in _SENSITIVE_ROUTES:
            allowed, retry_after = self.sensitive.check(f"sensitive:{ip}")
        if allowed:
            await self.app(scope, receive, send)
            return
        body = b'{"detail":"Rate limit exceeded. Try again shortly."}'
        headers = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
            (b"retry-after", str(max(1, int(retry_after))).encode()),
        ]
        await send({"type": "http.response.start", "status": 429, "headers": headers})
        await send({"type": "http.response.body", "body": body})

    def reset(self) -> None:
        self.api.reset()
        self.sensitive.reset()
