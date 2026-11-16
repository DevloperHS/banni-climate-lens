# Handoff: GlobalClimateLens (Banni Grasslands)

Written 2026-11-16 to restart work on this repo. Committed on the `harsh` branch. Read this first, then `README.md` on `main`, then `docs/ARCHITECTURE.md` and `docs/KNOWN_ISSUES.md`.

---

## 1. What this is

**GlobalClimateLens** is an Earth-observation analytics app. It pulls satellite series from Google Earth Engine (GEE), stores them as files, runs trend and regression statistics, and shows the results in a React UI with full provenance. Exports are CSV, GeoJSON, GeoTIFF and PDF.

- **First (and only) case study:** Banni Grasslands, Kutch, Gujarat, India, 2001–2024.
- **Context:** Team Aryavart, NASA Space Apps 2026, "Earth System Trend Detective" challenge. The original brief and handover PDFs (`docs/Banni Project - Handover to Nancy Chaudhry.pdf`, `docs/Banni Trend Detective Project Brief for Harsh.pdf`) are still in older branches and in the local checkout. `main` no longer tracks them.
- **Repo:** `https://github.com/DevloperHS/banni-climate-lens` (remote `origin`).
- **Live app:** https://banni-app.livelygrass-8df5f932.centralindia.azurecontainerapps.io (Azure Container Apps, Central India).

### Headline scientific result (do not change without re-running)
Monsoon NDVI greening of **+0.0051 NDVI/yr** (2001–2024). Rainfall explains about two-thirds of it. A residual of **+0.0017 NDVI/yr** remains after rainfall is removed (Hamed–Rao modified Mann–Kendall, **p = 0.006**, reported elsewhere as 0.0059). It holds with a second sensor (Aqua), a second index (EVI) and several windows. All 9 figures from the original handover reproduce exactly from stored data (`python -m app.cli reproduce`).

### Non-negotiable integrity rules (built into code, tests and UI copy)
1. No number is hard-coded. Everything shown comes from stored series.
2. With no data, the UI shows an explicit empty state. There is **no silent fallback to fake data**.
3. A synthetic sample exists only for exploring the UI. It lives in a separate store (`data/sample/`) and carries a *SYNTHETIC SAMPLE* badge everywhere: UI, API `meta.synthetic`, CSV, PDF and PNG.
4. Trends describe satellite quantities. Copy must **never** claim a cause, species or groundwater change from a trend alone.

Keep these rules in any rework. Reviewers and judges checked them.

---

## 2. Branch state (important: the local checkout is stale)

| Branch | State |
|---|---|
| `origin/main` | **Source of truth.** Has everything below, plus Azure deploy, docs cleanup, architecture PNGs and a slimmer README. Merged PR #1 (`research-two-modes`). |
| `ashutosh` (local, checked out at `1ea0fb2`) | **24 commits behind `origin/main`, 0 ahead.** All its work is already in main. Run `git checkout main && git pull` before starting anything. |
| `origin/research-two-modes` | Merged into main. Can be deleted. |
| `origin/harsh` / local `harsh` | Main merged in, **plus Prosopis random-forest research** (`research/prosopis_rf/`, 8 commits, by DevloperHS). **Not merged into main yet.** Its diff vs main also shows frontend files differing (Overview/Methodology/Reports/index.css). Check whether those are real changes or stale merge leftovers before merging. |
| `list` (local only) | Older subset of `harsh` (Prosopis RF first commits). Superseded by `harsh`. |

**Untracked in the local working tree** (not on any branch here):
- `research/prosopis_rf/labelling/sheets/*.jpg` (~11 MB): image chips for labelling. These are deliberately git-ignored (Esri imagery licence). Regenerate them with `research/prosopis_rf/scripts/02_make_chips.py` on `harsh`.
- `research/prosopis_rf/results/cropland_export_log.txt`: log from the farmland export (script `12a`).
- `demo-video/GlobalClimateLens_Banni_TeamAryavart_30s.mp4` and `_v2.mp4` (~51 MB): 30 s submission demo videos. Do not commit them (too large). Keep them outside git or use LFS or a release asset.

### CI/CD
`.github/workflows/deploy.yml` (on main) builds the Docker image, pushes it to Azure Container Registry, updates container app `banni-app` in resource group `banni-rg` and curls `/api/health`. It runs on **every push to `main` and `research-two-modes`**, so pushing to main deploys to the live URL.
- Secret: `AZURE_CLIENT_SECRET` (GitHub repo secret). The service-principal client id, tenant and subscription id are hardcoded in the workflow. Move them to secrets or variables in a rework.
- Manual fallback: `deploy/deploy.sh <tag>` (local docker build + push; comments are in Hinglish; the student Azure account has ACR Tasks disabled).

