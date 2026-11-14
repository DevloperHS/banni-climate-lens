# GlobalClimateLens

Earth-observation analytics for long-term environmental change. First research case: **Banni Grasslands, Kutch, Gujarat (2001-2024)**.

Select a region and period, retrieve satellite-derived series (Google Earth Engine), run trend / regression / rainfall-adjusted analyses, inspect gridded layers and FDR-corrected pixel trends, and export CSV / GeoJSON / GeoTIFF / PDF with full provenance.

> **Scientific integrity rules built into the platform**
> - No observation, statistic or finding is hard-coded. Everything shown is computed from stored series.
> - Without data the UI shows an explicit empty state. There is **no silent fallback to fake data**.
> - A clearly labelled **synthetic sample** (toy model) can be generated to explore the interface; it lives in a separate store and is badged *SYNTHETIC SAMPLE* in the UI, API (`meta.synthetic`), CSV, PDF and chart PNGs.
> - Trends describe satellite-derived quantities; they never identify causes, species or groundwater change.

## Status (honest summary)

| Area | State |
|---|---|
| Frontend (11 pages), backend API, statistics engine, pixel analysis, exports, reports | Implemented and tested (see *Tests*) |
| Earth Engine extraction (`backend/app/gee/extract.py`) | Implemented. Stored series include `retrieval_date` and `kind=observed`; the repository has no independent Earth Engine execution log. |
| Stored Banni series | Stored under `data/processed/` (git-ignored). `python -m app.cli reproduce` reproduces all 9 handover figures from the stored series. |
| Trend dashboards (`/dashboards`) | Rain and Green, Water and Heat, Where It Changed: one map and one year slider, a result card per factor, a 'before you trust this' box and a sources panel, all computed from stored data (`/api/dashboards/{id}`). |
| Handover reproduction | Implemented (`/api/statistics/handover-reproduction`); all 9 handover figures reproduce from the real data (`python -m app.cli reproduce`). |
| Aqua / EVI checks (brief s.7) | Aqua NDVI (`MODIS/061/MYD13Q1`) and Terra EVI (`MOD13Q1`) extracted with the handover protocol; trend and rain-removed tests repeated over the common years 2002-2024 (`python -m app.cli checks`, `/api/statistics/sensor-index-checks`, *Sensor and index checks* panel on Rain and Green). On the real data both agree with Terra NDVI in the monsoon and the dry season. |
| Geometry | Handover rectangle (9,751 km2) used; **no verified grassland polygon found** - support for supplying one is built. |
| Landsat species-level classification | **Not attempted** (no ground-truth labels). Landsat NDVI comparison with MODIS is implemented. |
| Groundwater | No automatic CGWB/India-WRIS download (the portal requires a sign-in with CAPTCHA); measured levels are analysed from a CSV upload (`lat`/`lon` columns place wells on the Water and Heat map). |
| Salinity | No satellite product integrated; reported as such in the UI. |
| Final phase (security, pipeline, report generator, new analyses, deployment assets) | Implemented and tested; see `docs/FINAL_COMPLETION_REPORT.md` for item-by-item status (COMPLETE / BLOCKED / NOT IMPLEMENTED) |
| Database | File-based store (JSON + GeoTIFF) rather than PostgreSQL/PostGIS; see `docs/ARCHITECTURE.md`. |

## Known limitations

- The analysis window is a rectangle, not a verified Banni grassland polygon: 23.20–23.95 °N, 68.80–69.95 °E (about 9,751 km²).
- No groundwater/well observations are included in the repository.
- `handover_water_table_*.json` contains ET and GLDAS soil moisture, not wells or depth-to-water.
- Salinity is an unvalidated SI1 proxy, not field-EC data.
- NDVI cannot distinguish *Prosopis* from native grass.
- The headline trend uses `ndvi` (no SummaryQA filter and no water mask).
- Demonstration mode is off by default.

## Quick start (Windows PowerShell; adapt paths on macOS/Linux)

```powershell
# 1. Backend
python -m venv .venv
.\.venv\Scripts\pip install -r backend\requirements.txt
cd backend; ..\.venv\Scripts\python -m uvicorn app.main:app --port 8000      # API docs: http://127.0.0.1:8000/docs

# 2. Frontend (second terminal)
cd frontend; npm install; npm run dev                                          # http://localhost:5173
```

Open the app. With no data you will see empty states. Either:
- **Explore the interface only:** Settings → *Enable demonstration mode* → *Generate sample* → *Show synthetic sample*. All values are synthetic; the mode is off by default.
- **Real data:** configure Earth Engine (`docs/SETUP.md` §4), then `python -m app.cli live-check` → `extract` → `reproduce` (or Settings → *Start processing job*).

## Tests

```powershell
cd backend;  ..\.venv\Scripts\python -m pytest -q      # science + API + jobs
cd frontend; npm test                                  # Vitest component tests
cd frontend; npx playwright install chromium; npm run e2e   # end-to-end (starts its own servers/ports)
```

