# GlobalClimateLens - Final Completion Report

Date of audit: 2026-11-07. Everything below was checked in the repository and, where stated, executed.

**Status vocabulary**
- **COMPLETE** - implemented and verified (by tests, a live probe, or an automated check that was run).
- **BLOCKED** - implementation exists but cannot be finished or verified without an external resource, credential or data source.
- **NOT IMPLEMENTED** - still requires development.

**Headline.** The platform is complete as software and verified on synthetic and planted data. **No real Banni satellite result exists yet**, because Earth Engine could not be authenticated here and no authoritative grassland boundary is available. Every real-data scientific item is therefore BLOCKED, not complete. Nothing in this report, the app or the exports presents synthetic data as observation.

---

> **Superseded in part by the real-data phase (see the section at the end of this report and `SCIENTIFIC_VALIDATION_REPORT.md` §11).** Statements below that real data is blocked describe the state at the first audit.

## 1. Completed features (COMPLETE)

### Science and analysis
| Feature | Evidence |
|---|---|
| Mann-Kendall, Hamed-Rao, Sen slope + CI; OLS + diagnostics + HAC; BH-FDR; rainfall-adjusted analysis with sensitivities S1-S5 and diagnostics-driven caveats | 32 science tests incl. exact agreement with `pymannkendall` (1e-8) |
| Reproduction of the research handover protocol with honest *reproduced / consistent / not reproduced* statuses | tests: equals the handover script verbatim; statuses; reference values from handover pp.1,9,12 |
| Seasonal NDVI (summer/monsoon/peak/post-monsoon/winter) and previous-monsoon rainfall control for dry-season NDVI | API + E2E |
| Pixel-level trend maps with BH-FDR and Rann-water masking (grid alignment / resampling checked) | unit + API tests; benchmark: full 250 m grid (171k px × 24 yr) in 4.0 s, ~317 MB peak |
| MODIS vs Landsat spatial trend agreement (cross-resolution) | tested on synthetic rasters of different resolutions |
| Exploratory dry-season persistence indicator + ground-truth validation tooling (AUC with bootstrap CI; refuses < 10 points per class) | tests; UI labels it EXPLORATORY and states that no labels exist |
| Salinity proxy + field-EC validation tool (refuses < 10 points; otherwise "UNVALIDATED") | tests |
| Measured groundwater CSV import with validation report, per-well Mann-Kendall + BH-FDR, multi-well anomaly aggregation, visualisation | unit, API, E2E |
| Cyclone Biparjoy placebo-year event study **and** rainfall-adjusted version (verified: removes a rain-driven change, keeps an independent shock) | unit + API + E2E |
| Multi-variable comparison: correlation matrices (BH-adjusted), partial correlations, VIF, leave-one-out R², lagged correlations, coincident anomalies; association / prediction / causation reported separately | unit (PRESS vs brute force) + API + E2E |
| Geometry comparison (rectangle vs grassland polygon as separate regions); polygon validation; ellipsoidal area (9,751.3 km², verified against an independent integration) | unit + API + E2E |
| Raster QC on every read (CRS, north-up, square pixels, extent, band years, valid fraction) | unit + API |
| Automated metadata verification against Google's catalogue: 10 collections, bands/units/scales/resolution/coverage | **run: all passed**; logic unit-tested |

### Application
| Feature | Evidence |
|---|---|
| All 11 pages functional with consistent region selector, **global period selector** and **data-availability strip** in the header | 22 E2E, 39 component tests |
| Layer switching, raster overlays, legends, coordinate display, pixel inspector, change (difference) maps, map export (PNG with axes/legend/CRS/provenance; GeoTIFF) | API + E2E |
| Chart PNG download; CSV, GeoJSON, GeoTIFF exports with provenance | tests |
| **Research report generator** (PDF built from stored data at request time): study region/period/geometry, datasets and provenance, methodology, trend tables with Z, p, Sen slope and 95% CI, rainfall-adjusted model with sensitivities and caveats, handover reproduction, pixel-trend and layer maps, data-quality table, interpretation, limitations, omitted-sections list, 14 references; report manifest; synthetic data watermark/banner | tests extract the PDF text and check every section |
| Demonstration mode hidden by default; synthetic data always labelled | E2E |

