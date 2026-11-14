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
| Frontend (12 pages including the trend dashboards), backend API, statistics engine, pixel analysis, exports, reports | Implemented and tested (see *Tests*) |
| Earth Engine extraction (`backend/app/gee/extract.py`) | Implemented and **run against live Earth Engine** (12-13 Nov 2026): NDVI, rainfall, ET, soil moisture, LST day/night, Landsat NDVI, JRC + MNDWI surface water, MCD12Q1 land cover, GRACE (CRI mascons), Aqua NDVI, EVI and the raster stacks. |
| Real Banni results | Committed under `data/processed/` (series and raster stacks) and `data/raw/` (raw extraction records). `python -m app.cli reproduce` reproduces all 9 handover figures. |
| Trend dashboards (`/dashboards`) | Rain and Green, Water and Heat, Where It Changed: one map and one year slider, a result card per factor, a 'before you trust this' box and a sources panel, all computed from stored data (`/api/dashboards/{id}`). |
| Handover reproduction | Implemented (`/api/statistics/handover-reproduction`); all 9 handover figures reproduce from the real data (`python -m app.cli reproduce`). |
| Aqua / EVI checks (brief s.7) | Aqua NDVI (`MODIS/061/MYD13Q1`) and Terra EVI (`MOD13Q1`) extracted with the handover protocol; trend and rain-removed tests repeated over the common years 2002-2024 (`python -m app.cli checks`, `/api/statistics/sensor-index-checks`, *Sensor and index checks* panel on Rain and Green). On the real data both agree with Terra NDVI in the monsoon and the dry season. |
| Geometry | Handover rectangle (9,751 km2) used; **no verified grassland polygon found** - support for supplying one is built. |
| Landsat species-level classification | **Not attempted** (no ground-truth labels). Landsat NDVI comparison with MODIS is implemented. |
| Groundwater | No automatic CGWB/India-WRIS download (the portal requires a sign-in with CAPTCHA); measured levels are analysed from a CSV upload (`lat`/`lon` columns place wells on the Water and Heat map). **No well data uploaded yet.** |
| Salinity | Landsat spectral proxy (SI1) extracted, but **unvalidated** for Banni until compared with field EC measurements. |
| Final phase (security, pipeline, report generator, new analyses, deployment assets) | Implemented and tested; see `docs/FINAL_COMPLETION_REPORT.md` for item-by-item status (COMPLETE / BLOCKED / NOT IMPLEMENTED) |
| Database | File-based store (JSON + GeoTIFF) rather than PostgreSQL/PostGIS; see `docs/ARCHITECTURE.md`. |

## Commands

All commands are for Windows PowerShell from the repository root unless a `cd` is shown. On macOS/Linux use `.venv/bin/` instead of `.\.venv\Scripts\`.

### 1. Get the code

```powershell
git clone https://github.com/DevloperHS/banni-climate-lens.git
cd banni-climate-lens
```

### 2. Install

Python 3.11+ and Node 20+ are required.

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r backend\requirements.txt       # runtime (includes earthengine-api)
.\.venv\Scripts\pip install -r backend\requirements-dev.txt   # adds pytest, httpx, pypdf, pip-audit for the tests
cd frontend; npm install; cd ..
copy .env.example .env                                         # then edit .env (never commit it)
```

### 3. Connect Google Earth Engine (only needed to download new data)

The extracted Banni data is already in `data/`, so the app works without this step. To re-extract or add variables:

1. Use a personal Google account with 2-Step Verification on. Create a Cloud project at <https://console.cloud.google.com/earth-engine>.
2. Enable the Earth Engine API: <https://console.cloud.google.com/apis/library/earthengine.googleapis.com>.
3. Register the project for noncommercial use: `https://code.earthengine.google.com/register?project=YOUR-PROJECT-ID`, then complete the questionnaire at <https://console.cloud.google.com/earth-engine/configuration>. Keep the free **Community** tier (no billing).
4. Sign in from this machine and set the default project:

```powershell
.\.venv\Scripts\earthengine authenticate
.\.venv\Scripts\earthengine set_project YOUR-PROJECT-ID
```

5. In `.env`, set the project and leave the service-account lines **empty** (if they are filled in, the app uses service-account mode instead of your login):

```
GCL_EE_PROJECT=YOUR-PROJECT-ID
GCL_EE_SERVICE_ACCOUNT=
GCL_EE_PRIVATE_KEY_FILE=
```

For a server, use a service account instead: grant it *Earth Engine Resource Viewer* (and *Service Usage Consumer* if needed), save its JSON key under `secrets/` and fill in all three lines. See `docs/SETUP.md`.

### 4. Download and analyse the data (command-line pipeline)

Run from `backend/`. Every command accepts `--region banni --start 2001 --end 2024`.

