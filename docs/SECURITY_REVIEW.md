# Security review

Scope: the repository as of the final phase (backend, frontend, deployment assets). Method: code review of every endpoint, automated tests of each control below, dependency audits (`pip-audit`, `npm audit`), and a live probe of a production-style launch (SPA + API in one process, token set). Findings marked **Fixed** were found during the review and corrected.

## Summary
| # | Area | Finding | Status |
|---|---|---|---|
| 1 | Secrets | No secret is stored in the repo. Credentials are read from env vars / a key file path; `.env*`, `secrets/`, key files and `data/` are git-ignored; a pattern scan of the tree found no private keys or API keys. | OK (scan re-run in final audit) |
| 2 | Authentication | Initially **no authentication at all**: anyone who could reach the API could start Earth Engine jobs, upload files and delete data. | **Fixed**: optional `GCL_API_TOKEN` guards every state-changing route (jobs, cancel, retry, sample, uploads, ground truth, field EC); constant-time comparison; 401 envelope with `WWW-Authenticate`. Reads stay open by design. **Residual:** with no token set the API is open - acceptable only on a trusted network. No per-user accounts or roles. |
| 3 | Path traversal | Region, variable and season are interpolated into file paths. Region/variable were checked against registries, but the store functions themselves did not enforce it. | **Fixed**: `safe_name()` (`^[a-z0-9][a-z0-9_]{0,63}$`) enforced inside every path builder; `Literal` types on query parameters; client filenames are never used as paths. Tests: encoded/double-encoded `../`, backslashes, absolute-style names. |
| 4 | Static file serving | The SPA catch-all could in principle expose files if the path were not confined. | OK: resolved path must be a file **inside** `dist` (`_static in f.parents`); verified with 12 traversal variants in a unit test and a live probe (HTML or 404, never source). |
| 5 | Upload handling | Single endpoint family accepting CSV: size, type and content were only loosely checked; user-supplied note flowed into exports. | **Fixed**: chunked read with hard cap (`GCL_MAX_UPLOAD_MB`, default 5; 413), NUL-byte/binary rejection, row caps, strict column and range validation, well IDs sanitised to `[A-Za-z0-9_.-]`, notes stripped of control characters (header injection) and truncated; uploaded files are parsed, never stored verbatim or executed. |
| 6 | CSV export / formula injection | Exports contain numeric data plus catalogue text; the only user-controlled text was the upload note. | OK after fix 5; `csv_cell()` helper neutralises leading `= + - @` for any future text cell. |
| 7 | CORS | `allow_headers=["*"]`, methods incl. all verbs. | **Fixed**: origins from `GCL_CORS_ORIGINS` only, methods GET/POST/DELETE, headers `Authorization, Content-Type`, no credentials. Verified: foreign origin gets no ACAO header. |
| 8 | Security headers | None. | **Fixed**: `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Permissions-Policy`, `Cache-Control: no-store` on API. **Content-Security-Policy added** (see below). HSTS is not set (belongs on the TLS terminator). |
| 9 | Error disclosure | Unhandled exceptions returned `ExcName: message` to the client. | **Fixed**: generic message to clients, details only in server logs. |
| 10 | Logging | Request log used path only (good); Earth Engine errors may include project IDs; tracebacks may contain paths. | **Fixed/Added**: `RedactingFilter` on all handlers (bearer tokens, `private_key`, PEM blocks, `token=`/`secret=`/`password=`/`api_key=`); job logs are redacted before writing; tests cover it. Query strings are not logged. |
| 11 | Denial of service | Expensive endpoints (pixel trends, PDF) had no rate limits. | **Fixed (in-process)**: sliding-window limiter per client, three buckets (read 600/min default; heavy = /6; write = /4; `GCL_RATE_LIMIT_PER_MIN`, 0 disables), 429 + `Retry-After`, `/api/health` exempt; results cached; upload/row caps; single job worker. **Residual:** per-process, per-address only; also rate-limit at the reverse proxy for public deployments. |
| 12 | Dependencies (Python) | `pip-audit`: no known vulnerabilities in application dependencies. Only `pip` itself (tooling) has an advisory (fix: pip 26.2). | OK / update pip in build images |
| 13 | Dependencies (JS) | `npm audit` initially reported 8 (2 moderate in production: `react-router` open redirect via backslash in `<Link>`/`useNavigate`, and an SSR hydration issue; 6 dev-only incl. a critical in `tinypool`). | **Fixed**: `react-router-dom` 7.18.5, `vitest` 5.1; `npm audit` = **0 vulnerabilities**; all tests re-run. |
| 14 | Container | Not built here (Docker unavailable). Dockerfile drops to a non-root user (uid 10001), compose sets `read_only`, `cap_drop: ALL`, `no-new-privileges`, localhost-only port. | **Unverified** (see FINAL_COMPLETION_REPORT) |
| 15 | Earth Engine credentials | Service-account key is a file path; never read by the browser; never logged. Compose mounts it read-only. | OK |
| 16 | Client storage | Region/period/theme in `localStorage`; the optional API token only in `sessionStorage` (cleared when the tab closes). | OK. XSS would still expose the token: there is no user-generated HTML anywhere (React escapes by default; no `dangerouslySetInnerHTML`). |
| 17 | SSRF | The backend fetches from Earth Engine (SDK) and the Earth Engine download URL it is given; no user-supplied URLs are fetched. | OK |
| 18 | Metadata verification tool | `verify-metadata` makes outbound HTTPS requests to a fixed Google host. | OK |

## Content-Security-Policy (added)
`default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https://tile.openstreetmap.org https://server.arcgisonline.com; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'`.
No inline or eval script is allowed. `style-src 'unsafe-inline'` remains only because React/Recharts emit style attributes (it does not permit inline scripts). `/docs`, `/redoc` and `/openapi.json` are exempt (Swagger UI loads from a CDN). **Verified in Chromium against the built app** (`npm run e2e:prod`): seven pages, the map overlay and the chart PNG download produce no CSP violations. Unit tests pin the policy string.

## Not covered
Penetration test by a third party; multi-user authorisation; audit trail of who ran which job; encryption at rest of `data/`; vulnerability scanning of the container image.

## Operational recommendations
1. Always set `GCL_API_TOKEN` when the service is reachable beyond localhost, and terminate TLS in front of it.
2. Bind to `127.0.0.1` (the compose file does) and publish only through the proxy; add rate limits there.
3. Rotate the Earth Engine service-account key periodically; store it with `chmod 600` / a secret manager.
4. Re-run `pip-audit` and `npm audit` before each release.