### Pipeline, security, operations
| Feature | Evidence |
|---|---|
| Job status, per-task progress, **cancellation**, **retry of unfinished tasks only**, detailed redacted logs, crash recovery (`interrupted`, temp-file cleanup), **completeness gate** (a series below 50% of expected values is not stored), atomic writes | unit/API tests with mocked Earth Engine incl. cancel mid-task writes nothing |
| Optional API token on all state-changing endpoints; path-traversal-proof identifiers; upload limits; sanitised notes; security headers; tight CORS; redacted logs; generic 500s | tests + live probe (see SECURITY_REVIEW.md) |
| Dependency audits | `pip-audit`: none in app dependencies; `npm audit`: **0** after upgrading react-router-dom and vitest |
| Production launch (API + built UI in one process, token enforced, health, gzip, headers, traversal probes) | **run live**; also unit-tested |
| Clean-environment install: fresh venv, runtime install of 68 pinned packages, full backend suite | **run** (result in section 6) |
| Backup/restore scripts (bash + PowerShell) | **run**: contents, exclusions and checksum verified |
| Health endpoint with operational facts; JSON logging option | tests |

## 2. Improved existing features
Handover-faithful NDVI/IMERG protocols (QA-filtered NDVI kept as sensitivity); `RootMoist_inst` for root-zone soil moisture; monsoon-rainfall control for ET/soil moisture; ellipsoidal area; raw/processed data separation; strict schema validation of stored series; Overview now honours the selected period; job model rebuilt (status set, progress, retry); groundwater upload rebuilt (validated, per-well); tile planner fixed (a single tile no longer split in two); pagination/catalogue extended to 15 datasets.

## 3. Remaining external dependencies (BLOCKED)
| Item | Needs | Implementation state |
|---|---|---|
| Real NDVI/IMERG/LST/ET/soil-moisture extraction and the handover comparison | Earth Engine project + credentials (`python -m app.cli live-check` stops with the exact error today) | code written, **never run against the live service**; pipeline plumbing tested with a mocked extractor |
| Verified Banni grassland polygon | Gujarat Forest Department / Banni Grassland Division survey, or ISRO Bhuvan. Open data checked: OSM (Nominatim, Overpass), Wikidata - **none exists** | import/validation/separate-region handling complete and tested |
| Real Rann-water mask (`water_occurrence`) and `ndvi_nowater` | Earth Engine | masking math tested; extraction code unrun |
| Landsat vegetation investigation on real imagery (tiled 120 m stack, Sep-Oct composites) | Earth Engine | export, tiling and agreement code tested offline; live export unverified |
| Landsat MNDWI water extent for 2023 (JRC ends 2022-01) and salinity-index series | Earth Engine | code written; thresholds unvalidated |
| Salinity validation | measured EC points from the field | tool complete |
| *Prosopis* vs grassland identification | field-labelled points (≥ 10 per class, independent survey) | indicator and validation tool complete; **no classification is attempted** |
| Groundwater trends | CGWB / India-WRIS well data (no automatic download exists) | import/validation/visualisation complete |
| Docker image | a machine with Docker | Dockerfile/compose written, **never built** |
| Live band/mask checks (e.g. MOD13Q1 fill masking, IMERG `time_end − time_start`) | Earth Engine | checklist in DATASET_VERIFICATION.md |

## 4. Scientific limitations (not defects)
- NDVI cannot identify species; a rainfall-adjusted positive NDVI trend does not show *Prosopis* expansion or grassland recovery.
- All handover numbers were computed over the 9,751 km² rectangle, which includes non-grassland land (Rann). They describe the rectangle, not the ≈2,500 km² grassland.
- MOD16 ET uses NDVI/LAI as input (not independent of NDVI); GLDAS is a 0.25° model covering a few cells; neither proves groundwater change.
- LST is skin temperature. IMERG is an ~11 km satellite-gauge estimate.
- n ≈ 24 annual observations: limited power; the handover's decision rule uses a single test at p < 0.05.
- The 10% water-occurrence masking threshold is an analyst choice; the dry-season persistence index is unvalidated; the salinity index and MNDWI threshold are unvalidated proxies.
- JRC water history ends 2022-01; Landsat 7 ends 2024-01; Landsat 5 ends 2012-05.
- Cancellation takes effect between Earth Engine round-trips (a single long server call cannot be interrupted).
- FDR control is approximate for spatially autocorrelated pixels; per-pixel tests ignore serial correlation.

## 5. Dataset availability
| Dataset | Verified in catalogue (2026-11-07) | Retrieved for Banni |
|---|---|---|
| MODIS MOD13Q1 NDVI, GPM IMERG V07, MOD11A2, MOD16A2GF, GLDAS Noah, JRC water (monthly + occurrence), Landsat 5/7/8 L2 | yes (automated) | **no** (Earth Engine blocked) |
| Measured groundwater, field EC, ground-truth labels, grassland polygon | n/a | **no** (external data) |
| Synthetic sample | n/a | generated on demand; hidden by default; labelled everywhere |

