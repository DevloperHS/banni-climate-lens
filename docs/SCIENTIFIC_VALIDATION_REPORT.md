# Scientific validation report

**Status as of 2026-11-07: validation is INCOMPLETE. No real satellite data has been retrieved and no handover number has been reproduced.** Earth Engine could not be authenticated in the development environment (no project ID, no credentials). Sections marked **PENDING** are placeholders to be filled from a real run; nothing in them is an estimate.

## 1. Summary by task

| Task | Status | Evidence |
|---|---|---|
| 1. Compare implementation with the handover | **Done** | §2; handover read in full (15 pp.) |
| 2. Validate geographical boundaries | **Partly done** | §3: areas verified; **no authoritative polygon found**; polygon support built |
| 3. Verify dataset metadata | **Done offline; live part pending** | `docs/DATASET_VERIFICATION.md` |
| 4. Earth Engine authentication | **Attempted - failed** | §4: exact error recorded |
| 5. Real NDVI/IMERG extraction | **Not run** (blocked by 4) | – |
| 6. Reproduce handover statistics | **Not run** (blocked by 5); machinery tested on planted data | §6 |
| 7. ET and soil moisture | **Not run** (blocked by 5) | – |
| 8. Connect real results to the app | **App side done**; no real data to show | §7 |
| 9. Final validation | **Software tests done**; scientific validation pending | §8 |

## 2. Handover vs implementation (Task 1)

