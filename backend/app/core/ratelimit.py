"""Small in-process rate limiter (sliding window per client) for a single-node deployment.

Three buckets: `heavy` (PDF, pixel statistics, exports), `write` (state-changing calls) and `read` (everything else under
/api). Limits are generous for one analyst and stop a runaway client. Behind a reverse proxy use `--proxy-headers` so the
real client address is seen. For internet-facing use ALSO rate-limit at the proxy (see DEPLOYMENT.md)."""
from __future__ import annotations
import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from .config import get_settings

HEAVY_PREFIXES = ("/api/reports/pdf", "/api/spatial/pixel-trend", "/api/spatial/export", "/api/spatial/evergreen", "/api/spatial/difference",
                  "/api/spatial/trend-agreement", "/api/statistics/compare", "/api/statistics/rainfall-adjusted")


def bucket_for(method: str, path: str) -> str:
    if method in ("POST", "DELETE"):
        return "write"
    return "heavy" if path.startswith(HEAVY_PREFIXES) else "read"


class RateLimiter(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.hits: dict[tuple[str, str], deque] = defaultdict(deque)

    async def dispatch(self, request, call_next):
        s = get_settings()
        if not request.url.path.startswith("/api/") or request.url.path == "/api/health" or s.rate_limit_per_min <= 0:
            return await call_next(request)
        b = bucket_for(request.method, request.url.path)
        limit = {"read": s.rate_limit_per_min, "heavy": max(5, s.rate_limit_per_min // 6), "write": max(5, s.rate_limit_per_min // 4)}[b]
        client = request.client.host if request.client else "unknown"
        now = time.monotonic()
        q = self.hits[(client, b)]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= limit:
            retry = int(60 - (now - q[0])) + 1
            return JSONResponse(status_code=429, headers={"Retry-After": str(retry)},
                                content={"error": {"code": "rate_limited", "message": f"Too many {b} requests; retry in {retry} s.", "details": None}})
        q.append(now)
        if len(self.hits) > 5000:                       # bound memory
            self.hits.clear()
        return await call_next(request)