```powershell
cd backend
..\.venv\Scripts\python -m app.cli live-check        # sign-in, connection, and every collection/band the app reads
..\.venv\Scripts\python -m app.cli extract           # MODIS NDVI + IMERG rainfall 2001-2024, plus the handover's 2001/2023 NDVI test
..\.venv\Scripts\python -m app.cli quality           # completeness, missing months and unit checks per series
..\.venv\Scripts\python -m app.cli reproduce         # handover protocol vs its 9 reported figures (never forced to match)
..\.venv\Scripts\python -m app.cli water             # evapotranspiration + GLDAS root-zone and surface soil moisture
..\.venv\Scripts\python -m app.cli extended          # all remaining series (LST, Landsat, surface water, land cover, GRACE, Aqua, EVI ...) and the map raster stacks
..\.venv\Scripts\python -m app.cli checks            # Aqua NDVI + EVI: extract, then repeat the trend and rain-removed tests vs Terra NDVI
..\.venv\Scripts\python -m app.cli verify-metadata   # check dataset IDs, bands, units and scales against Google's catalogue (no sign-in needed)
..\.venv\Scripts\python -m app.cli validate-csv groundwater path\to\wells.csv   # check a field CSV offline before uploading (kinds: groundwater, field-ec, ground-truth; column layouts in data-templates\)
```

`extract`, `water` and `checks` stop at the first failure and store nothing incomplete. `extended` runs every task and prints a summary of what succeeded. The same jobs can be started from the app under **Settings > Data processing**.

Output goes to `data/processed/series/banni/*.json` (series), `data/processed/rasters/banni/*.tif` (map stacks) and `data/raw/banni/` (timestamped raw records).

### 5. Run the app

```powershell
# terminal 1: API on http://127.0.0.1:8000 (interactive docs at /docs)
cd backend; ..\.venv\Scripts\python -m uvicorn app.main:app --port 8000

# terminal 2: web app on http://localhost:5173 (/api is proxied to port 8000)
cd frontend; npm run dev
```

Open <http://localhost:5173/dashboards> for the three trend dashboards. Without data you will see empty states; to explore the interface with toy values use **Settings > Enable demonstration mode > Generate sample**. Everything shown in that mode is labelled synthetic.

Useful API checks while the backend runs:

```powershell
curl http://127.0.0.1:8000/api/health
curl "http://127.0.0.1:8000/api/health/earthengine"
curl "http://127.0.0.1:8000/api/statistics/handover-reproduction?region=banni&source=processed"
curl "http://127.0.0.1:8000/api/statistics/sensor-index-checks?region=banni&source=processed"
curl "http://127.0.0.1:8000/api/dashboards/rain_green?region=banni&source=processed"
```

### 6. Tests

```powershell
cd backend;  ..\.venv\Scripts\python -m pytest -q      # science + API + jobs (uses a temporary data folder, never your data)
cd frontend; npm test                                  # Vitest component tests
cd frontend; npm run typecheck                         # TypeScript check
cd frontend; npx playwright install chromium; npm run e2e   # end-to-end (starts its own servers/ports)
cd frontend; npm run build                             # production build into frontend/dist
```

Results of the last full run are recorded in `docs/TEST_RESULTS.md`.

### 7. Docker (optional)

```powershell
copy .env.production.example .env.production   # then edit; never commit it
docker compose up --build                      # API + built frontend in one container on http://127.0.0.1:8000; see docs/DEPLOYMENT.md
```

## Documentation

[FINAL COMPLETION REPORT](docs/FINAL_COMPLETION_REPORT.md) · [SECURITY REVIEW](docs/SECURITY_REVIEW.md) · [VALIDATION REPORT](docs/SCIENTIFIC_VALIDATION_REPORT.md) · [DATASET VERIFICATION](docs/DATASET_VERIFICATION.md) · [ARCHITECTURE](docs/ARCHITECTURE.md) · [SETUP](docs/SETUP.md) · [DATASETS](docs/DATASETS.md) · [METHODOLOGY](docs/METHODOLOGY.md) · [API](docs/API_DOCUMENTATION.md) · [DEPLOYMENT](docs/DEPLOYMENT.md) · [CONTRIBUTING](docs/CONTRIBUTING.md)

## Stack

React 18 + TypeScript + Vite + Tailwind 4 + Recharts + Leaflet + React Router + TanStack Query · FastAPI + Pydantic · NumPy / SciPy / pandas / statsmodels / rasterio / Pillow / matplotlib / ReportLab · earthengine-api · pytest / Vitest / Testing Library / Playwright.

## Layout

```
backend/app/{core,science,gee,routers}   config, stats engine, Earth Engine layer, HTTP routes
backend/tests                            pytest (science validation, API, jobs)
frontend/src/{pages,components,lib,state,test}   UI;  frontend/e2e  Playwright
data/processed, data/raw                 extracted Banni data (committed)
data/sample, data/cache                  synthetic sample and job logs (git-ignored)
data-templates/                          CSV templates for wells, field EC and ground truth
docs/                                    documentation
```
