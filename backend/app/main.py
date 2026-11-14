import json
import logging
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .core.config import get_settings
from .core.ratelimit import RateLimiter
from .core.security import RedactingFilter, SecurityHeaders
from .services import AppError
from .gee.client import EarthEngineUnavailable
from .routers.core_routes import health, regions, datasets
from .routers.variables import vegetation, rainfall, temperature, water, landcover
from .routers.analysis import statistics, spatial
from .routers.reports import reports
from .routers.extra import salinity, spatial2, stats2
from .routers.dashboards import dashboards

VERSION = "1.0.0"
settings = get_settings()


class JsonFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({"t": self.formatTime(record), "level": record.levelname, "logger": record.name, "msg": record.getMessage()})


def _setup_logging():
    h = logging.StreamHandler()
    h.setFormatter(JsonFormatter() if settings.log_json else logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    h.addFilter(RedactingFilter())
    root = logging.getLogger()
    root.handlers = [h]
    root.setLevel(logging.INFO)


_setup_logging()
log = logging.getLogger("gcl.api")

app = FastAPI(title="GlobalClimateLens API", version=VERSION,
              description="Earth-observation analytics. Every result carries provenance in `meta`; "
                          "`meta.synthetic=true` marks synthetic sample data, which is never real observation. "
                          "State-changing endpoints require `Authorization: Bearer <GCL_API_TOKEN>` when a token is configured.")
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(RateLimiter)
app.add_middleware(SecurityHeaders)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_list, allow_methods=["GET", "POST", "DELETE"],
                   allow_headers=["Authorization", "Content-Type"], allow_credentials=False, max_age=600)

for r in (health, regions, datasets, vegetation, rainfall, temperature, water, landcover, salinity, statistics, stats2, spatial, spatial2, reports, dashboards):
    app.include_router(r)


@app.middleware("http")
async def timing(request: Request, call_next):
    t = time.perf_counter()
    resp = await call_next(request)
    log.info("%s %s -> %s (%.0f ms)", request.method, request.url.path, resp.status_code, (time.perf_counter() - t) * 1000)   # path only: no query strings
    return resp


def _err(status, code, message, details=None, headers=None):
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message, "details": details}}, headers=headers)


@app.exception_handler(AppError)
async def app_error(_, e: AppError):
    return _err(e.status, e.code, e.message)


@app.exception_handler(EarthEngineUnavailable)
async def ee_error(_, e):
    return _err(503, "earth_engine_unavailable", str(e))


@app.exception_handler(StarletteHTTPException)
async def http_error(_, e: StarletteHTTPException):
    if isinstance(e.detail, dict) and "error" in e.detail:
        return JSONResponse(status_code=e.status_code, content=e.detail, headers=getattr(e, "headers", None))
    return _err(e.status_code, "http_error", str(e.detail))


@app.exception_handler(RequestValidationError)
async def validation_error(_, e: RequestValidationError):
    return _err(422, "validation_error", "Invalid request parameters.", [{"loc": x["loc"], "msg": x["msg"]} for x in e.errors()])


@app.exception_handler(ValueError)
async def value_error(_, e: ValueError):
    return _err(422, "invalid_input", str(e))


@app.exception_handler(Exception)
async def unhandled(_, e: Exception):
    log.exception("unhandled error")
    return _err(500, "internal_error", "Internal error. See server logs.")       # no exception text leaked to clients


# Optional: serve the built frontend from the same process (Docker / single node). API routes keep priority.
if settings.static_dir and Path(settings.static_dir).is_dir():
    _static = Path(settings.static_dir).resolve()
    app.mount("/assets", StaticFiles(directory=_static / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        if path.startswith("api/"):
            return _err(404, "not_found", "Unknown API route")
        f = (_static / path).resolve()
        if path and f.is_file() and _static in f.parents:      # path-traversal safe
            return FileResponse(f)
        return FileResponse(_static / "index.html")