## 6. Test results (all executed)
| Suite | Command | Result |
|---|---|---|
| Backend | `cd backend; python -m pytest -q` | **137 passed** |
| Backend in a **clean virtualenv** (runtime deps from scratch + dev deps) | see `scripts` note below | **137 passed** (fresh venv, 68 pinned runtime packages from `requirements.txt`, then dev deps) |
| Frontend types | `npx tsc --noEmit` | exit 0 |
| Frontend component tests | `npm test` | **39 passed** |
| End-to-end (Chromium, own servers) | `npm run e2e` | **22 passed** |
| Production build | `npx vite build` | built |
| Python dependency audit | `pip-audit` | no vulnerable app dependencies (only `pip` itself) |
| JS dependency audit | `npm audit` | **0 vulnerabilities** |
| Metadata verification | `python -m app.cli verify-metadata` | all 10 collections pass |
| Production-mode live probe | curl against a running instance | SPA, deep links, gzip, health (GET/HEAD), 401/200 token behaviour, headers, CORS, traversal - all as intended |
| Backup scripts | run on a temp tree | verified |
| Performance | pixel trends, 171k px × 24 yr | 4.0 s, ~317 MB peak |

Not tested: Earth Engine live calls; Docker build/run; browsers other than Chromium; load testing; third-party penetration test; accessibility audit beyond semantic roles used in tests.

## 7. Security findings
See `docs/SECURITY_REVIEW.md` (18 items). Fixed during this audit: no authentication, store-level path safety, upload hardening, CORS breadth, missing headers, error disclosure, log redaction, 2 vulnerable production JS dependencies. Residual: API open if no token is configured; no rate limiting; no CSP; no per-user authorisation; container image unscanned.

## 8. Deployment readiness
- **Ready:** single-node deployment without Docker (documented, launched and probed); clean install; backups; health checks; logging; token auth.
- **Unverified:** Docker build/run; TLS/proxy configuration (example provided); behaviour under real Earth Engine load.
- **Not done by design:** pushing, committing, releasing, billing - none was performed (the folder is not a git repository).
- **Overall:** ready for a **supervised pilot on a trusted network**; not yet ready to be called production-validated until a real Earth Engine run, the Docker build and the grassland polygon are done.

## 9. How to run the platform
```powershell
# one-time
python -m venv .venv ; .\.venv\Scripts\pip install -r backend\requirements.lock
cd frontend ; npm ci ; cd ..
copy .env.example .env            # edit: GCL_EE_PROJECT (+ GCL_API_TOKEN if shared)

# development (two terminals)
cd backend ; ..\.venv\Scripts\python -m uvicorn app.main:app --port 8000
cd frontend ; npm run dev         # http://localhost:5173

# single process (API + built UI)
cd frontend ; npm run build ; cd ..
$env:GCL_STATIC_DIR="$PWD\frontend\dist"; cd backend ; ..\.venv\Scripts\python -m uvicorn app.main:app --port 8000

# real data, in order (stops at the first failure)
python -m app.cli verify-metadata ; python -m app.cli live-check
python -m app.cli extract ; python -m app.cli quality ; python -m app.cli reproduce ; python -m app.cli water
# then Settings > "Data processing" for the raster stacks (incl. water_occurrence), then Reports > PDF
```
Earth Engine setup (personal Gmail, non-commercial Community tier, **no billing**, API enabled): `docs/SETUP.md` §3-4. Deployment: `docs/DEPLOYMENT.md`.

## 10. Recommended next steps (in order)
1. Authenticate Earth Engine and run the CLI workflow; fill the PENDING sections of `SCIENTIFIC_VALIDATION_REPORT.md` with the real comparison against the handover numbers (do not tune to match).
2. Obtain the Banni boundary polygon from the Forest Department / Bhuvan; rerun for `banni_grassland` and compare with the rectangle.
3. Run the stack jobs (including `water_occurrence`), then the masked pixel trends and the Landsat agreement.
4. Collect field data: georeferenced vegetation labels (≥ 10 per class), EC measurements, CGWB well readings; upload and validate.
5. Build and test the Docker image; add rate limiting and a CSP at the proxy; set `GCL_API_TOKEN`.
6. Have a domain scientist review the interpretation text and the 10% water-mask threshold before publication.