Results of the last full run are recorded in `docs/TEST_RESULTS.md`.

## Documentation

[FINAL COMPLETION REPORT](docs/FINAL_COMPLETION_REPORT.md) · [SECURITY REVIEW](docs/SECURITY_REVIEW.md) · [VALIDATION REPORT](docs/SCIENTIFIC_VALIDATION_REPORT.md) · [DATASET VERIFICATION](docs/DATASET_VERIFICATION.md) · [ARCHITECTURE](docs/ARCHITECTURE.md) · [SETUP](docs/SETUP.md) · [DATASETS](docs/DATASETS.md) · [METHODOLOGY](docs/METHODOLOGY.md) · [API](docs/API_DOCUMENTATION.md) · [DEPLOYMENT](docs/DEPLOYMENT.md) · [CONTRIBUTING](docs/CONTRIBUTING.md)

## Stack

React 18 + TypeScript + Vite + Tailwind 4 + Recharts + Leaflet + React Router + TanStack Query · FastAPI + Pydantic · NumPy / SciPy / pandas / statsmodels / rasterio / Pillow / matplotlib / ReportLab · earthengine-api · pytest / Vitest / Testing Library / Playwright.

## Layout

```
backend/app/{core,science,gee,routers}   config, stats engine, Earth Engine layer, HTTP routes
backend/tests                            pytest (science validation, API, jobs)
frontend/src/{pages,components,lib,state,test}   UI;  frontend/e2e  Playwright
data/{processed,sample,raw,cache}        runtime data (git-ignored)
docs/                                    documentation
```

<!-- deploy-section -->
## Run with Docker

    docker build -t banni-climate-lens:local .
    docker run --rm -d --name banni-test -p 8001:8000 -e GCL_API_TOKEN=change-me banni-climate-lens:local

Open http://localhost:8001. The container serves the React frontend, the static pages (`/overview/`, `/report/`, `/methodology/`) and the API from one origin. Writes to the API need the `GCL_API_TOKEN` bearer token.

## Deploy to Azure (Container Apps)

Live app: https://banni-app.livelygrass-8df5f932.centralindia.azurecontainerapps.io

The app runs on Azure Container Apps (`banni-app` in resource group `banni-rg`, region `centralindia`) with the image stored in Azure Container Registry. On an Azure for Students subscription `az acr build` is blocked (`TasksOperationsNotAllowed`), so the image is built locally and pushed:

    az login --use-device-code
    ./deploy/deploy.sh v5

Use a new tag for every deploy. The script builds with `--provenance=false --sbom=false`, pushes to ACR, updates the container app and runs a health check. See `deploy/DEPLOY.md` for the full cheat sheet, rollback steps and known pitfalls.

## Security notes

- Responses carry `X-Frame-Options: SAMEORIGIN` and a Content-Security-Policy with `frame-ancestors 'self'`, so the app can embed its own pages in iframes and nothing else can.
- The static pages (`/overview/`, `/report/`, `/methodology/`) have a CSP that allows their one inline script. All other routes use `script-src 'self'`.
- The API token is stored as the Container App secret `gcl-token`. Never commit it.
<!-- /deploy-section -->

<!-- deploy-section -->
## Run with Docker

    docker build -t banni-climate-lens:local .
    docker run --rm -d --name banni-test -p 8001:8000 -e GCL_API_TOKEN=change-me banni-climate-lens:local

Open http://localhost:8001. The container serves the React frontend, the static pages (`/overview/`, `/report/`, `/methodology/`) and the API from one origin. Writes to the API need the `GCL_API_TOKEN` bearer token.

## Deploy to Azure (Container Apps)

Live app: https://banni-app.livelygrass-8df5f932.centralindia.azurecontainerapps.io

The app runs on Azure Container Apps (`banni-app` in resource group `banni-rg`, region `centralindia`) with the image stored in Azure Container Registry. On an Azure for Students subscription `az acr build` is blocked (`TasksOperationsNotAllowed`), so the image is built locally and pushed:

    az login --use-device-code
    ./deploy/deploy.sh v5

Use a new tag for every deploy. The script builds with `--provenance=false --sbom=false`, pushes to ACR, updates the container app and runs a health check. See `deploy/DEPLOY.md` for the full cheat sheet, rollback steps and known pitfalls.

## Security notes

- Responses carry `X-Frame-Options: SAMEORIGIN` and a Content-Security-Policy with `frame-ancestors 'self'`, so the app can embed its own pages in iframes and nothing else can.
- The static pages (`/overview/`, `/report/`, `/methodology/`) have a CSP that allows their one inline script. All other routes use `script-src 'self'`.
- The API token is stored as the Container App secret `gcl-token`. Never commit it.
<!-- /deploy-section -->
