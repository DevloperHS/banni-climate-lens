# syntax=docker/dockerfile:1
# --- 1. build the frontend
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- 2. runtime: API + built frontend in one process
FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    GCL_DATA_DIR=/data GCL_STATIC_DIR=/app/static GCL_LOG_JSON=true
RUN useradd --create-home --uid 10001 gcl && mkdir -p /data /app/static && chown -R gcl:gcl /data
WORKDIR /app
COPY backend/requirements.txt backend/requirements.lock ./
# the lock file (exact versions) is preferred; fall back to the ranges if a wheel is unavailable for this platform
RUN pip install -r requirements.lock || pip install -r requirements.txt
COPY backend/app ./app
COPY --from=web /web/dist /app/static
USER gcl
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; r=urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=4); sys.exit(0 if r.status==200 else 1)"
# one worker: the job queue and result cache are in-process
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers"]
