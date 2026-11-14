# Deployment

GlobalClimateLens is a **single-node** application: one FastAPI process (API + optional built frontend), a file-based data directory, and Earth Engine as the only external service.

**Verification status.** Verified here: clean-environment install and full test suite, production-mode launch (API and built UI served by one process, token enforced, headers, traversal probes), the strict Content-Security-Policy in a real browser (`npm run e2e:prod`), and the in-process rate limiter. **BLOCKED:** the Docker image build, container run, health check inside a container, volume persistence and image vulnerability scan (Docker is not installed on the development machine; nothing below about the container has been executed). **Not verified:** TLS/reverse-proxy setups, cloud hosting.

## 1. Without Docker (verified path)
```bash
python -m venv .venv && . .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
pip install -r backend/requirements.lock              # exact versions; or requirements.txt for ranges
(cd frontend && npm ci && npm run build)
export GCL_DATA_DIR=/var/lib/globalclimatelens GCL_STATIC_DIR=$PWD/frontend/dist \
       GCL_API_TOKEN="$(python -c 'import secrets;print(secrets.token_urlsafe(32))')" \
       GCL_LOG_JSON=true GCL_CORS_ORIGINS=https://climate.example.org
cd backend && uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 --proxy-headers
```
Open `http://127.0.0.1:8000/` (UI) - API docs at `/docs`.
**Use exactly one worker:** the job queue and result cache are in-process.

## 2. Docker (written, unbuilt)
```bash
cp .env.production.example .env.production      # edit: token, CORS origin, Earth Engine project/service account
mkdir -p secrets && cp /path/to/ee-key.json secrets/ee-key.json && chmod 600 secrets/ee-key.json
# uncomment the secrets volume line in docker-compose.yml
docker compose up -d --build
docker compose ps        # STATUS should become "healthy"
curl -s http://127.0.0.1:8000/api/health
```
Image: multi-stage (Node builds the UI; Python 3.12-slim runtime), non-root user, health check on `/api/health`, data in the `gcl_data` volume, `read_only` root filesystem with a tmpfs `/tmp`, `cap_drop: ALL`, `no-new-privileges`, port published on localhost only. If the build fails on `requirements.lock` (wheels differ by platform) the Dockerfile falls back to `requirements.txt`; please record the result of the first real build.

## 3. TLS, reverse proxy, access control
Terminate TLS in front (nginx / Caddy / a cloud load balancer). Example nginx:
```nginx
server { listen 443 ssl http2; server_name climate.example.org;
  client_max_body_size 6m;                              # uploads are capped at GCL_MAX_UPLOAD_MB (5) in the app too
  location / { proxy_pass http://127.0.0.1:8000; proxy_read_timeout 300s; proxy_set_header X-Forwarded-Proto $scheme; }
  add_header Strict-Transport-Security "max-age=31536000" always; }
limit_req_zone $binary_remote_addr zone=gcl:10m rate=10r/s;   # add `limit_req zone=gcl burst=20;` for /api/
```
`GCL_API_TOKEN` is **mandatory** for anything reachable beyond localhost; it protects job creation, uploads, deletions. Read endpoints are public by design (the data is not secret) - put the whole site behind SSO/basic auth if it must be private.

## 4. Configuration reference (`GCL_` prefix)
| Variable | Default | Meaning |
|---|---|---|
| `DATA_DIR` | `./data` | all runtime data |
| `STATIC_DIR` | unset | serve built frontend from the API process |
| `CORS_ORIGINS` | localhost dev | comma-separated exact origins |
| `API_TOKEN` | unset (open) | bearer token for state-changing endpoints |
| `LOG_JSON` | false | one JSON object per log line |
| `MAX_UPLOAD_MB` | 5 | upload cap |
| `MIN_COMPLETENESS` | 0.5 | a series with fewer valid months is **not stored** |
| `RATE_LIMIT_PER_MIN` | 600 | per-client read limit (heavy endpoints /6, writes /4); 429 + `Retry-After`; 0 disables. Relative `DATA_DIR` values resolve against the repository root |
| `EE_PROJECT`, `EE_SERVICE_ACCOUNT`, `EE_PRIVATE_KEY_FILE` | unset | Earth Engine (see SETUP.md) |

## 5. Health, logging, monitoring
- `GET /api/health` (also `HEAD`): status (`ok`/`degraded`), version, data-dir writability, free disk, active jobs, whether write-auth and Earth Engine are configured. Use it for load balancer and container health checks. `GET /api/health/earthengine?probe=true` performs a real Earth Engine call (slow; do not poll).
- Logs: stdout; request line = method, path, status, latency (no query strings); secrets are redacted. Job logs (with tracebacks) in `data/cache/job_logs/<id>.log`, readable via `GET /api/datasets/jobs/<id>/log`.
- Alert on: `status != ok`, free disk below 1 GB, jobs stuck `running` for hours (cancel and retry).

## 6. Data, backups, restore
What matters: `data/processed/` (series, rasters, field data, groundwater uploads) and `data/raw/` (timestamped raw extractions). Disposable: `data/cache/`, `data/sample/`.
```bash
scripts/backup.sh /var/lib/globalclimatelens /backups        # tar.gz + SHA-256; Windows: scripts\backup.ps1
scripts/restore-check.sh /backups/globalclimatelens_<stamp>.tar.gz
```
Restore = extract into `GCL_DATA_DIR` while the service is stopped. Schedule daily with cron/Task Scheduler; keep copies off the host. Backups contain provenance for every series, so a restored system remains auditable.

## 7. Upgrades
Stop the service (running jobs become `interrupted` and can be retried), back up, deploy the new image/code, start. Partial `*.tmp` files left by an interrupted write are removed on start-up. Re-run `pip-audit` / `npm audit` before each release.

## 8. Pipeline operation
Jobs run in a single background worker: queued → running → completed / completed_with_errors / failed / cancelled / interrupted. Cancel takes effect between Earth Engine round-trips; retry re-runs only unfinished tasks. A series is stored only after extraction **and** schema/completeness validation succeed, and every write is atomic, so interrupted or failed jobs leave no partial results.

## 9. Known limits
Single node, single worker, file store; no multi-user accounts; no rate limiting in the app; Earth Engine quotas apply (non-commercial tier).