---

## 3. Stack and layout

**Backend:** Python 3.11+ (developed on 3.14), FastAPI, Pydantic, NumPy, SciPy, pandas, statsmodels, rasterio, Pillow, matplotlib, ReportLab, earthengine-api.
**Frontend:** React 18, TypeScript (strict), Vite, Tailwind 4, Recharts, Leaflet, React Router, TanStack Query.
**Tests:** pytest, Vitest + Testing Library, Playwright.
**Storage:** a file store (JSON series + GeoTIFF rasters), with no database. Rationale is in `docs/ARCHITECTURE.md`. `core/store.py` is the only module that touches storage, so it is the single swap point for PostGIS.

```
backend/app/
  core/       config (GCL_* env), regions registry, dataset catalog, file store, synthetic sample,
              security (token, headers, sanitising), rate limiter, groundwater + field data import
  science/    pure numerics, no web or GEE imports:
              processing (scale/QA/aggregation), timeseries (seasons, coverage rules), stats (MK,
              Hamed-Rao, Sen+CI, OLS+HAC, BH-FDR, rainfall-adjusted, event study), pixel (vectorised
              per-pixel MK/Sen + FDR), raster_qc, validation, multivar, handover (reproduction protocol)
  gee/        client (auth), extract (per-dataset extraction, tiled raster export), cancel
  routers/    analysis, core_routes, dashboards, extra, reports, variables (generic router factory)
  services.py orchestration + mtime-keyed cache + insight text
  jobs.py     single-worker background job queue (progress/cancel/retry/logs, crash recovery)
  reporting.py PDF report built from stored results
  cli.py      live-check | extract | quality | reproduce | water | checks | verify-metadata
  config/regions.json            add a study area = add a JSON entry
  config/handover_reference.json numbers the reproduction is compared against
backend/tests/   pytest (science, API, jobs, hardening, deploy, handover)
frontend/src/    pages/, components/ (analysis.tsx, charts.tsx, MapView.tsx, panels2.tsx, ui.tsx, Layout.tsx),
                 lib/api.ts (typed client), state/AppState.tsx (region/period/source/theme in localStorage)
frontend/public/{overview,methodology,report}/index.html   large hand-written static HTML pages, embedded by iframe
frontend/e2e, frontend/e2e-prod   Playwright (prod suite checks the strict CSP)
data/processed/series/banni/*.json   extracted series (tracked in git)
data/raw/banni/*.json                raw GEE extracts (tracked)
data/sample, data/cache              git-ignored
data-templates/                      CSV templates: groundwater, field EC, ground truth
docs/                                see section 8
```

### Frontend: what users actually see (on main)
The sidebar has only **two entries**: **Overview** (`/`) and **Research** (`/reports`). The other routes still exist in `App.tsx` (`/dashboards`, `/regions`, `/satellite`, `/vegetation`, `/climate`, `/water`, `/spatial`, `/statistics`, `/methodology`, `/settings`) and you can reach them by URL.
- **Overview** is just an iframe of `public/overview/index.html` (an animated "Banni overview scene").
- **Research** (`pages/Reports.tsx`) has a two-mode toggle, persisted in `localStorage['research.mode']`:
  - *Researcher / Environmental scientist*: live API-driven panels, a hero map with a layer switch (pixel NDVI trend / land cover / 2001 vs 2024), a variable/aggregation picker, and a split view with the research paper (`public/report/index.html`).
  - *Student / Local community*: plain-language content, which embeds `public/methodology/index.html`.
- Content source for the Research page copy: `docs/research_page_content.md`. Main deleted it during docs cleanup, so check whether you still need it.
- The static HTML pages take a `?theme=` param and were reworked heavily in the last commits. They hold a lot of copy and numbers. Check that the numbers match the API (the latest fixes included Hamed–Rao p-values, Durbin–Watson from platform diagnostics, adjusted p-values in Figure 6, and the area unified to 9,751 km²).

---

## 4. Running it (Windows, this machine)

Use the **root `.venv`** for everything (install deps there; do not make per-folder venvs).

