# Setup

## 1. Prerequisites
Python 3.11+ (developed on 3.14), Node 20+ (developed on 24), npm.

## 2. Install & run
```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r backend\requirements.txt
cd frontend; npm install; cd ..
copy .env.example .env      # then edit; .env is git-ignored
```
Backend: `cd backend; ..\.venv\Scripts\python -m uvicorn app.main:app --port 8000` (OpenAPI UI at `/docs`).
Frontend: `cd frontend; npm run dev` (port 5173; `/api` is proxied to port 8000, override with `API_TARGET`).

## 3. Earth Engine configuration
Earth Engine requires a Google Cloud project registered for Earth Engine (noncommercial or commercial registration at https://earthengine.google.com).

**Option A - service account (recommended for servers/CI)**
1. In the Cloud project enable the *Earth Engine API*; create a service account; register it for Earth Engine access.
2. Create a JSON key and store it **outside the repo** (or under `secrets/`, which you must keep out of Git; `*service-account*.json` and `.env*` are git-ignored).
3. In `.env`:
   ```
   GCL_EE_PROJECT=your-gcp-project-id
   GCL_EE_SERVICE_ACCOUNT=sa-name@your-project.iam.gserviceaccount.com
   GCL_EE_PRIVATE_KEY_FILE=C:/path/to/key.json
   ```

**Option B - local development with your own account**
```powershell
.\.venv\Scripts\earthengine authenticate
```
then set only `GCL_EE_PROJECT` in `.env`.

Credentials are read **only by the backend**; the browser never receives them.

## 4. Verify the integration, then run the validation workflow
Account notes from the research handover (pp.2-3): use a **personal Gmail** with 2-Step Verification on (organisation accounts lack the permission to enable the API); register the Cloud project as **non-commercial, Community tier** (signup.earthengine.google.com); if you are asked to add a payment method you are on the commercial path - go back. Enable the **Earth Engine API** for that project separately (APIs & Services > Library > Google Earth Engine API). Do not enable billing.

Then, from `backend/` with the virtual environment active and `GCL_EE_PROJECT` set (and `earthengine authenticate` done, or a service account configured):

```powershell
python -m app.cli live-check   # connection + every collection and band; stops with the exact error if anything fails
python -m app.cli extract      # MODIS NDVI + IMERG rainfall 2001-2024 (raw -> data/raw, processed -> data/processed)
python -m app.cli quality      # completeness, missing months, unit-plausibility flags
python -m app.cli reproduce    # handover protocol vs the handover's reported numbers (never forced to match)
python -m app.cli water        # ET + GLDAS root-zone / surface soil moisture (after reproduce looks sane)
python -m app.cli verify-metadata   # network only (no credentials): checks every collection/band/unit/scale/coverage against Google's catalogue
```
Each stage refuses to continue if the previous one failed. Then complete the **PENDING** sections of `docs/SCIENTIFIC_VALIDATION_REPORT.md` and the live checklist in `docs/DATASET_VERIFICATION.md`.

Manual spot-check: compare three monthly values (an NDVI month, an IMERG monthly total, one ET composite) with the Code Editor, and check the IMERG day-count (`days_agree`) in `data/raw/banni/precip_*.json`.

After the series jobs, run the *stack* jobs in Settings (NDVI annual/monsoon/summer/peak, rainfall, LST, ET, soil moisture, Landsat NDVI, salinity proxy, and `water_occurrence` for the Rann-water mask). They are exported on a shared, region-anchored grid and split into tiles automatically.

Raster stacks for the maps use `getDownloadURL` (~32 MB cap per request). If a stack exceeds it, shorten the period or raise `scale_m` in `core/catalog.py`; the error is surfaced in the job.

## 5. Without Earth Engine
The app runs and shows explicit empty states. For interface exploration only: Settings → enable *Demonstration mode* → *Generate sample* creates a **synthetic** toy dataset (stored in `data/sample/`, hidden from the default experience, labelled SYNTHETIC everywhere). Groundwater CSVs can be uploaded regardless.

## 5b. Authentication token (recommended whenever the API is not strictly local)
Set `GCL_API_TOKEN` in `.env`; enter the same token in Settings > API access token (kept in the tab's sessionStorage). It protects job creation, uploads and deletions.

## 6. Boundary polygon (optional, recommended)
Place a verified Banni grassland polygon at `backend/app/config/geometries/banni_grassland.geojson` (see the README in that folder). It is registered as a separate region `banni_grassland`; run the same jobs for it and compare with the rectangle.

## 7. Adding a study region
Append an object to `backend/app/config/regions.json` (`id`, `name`, `bbox`, `study_period`, optional `events`, `monsoon_months`). It appears in the region selector after a backend restart. Monsoon/summer season definitions are global in `science/timeseries.py`; change them there for non-Indian climates.

## 8. Tests
See README. E2E tests start their own backend (port 8001, temp data dir) and Vite (port 5174).
