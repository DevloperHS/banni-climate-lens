"""Security helpers: optional API token for state-changing endpoints, safe-name validation, security headers,
log redaction."""
from __future__ import annotations
import hmac
import logging
import re

from fastapi import Header, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from .config import get_settings

SAFE_NAME = re.compile(r"^[a-z0-9][a-z0-9_]{0,63}$")


def safe_name(value: str, what: str = "name") -> str:
    """Identifiers that become file-system path parts (region, variable key, season) must be plain [a-z0-9_]."""
    if not isinstance(value, str) or not SAFE_NAME.fullmatch(value):
        raise ValueError(f"invalid {what}: {value!r}")
    return value


def require_write(authorization: str | None = Header(default=None)) -> None:
    """FastAPI dependency for endpoints that change state or start expensive work.
    If GCL_API_TOKEN is set a matching `Authorization: Bearer <token>` header is required; otherwise the API is open
    (appropriate only on a trusted network). Comparison is constant-time."""
    token = get_settings().api_token
    if not token:
        return
    supplied = (authorization or "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(supplied.encode(), token.encode()):
        raise HTTPException(status_code=401, detail={"error": {"code": "unauthorized", "message": "A valid API token is required for this operation.", "details": None}},
                            headers={"WWW-Authenticate": "Bearer"})


# Restrictive policy for the app: scripts only from this origin (no inline/eval), network only to this origin, images from
# this origin plus the two map-tile hosts, no plugins, no framing, no base-tag or form hijacking. `style-src` keeps
# 'unsafe-inline' only because React/Recharts emit style attributes; it does not allow inline <script>.
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
       "img-src 'self' data: blob: https://tile.openstreetmap.org https://server.arcgisonline.com; font-src 'self'; connect-src 'self'; "
       "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'self'")
# Our own static pages (iframed by the React app) use one inline <script>; allow it only on these paths.
CSP_STATIC = CSP.replace("script-src 'self';", "script-src 'self' 'unsafe-inline';")
STATIC_PAGES = ("/overview/", "/report/", "/methodology/")
CSP_EXEMPT = ("/docs", "/redoc", "/openapi.json")       # Swagger UI loads scripts from a CDN and uses inline script


class SecurityHeaders(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        resp = await call_next(request)
        if not request.url.path.startswith(CSP_EXEMPT):
            resp.headers.setdefault("Content-Security-Policy", CSP_STATIC if request.url.path.startswith(STATIC_PAGES) else CSP)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        resp.headers.setdefault("Permissions-Policy", "geolocation=(), camera=(), microphone=()")
        if request.url.path.startswith("/api/"):
            resp.headers.setdefault("Cache-Control", "no-store") if "Cache-Control" not in resp.headers else None
        return resp


_REDACT = [
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]+"), r"\1[REDACTED]"),
    (re.compile(r'(?i)("?private_key(_id)?"?\s*[:=]\s*)("[^"]*"|\S+)'), r"\1[REDACTED]"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S), "[REDACTED KEY]"),
    (re.compile(r"(?i)(token|secret|password|api[_-]?key)=([^&\s]+)"), r"\1=[REDACTED]"),
]


def redact(text: str) -> str:
    for rx, rep in _REDACT:
        text = rx.sub(rep, text)
    return text


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = redact(record.getMessage())
            record.args = ()
        except Exception:
            pass
        return True


def safe_text(value: str, limit: int = 200) -> str:
    """Strip control characters/newlines from user-provided notes that end up in exports (header injection)."""
    return re.sub(r"[\x00-\x1f\x7f]+", " ", str(value))[:limit].strip()


def csv_cell(value) -> str:
    """Neutralise spreadsheet formula injection for any text cell we write to CSV."""
    s = safe_text(str(value), 500)
    return "'" + s if s[:1] in ("=", "+", "-", "@") and not _is_number(s) else s


def _is_number(s: str) -> bool:
    try:
        float(s)
        return True
    except ValueError:
        return False