```powershell
# one-time
python -m venv .venv
.\.venv\Scripts\pip install -r backend\requirements.txt      # or requirements.lock for exact pins
cd frontend; npm install; cd ..

# run (two terminals)
cd backend;  ..\.venv\Scripts\python -m uvicorn app.main:app --port 8000   # docs at http://127.0.0.1:8000/docs
cd frontend; npm run dev                                                  # http://localhost:5173
```
`.claude/launch.json` already defines `backend` (port 8000) and `frontend` (port 5173) for the Claude preview tools.

The extracted Banni data ships in `data/`, so the app runs **without GEE credentials**. A local `.env` exists (not committed). Templates are `.env.example` and `.env.production.example`.

**Tests**
```powershell
cd backend;  ..\.venv\Scripts\python -m pytest -q
cd frontend; npm test
cd frontend; npx playwright install chromium; npm run e2e     # starts its own servers on :8001/:5174
cd frontend; npm run e2e:prod                                 # CSP check against the production build
```
Last recorded full run (`docs/TEST_RESULTS.md`, 2026-11-07): 137 backend / 39 component / 22 e2e passed. The later UI consolidation rewrote `app.test.tsx` and `e2e/app.spec.ts`, so re-run everything before trusting those counts.

**Production:** a single process with one worker. The job queue and cache are in-process, so **never run more than 1 uvicorn worker**. `GCL_STATIC_DIR` serves the built UI from FastAPI. `GCL_API_TOKEN` guards write endpoints; reads are public. Full env reference: `docs/DEPLOYMENT.md` §4.

**Re-extracting from GEE** (needs a GEE project; the one used was `banni-trend-2026`): `docs/SETUP.md` §3–4. Then run `python -m app.cli live-check`, `extract`, `quality`, `reproduce`, `water`, `checks` and `verify-metadata`.

---

## 5. Data inventory (Banni, `data/processed/series/banni/`)

| Key | Source | Notes |
|---|---|---|
| `ndvi` | MODIS Terra MOD13Q1 v6.1, 250 m | **Headline series.** No SummaryQA filter, no water mask. |
| `ndvi_qa`, `ndvi_nowater` | same | Sensitivity series only. Not used in the headline. |
| `ndvi_aqua` | MODIS Aqua MYD13Q1 | Sensor cross-check (2002–2024). |
| `evi` | MOD13Q1 EVI | Index cross-check. |
| `ndvi_landsat` | Landsat | Comparison with MODIS. |
| `precip` | GPM IMERG Monthly V07 | **Suspect: about 1.8× CHIRPS** (2020: 1,001 mm vs 524 mm). Verify against CHIRPS/IMD. |
| `et` | MOD16A2GF | |
| `sm_root`, `sm_surface` | GLDAS-2.1 Noah | Model output, about 28 km. |
| `lst_day`, `lst_night` | MOD11A2 | |
| `grace_tws` | GRACE JPL mascons, 3° | Context only. |
| `lc_*` | MCD12Q1 | Land-cover shares. |
| `water_extent`, `water_extent_mndwi` | Landsat MNDWI | |
| `salinity_index` | Landsat SI1 | **Unvalidated proxy.** |

**Geometry:** the handover rectangle is 23.20–23.95 °N, 68.80–69.95 °E (**9,751 km²**). Banni itself is only about 2,500 km². The rectangle includes mainland Kutch and the edge of the Rann. **No verified grassland polygon has been found.** Upload support exists (`backend/app/config/geometries/`).

---

## 6. Known issues and gaps (carry these into the rework)

From `docs/KNOWN_ISSUES.md` and README status:
- `data/raw/banni/handover_water_table_*.json` is misnamed. It holds ET + GLDAS soil moisture, not wells, and its provenance says `key: ndvi`. `extract.py` has been fixed for new extracts, but the old artifact remains.
- **No groundwater data.** CGWB / India-WRIS needs a sign-in with a CAPTCHA, so there is no automatic download. The only path is CSV upload (`data-templates/groundwater_template.csv`).
- IMERG rainfall looks inflated (see above).
- Two aggregation rules exist and are **not interchangeable**: `timeseries.seasonal_aggregate` (75 % valid-month rule) vs `handover.handover_annual` (handover protocol).
- NDVI cannot separate *Prosopis* from native grass. No Landsat species classification exists in the app (no ground-truth labels). Research on `harsh` partly addresses this; see section 7.
- `docs/DEPLOYMENT.md` says Docker was never built locally. That is outdated: the Azure pipeline now builds it. Commit `1003047` added `libexpat` for rasterio, same-origin framing and the CSP for the static pages.
- Azure identifiers are hardcoded in `deploy.yml` (see section 2).

