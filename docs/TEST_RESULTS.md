# Test results

Last full run: 2026-11-07 (final phase), Windows 11, Python 3.14.6, Node 24.18, Chromium (Playwright 1254). Every number below comes from a command that was actually executed.

| Suite | Command | Result |
|---|---|---|
| Backend: science, API, jobs, security, pipeline, deployment | `cd backend; python -m pytest -q` | **137 passed**, 4 warnings (Starlette/httpx deprecation; all-NaN-slice for fully masked pixels, returned as NaN by design; two library warnings) |
| Backend in a clean virtualenv | `scripts` in FINAL_COMPLETION_REPORT §6: fresh venv → `requirements.txt` → freeze to `requirements.lock` → dev deps → pytest | **137 passed** (fresh venv; 68 pinned runtime packages written to `requirements.lock`) |
| Frontend type-check | `cd frontend; npx tsc --noEmit` | exit 0 |
| Frontend component tests | `npm test` | **39 passed** (2 files) |
| End-to-end (Chromium; own backend on :8001 with a temp data dir, own Vite on :5174) | `npm run e2e` | **22 passed** |
| Production build | `npx vite build` | built |
| `npm audit` | `cd frontend; npm audit` | **0 vulnerabilities** (after `react-router-dom` 7.18.5, `vitest` 5.1) |
| `pip-audit` | `python -m pip_audit` | no vulnerable application dependency; only `pip` itself |
| Metadata verification (network, no credentials) | `python -m app.cli verify-metadata` | all 10 collections OK |

History: phase 1 = 52 / 20 / 13 (backend / component / e2e); phase 2 = 72 / 26 / 14; final = 137 / 39 / 22.

## Final-phase coverage (added)
- **Science (23 tests)**: raster QC (CRS, square pixels, extent, band years, empty), grid alignment/resampling, water mask (incl. effect on pixel trends), difference maps, cross-resolution trend agreement, evergreen index; ground-truth parsing and separability (refuses small samples, AUC orientation, noise gives ~0.5); EC validation; multivariate comparison (matrix symmetry, BH, VIF/collinearity, PRESS vs brute-force LOO, partial correlation, detrending, coincident anomalies); rainfall-adjusted event study (removes rain-driven change, keeps independent shock); groundwater validation (rejection reasons, id sanitising, anomaly aggregation without spurious steps, per-well FDR); metadata check logic (units, scale, gsd, coverage, fetch failure).
- **API / security / pipeline (27 tests)**: token enforcement on every write route and open reads; traversal and bad identifiers; headers/CORS/preflight; no error-detail leakage; redaction and CSV/text sanitising; upload limit 413, binary rejection, note injection; health; groundwater and salinity workflows; ground-truth workflow; water-masked pixel trends and GeoTIFF tags; difference, export PNG, layer GeoTIFF, QC; trend agreement; comparison endpoints; rainfall-adjusted event; previous-monsoon control; job progress/log; **completeness gate stores nothing**; **cancel mid-task writes nothing, retry runs only unfinished tasks**; recovery after restart removes partial files; atomic writes; job validation for new datasets; tile plan covers the grid exactly under the download cap; tile mosaic round trip; report manifest and PDF contents (all 11 sections, references, synthetic banner, geometry statement); honest degradation without data.
- **Deployment (12 tests)**: SPA fallback and API precedence; 7 traversal variants never expose files outside the build; headers on SPA; health degrades when the data dir is not writable; JSON logging with redaction; no query strings in logs.
- **Component (13 tests)**: availability strip; global period feeds requests; comparison panel separates association/prediction/causation and refuses < 2 variables; groundwater empty state and validation report; salinity stays UNVALIDATED; Prosopis panel exploratory with no-labels message; job progress, cancel with bearer token, retry and log, error surfacing; token kept in sessionStorage only; CSV upload validation.
- **E2E (8 added)**: availability and period selector; dry-season analysis and honest Prosopis investigation with Rann mask; ground-truth upload to separability with caveats; spatial mask, change map and map export; environmental comparison; groundwater upload to per-well trends, salinity unvalidated, rain-adjusted cyclone; report manifest and PDF; settings token and geometry honesty.

## Other executed checks
- Pixel-trend benchmark on the full 250 m Banni grid (334 × 513 px × 24 yr): **4.0 s**, ~317 MB peak (500 m grid: 0.8 s, ~158 MB).
- Production-mode instance probed with curl (SPA, deep link, gzip asset, health GET/HEAD, 404 JSON for unknown API routes, 401 without token / 200 with token, security headers, CORS closed to foreign origin, 5 traversal variants → HTML or 404 only, JSON logs).
- `scripts/backup.sh` and `scripts/backup.ps1` run on temp trees (cache/sample/partial files excluded; checksum verified).
- Secret pattern scan of the tree: only a deliberately fake PEM header inside a redaction test.

## Not tested / not verified
- **Earth Engine live calls** (no credentials): extraction code, band masks, raster export and tiling against the service.
- **Docker build and run** (Docker unavailable).
- Real-data scientific results for Banni: none exist.
- Firefox/Safari, load/stress testing, third-party penetration test, full accessibility audit, TLS/proxy setups.