| # | Item | Handover | Implementation before | Now |
|---|---|---|---|---|
| 1 | Geometry | rectangle 23.20-23.95 N, 68.80-69.95 E (all scripts) | same | same; polygon supported separately |
| 2 | NDVI QA | none | SummaryQA == 0 | `ndvi` = handover; `ndvi_qa` sensitivity |
| 3 | NDVI month assignment/aggregation | mean image of composites dated in month, then regional mean | regional mean per composite, month by midpoint | `ndvi` = handover |
| 4 | Rain conversion | rate × 24 × (end − start) days | rate × 24 × calendar days | handover form, with day-count check |
| 5 | Monsoon aggregation | NDVI mean / rain **sum** of available Jun-Sep months | required ≥3/4 (mean) or 4/4 (sum) | reproduction module uses handover rule |
| 6 | Trend test | Hamed-Rao + Sen (always) | MK + HR, HR recommended conditionally | reproduction runs pymannkendall directly; engine cross-checked |
| 7 | Regression | OLS NDVI ~ monsoon rain; residual trend | same | same + sensitivities S1-S5 |
| 8 | ET annual | sum of composites × 0.1 | sum of rate-based monthly totals | small known difference (documented) |
| 9 | ET / SM control | monsoon rainfall | same-season rainfall | `rain_season` (default monsoon) |
| 10 | Root-zone SM | `RootMoist_inst` | 0-100 cm layer sum | `RootMoist_inst` |
| 11 | SM aggregation | mean of all 3-hourly images | mean of monthly means | small known difference (documented) |
| 12 | Interpretation | "matches Prosopis"; water table = hypothesis | association only; no species claim | unchanged (consistent with handover's own caution) |

Handover next-steps (p.14) status: LST day/night separate (done); summer NDVI (available via `agg=summer`, not made default); FDR pixel map (done); Landsat cross-check (done in code, untested on real data); exclude Rann-water pixels with the JRC mask (**not implemented**) and mark the Biparjoy year (event study done); groundwater as hypothesis unless CGWB data (done); first-screen message, plain p-value wording, zones of Prosopis vs grass (**not implemented**; Prosopis mapping needs ground truth).

## 3. Geometry (Task 2)

- Rectangle area (WGS84 ellipsoid): **9,751.3 km²**, confirmed by independent numerical integration of the ellipsoid (agreement 0.01 km²; unit test). A figure of 9,727 km² was quoted earlier in the project; it was ≈0.25% low. A spherical formula gives 9,774 km² (+0.2%).
- The handover labels the rectangle "~2,618 km²". That cannot be its area. Published figures for the Banni grassland: ≈2,497 km² (Forest Department GPS survey 2005-06, via Deccan Herald), ≈2,617 km² (Sahapedia), ≈2,465 km² (Banni Protected Forest working plan, quoted in a search summary - **not individually verified**). So 2,618 km² most plausibly refers to the grassland.
- **Consequence:** every handover number (p = 0.0059 etc.) was computed over the 9,751 km² rectangle, which includes Rann salt flats and other non-grassland land. The headline conclusion therefore concerns the rectangle, not the grassland.
- **Boundary source:** OSM Nominatim returned nothing; Overpass queries timed out; no downloadable authoritative polygon was found. *Not fabricated.* To obtain one: Gujarat Forest Department / Banni Grassland Division (boundary demarcation survey, pillars and trenches are documented in tribunal filings) or ISRO Bhuvan. Drop the GeoJSON at `backend/app/config/geometries/banni_grassland.geojson` with `source`, `retrieved`, `license`; it becomes a separate region `banni_grassland` with its own results and provenance.
- Every stored series now records the geometry id, source and area; the Overview page states which geometry is in use and shows a warning while the polygon is pending.

## 4. Earth Engine authentication (Task 4) - result

Command: `python -m app.cli live-check` (exit code 2). Output (verbatim):

```
project_configured: false   auth_mode: null   initialised: false   verified: false
error: "GCL_EE_PROJECT is not set. Earth Engine is not available. Configure ONE of: (A) service account ... or (B) local development - run `earthengine authenticate` then set GCL_EE_PROJECT. See docs/SETUP.md."
STOP: Earth Engine is not verified. No data was requested and nothing was written.
```
No `.env`, no environment variables and no stored Earth Engine credentials were present on the machine. `data/processed/` and `data/raw/` are empty.

## 5. Extraction (Task 5) - PENDING
Run `python -m app.cli live-check`, then `python -m app.cli extract`. To be recorded here:

| Item | Value |
|---|---|
| Run timestamp / project | PENDING |
| Geometry | handover_bbox (9,751.3 km²) |
| NDVI: months valid / expected, images per month | PENDING |
| IMERG: months valid / expected, `days_agree` all true? | PENDING |
| Mean annual rainfall (plausibility 50-2000 mm) | PENDING |
| Missing months list | PENDING (`python -m app.cli quality`) |
| Raw files | `data/raw/banni/*.json` |

## 6. Reproduction of the handover statistics (Task 6)

**Software validated on planted data (done, tested):** the reproduction module equals the handover's Colab cell run verbatim (same p, Z, slope, R²), the platform's own engine agrees with pymannkendall to 1e-8, and the comparison logic labels exact / partially matching / opposite results as *reproduced* / *consistent* / *not reproduced*.

**Real comparison: PENDING.** Values to be compared (from the handover):

| Quantity | Handover | Computed |
|---|---|---|
| Mean NDVI 2001 / 2023 (all images) | 0.16668 / 0.27505 | PENDING |
| Monsoon NDVI trend (Hamed-Rao) | increasing, p = 0.0001, +0.00495 /yr | PENDING |
| Monsoon rainfall trend | no trend, p = 0.0561, +15.71 mm/yr | PENDING |
| NDVI ~ rain residual trend | increasing, p = 0.0059, +0.0017 /yr, Z = 2.753 | PENDING |
| ET annual raw / residual | p = 0.0122, +5.0 mm/yr / p = 0.0350, +1.44 mm/yr | PENDING |
| Root-zone SM raw / residual | p = 0.8427 / p = 0.2824 | PENDING |

If a value differs, investigate in this order: (1) geometry; (2) QA filtering (`ndvi` vs `ndvi_qa`); (3) month assignment; (4) IMERG unit/day count (`days_agree`, plausibility flag); (5) missing months; (6) product reprocessing since the handover; (7) rounding in the handover (e.g. p = 0.0001 may be < 0.0001). Record the explanation here; do not tune to match.

## 7. Application state (Task 8)
- Default experience shows only processed observations. The synthetic sample is hidden unless *Demonstration mode* is enabled in Settings, and is badged SYNTHETIC wherever it appears.
- Statistics page: handover-reproduction table (reported vs computed, status), data-quality panel (completeness, missing months, plausibility flags, geometry, retrieval date, raw files).
- With no real data the pages show explicit empty states. Once `extract`/`water` jobs finish, the existing pages populate; raster layers need the stack jobs (Settings).

## 8. Software tests (Task 9)
See `docs/TEST_RESULTS.md` for counts. New tests cover: handover protocol vs verbatim script; comparison statuses; reference values; catalogue facts verified against the official metadata (IMERG mm/hr, RootMoist, scale factors, JRC end date); ellipsoidal area vs independent integration; polygon validation and separate-region registration; provenance completeness (geometry, units, dates); series schema validation; reproducible extraction with raw/processed separation (mocked Earth Engine); data-quality missing-month and unit-error detection; CLI stops without credentials.

## 9. Remaining limitations
- Real-data validation not performed; Earth Engine code remains unverified against the live service.
- Results describe the rectangle, not the grassland, until a polygon is supplied.
- NDVI cannot identify species; a positive rainfall-adjusted trend is not evidence of *Prosopis*. MOD16 ET uses NDVI/LAI as inputs, so ET is not independent of NDVI. GLDAS is a 0.25° model (a few cells here) and cannot see *Prosopis* or pumping. Groundwater decline remains a hypothesis without CGWB/India-WRIS well data.
- Annual tests use n ≈ 24: low power; the handover's decision rule is p < 0.05 and slope > 0 on a single test.
- JRC monthly water history ends 2022-01; Biparjoy surface-water effects are not assessable with it.
- Rann-water pixel masking, Prosopis/grass zone mapping and species classification are not implemented.

## 10. Update - final phase: boundary search (Phase 1)
A second, broader search for a machine-readable Banni boundary was made on 2026-11-07: OSM Nominatim (four queries: "Banni Grassland", "Banni Kachchh", "Banni Reserve Gujarat", "Banni Protected Forest") returned no results; Wikidata has an entity "Banni Grasslands Reserve" (Q1747332) with a point coordinate (23.55 N, 69.27 E) but **no OSM relation and no geoshape**; an Overpass query for ways/relations whose name starts with "Banni" inside the study window returned **no elements**; other protected areas in the window (Kachchh Desert WLS, Narayan Sarovar Sanctuary) are different polygons and were not used. **No authoritative polygon is obtainable from open data services.** The item remains **BLOCKED** on the Gujarat Forest Department (Banni Grassland Division demarcation survey) or ISRO Bhuvan. Everything downstream is ready: drop the validated GeoJSON into `backend/app/config/geometries/` and run the same jobs for `banni_grassland`.