---

## 7. Prosopis research (branch `harsh`, not yet in main)

`research/prosopis_rf/` contains `README.md`, `REPORT.md` (plain-language), `gee/*.js`, `scripts/01–12*.py`, `labelling/*.csv` and `results/*`.

**Question:** is *Prosopis juliflora* (an invasive thorny tree) the cause of the greening that rain does not explain?

**Method:**
- Sentinel-2 random-forest classifier (from a supplied `banni_rf.js`).
- 159 hand-labelled training points, checked visually on Esri imagery and calibrated on Bhan 2024 field sites (Zenodo 10.5281/zenodo.11197850): 39 Prosopis, 34 mixed, 53 water, 33 saline brush, all at least 150 m apart.
- A 2023 class map at 10 m, with a 2017 map for robustness. MODIS pixels are split by Prosopis share.
- Trends are tested with CHIRPS and with IMERG rain removed.
- The original script could not export, because MODIS sinusoidal reprojection ran out of memory. The fix was a two-stage run: store the class map as an asset, then run the reduction with `tileScale: 16`.

**Findings:**
- 2023 cover: woodland 11.6 %, mixed 45.9 %, water 13.6 %, saline brush 29.0 %.
- Both high- and low-Prosopis pixels green significantly, with or without rain removed. The difference (high minus low) is +0.0015/yr, **p = 0.063 (not significant)**. It reaches p < 0.05 under only one looser cutoff.
- **Pure saline brushland with no trees in 2017 or 2023 also greens** (after rain removal, p = 0.001–0.002).
- Relative pace is about **18–24 % per decade for every class**.
- Removing Prosopis woodland changes the area trend by less than 13 %, which is **neutral** under the brief's 25 % rule.
- **Conclusion:** Prosopis is not the main driver. The greening affects the whole landscape, and its cause is still unknown (candidates: farming, soil moisture or salinity, grazing, rain timing).

**Limits:**
- The classifier has no farmland class. Script `12_farming_test.py` / `12a_export_cropland.py` began a farmland test (log in the untracked `cropland_export_log.txt`). **Its status is unclear. Check `harsh` README "Further exploration".**
- The brushland vs mixed boundary is the weakest part of the map.
- The 2017 map has not been validated.
- Removing rain is linear only.

**Decision needed:** whether to merge `harsh` into main, and whether to surface the Prosopis result in the app's Research page. It is not in the UI today. The UI currently says species-level classification was "not attempted".

---

## 8. Docs map

On `main`: `README.md`, `docs/SETUP.md`, `ARCHITECTURE.md` (+ `arch-system.png`, `arch-pipeline.png`), `DATASETS.md`, `DATASET_VERIFICATION.md`, `METHODOLOGY.md`, `API_DOCUMENTATION.md`, `DEPLOYMENT.md`, `CONTRIBUTING.md`, `FIELD_DATA_GUIDE.md`, `KNOWN_ISSUES.md`, `SCIENTIFIC_VALIDATION_REPORT.md`, `SECURITY_REVIEW.md`, `TEST_RESULTS.md`, `FINAL_COMPLETION_REPORT.md` (item-by-item COMPLETE / BLOCKED / NOT IMPLEMENTED), `FINAL_REPORT.md`.
Removed on main (still on old branches): `FINAL_CHECKLIST.md`, `TRANSFORMATION_REPORT.md`, `research_page_content.md`, both brief/handover PDFs.

---

## 9. Restart checklist for the next agent

1. `git fetch --all && git checkout main && git pull`. Do **not** build on local `ashutosh`.
2. Set up the root `.venv`, run backend + frontend, and run all four test suites. Record the real counts.
3. Decide on `harsh`: diff its `frontend/` against main and merge only `research/` if the frontend changes are stale.
4. Remember that **any push to `main` deploys to the live Azure app.** Work on a branch and open a PR.
5. Keep the integrity rules in section 1 and the caveats in section 6 in every new piece of UI copy.
6. Keep `demo-video/*.mp4` and `labelling/sheets/*.jpg` out of git.

### Open questions for the team (unknown from the repo)
- What is the scope of "rework": UI and copy, adding a new region, merging the Prosopis research, or something larger such as replacing the file store?
- Is the live Azure deployment still needed, and who owns its credentials?
- Has a verified Banni grassland polygon been found yet?

Contributors seen in history: DevloperHS (Prosopis research, README), Ashutosh Shri Mishra (platform, UI, deploy).
