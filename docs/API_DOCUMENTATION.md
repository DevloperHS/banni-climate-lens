# API reference

Interactive OpenAPI docs: `http://127.0.0.1:8000/docs` (schema at `/openapi.json`).

## Conventions
- Analysis endpoints return `{ "result": ..., "meta": ... }`. `meta` has `region`, `variable`, `kind` (`observed` | `user-supplied` | `synthetic`), `synthetic` (bool), `disclaimer`, and `dataset` provenance (id, provider, resolution, unit, scale factor, quality filter, period, retrieval date, limitations).
- Errors: `{ "error": { "code", "message", "details" } }` with HTTP 404 `no_data`, 422 `validation_error` / `insufficient_data` / `bad_*`, 503 `earth_engine_unavailable`, 500 `internal_error`.
- Common query parameters: `region` (default `banni`), `source` (`processed` | `sample`, default `processed`), `start`, `end` (years), `agg`.
- `agg` values: `monthly`, `annual`, `summer`, `monsoon`, `postmonsoon`, `winter`, `peak`.
- Read endpoints never call Earth Engine. Only `POST /api/datasets/jobs` does.

## Authentication
If the server runs with `GCL_API_TOKEN`, every state-changing endpoint (marked **W** below) needs `Authorization: Bearer <token>`; otherwise 401 `unauthorized`. Read endpoints never need a token.

## Health
| | |
|---|---|
| `GET /api/health` (+`HEAD`) | status, version, data-dir writable, free disk, active jobs, auth/EE configuration |
| `GET /api/health/earthengine?probe=false` | configuration status; `probe=true` attempts a real Earth Engine call |

## Regions
`GET /api/regions` · `GET /api/regions/{id}` · `GET /api/regions/{id}/boundary` (GeoJSON Feature)

## Datasets
| | |
|---|---|
| `GET /api/datasets?region&source&page&page_size` | catalogue with availability, kind, period, rasters (paginated) |
| `POST /api/datasets/jobs` **W** | body `{region, start, end, tasks:[{type:"series"\|"stack", key, season?}]}` → 202 job; 503 if Earth Engine is unavailable. Stack seasons include `static` (only for `water_occurrence`) |
| `GET /api/datasets/jobs`, `GET /api/datasets/jobs/{id}` | job status; `progress {done,total,percent}`; per-task `status/attempts/error/detail` |
| `GET /api/datasets/jobs/{id}/log` | redacted log with tracebacks of failed tasks |
| `POST /api/datasets/jobs/{id}/cancel` **W** | cooperative cancel; cancelled tasks write nothing |
| `POST /api/datasets/jobs/{id}/retry` **W** | re-run unfinished tasks (409 if the job completed) |
| `GET /api/datasets/quality?variable` | completeness, missing months, plausibility flags, geometry, raw files |
| `POST /api/datasets/sample?region` / `DELETE /api/datasets/sample` **W** | generate / remove the **synthetic** sample |
| `POST /api/datasets/upload` **W** | multipart: `region`, `key=groundwater`, `source`, `file` (CSV `date,value[,well_id]`); returns the validation report. Errors: 413 too large, 422 invalid |

## Variable groups
Groups share one implementation: `/api/vegetation` (`ndvi`, `ndvi_landsat`), `/api/rainfall` (`precip`), `/api/temperature` (`lst_day`, `lst_night`), `/api/water` (`et`, `sm_surface`, `sm_root`, `water_extent`, `groundwater`). Pass `variable=`.

| Endpoint (prefix = group) | Returns |
|---|---|
| `GET /variables` | variables and availability |
| `GET /timeseries?agg` | `{x, values, unit, frequency}` |
| `GET /trend?agg&alpha` | Mann-Kendall + Hamed-Rao + Sen (slope, CI), autocorrelation, recommended test, interpretation, limitations, fitted line |
| `GET /anomalies?agg` | anomaly, z, flag (|z|>2) |
| `GET /monthly-pattern` | per-month mean/sd/min/max |
| `GET /seasonal-comparison` | per-season series and trend |

Extras: `GET /api/vegetation/landsat-comparison`, `GET /api/water/investigations` (status of surface water, salinity, groundwater, cyclone work).

## Statistics
| | |
|---|---|
| `POST /api/statistics/trend` | body `{values, times?, alpha}`; trend tests on supplied data |
| `GET /api/statistics/rainfall-adjusted?response&season` | model, residuals, residual trend, sensitivity S1–S5, diagnostics, caveats, verdict |
| `GET /api/statistics/regression?y&x=a,b&agg` | OLS (≤3 predictors) with CI, HAC, diagnostics, residual trend |
| `GET /api/statistics/correlation?a&b&agg&detrend` | Pearson (CI), Spearman |
| `GET /api/statistics/event?variable&event_id&pre_months&post_months` | placebo-year event study |

## Spatial
| | |
|---|---|
| `GET /api/spatial/layers` | available raster stacks: years, bounds, CRS, colour range |
| `GET /api/spatial/layer.png?variable&season&year` (or `product=mean`) | colourised PNG for a Leaflet overlay |
| `GET /api/spatial/pixel-trend?variable&season&start&end&q` | counts (FDR vs uncorrected), method, limitations |
| `GET /api/spatial/pixel-trend.png?product=class\|slope\|uncorrected` | map image |
| `GET /api/spatial/pixel-trend.tif` | 5-band GeoTIFF (EPSG:4326) |
| `GET /api/spatial/inspect?lat&lon&variable&season` | pixel time series (+ exploratory trend) |

## Reports and exports
| | |
|---|---|
| `GET /api/reports/insights` | findings generated from computed results, with texts for researcher / authority / student / community |
| `GET /api/reports/export/csv?variable&agg` | CSV with provenance header comments |
| `GET /api/reports/export/geojson` | boundary Feature with computed trend statistics |
| `GET /api/reports/pdf` | PDF: question, area, findings, charts, regression table, sensitivities, limitations, provenance table |

Chart PNG downloads are produced client-side from the rendered chart (synthetic charts are stamped).

## Final-phase endpoints
| | |
|---|---|
| `GET /api/water/groundwater/wells` | per-well series, upload validation report, per-well Mann-Kendall/Sen with BH-FDR |
| `GET /api/salinity/{variables,timeseries,trend,anomalies,monthly-pattern,seasonal-comparison}` | salinity-proxy series (group router) |
| `POST /api/salinity/field-ec` **W** | CSV `lat,lon,ec[,year]` (dS/m) |
| `GET /api/salinity/validation` | Spearman of proxy vs measured EC; `no_field_data` / `insufficient` / `computed` |
| `POST /api/spatial/ground-truth` **W** | CSV `lat,lon,class`; validated (≥2 classes; warnings under 10 per class) |
| `GET /api/spatial/ground-truth/status` | whether labels exist and what is required |
| `GET /api/spatial/evergreen`, `/evergreen.png?product=mean\|trend` | exploratory dry-season persistence indicator, pixel trend (FDR), optional `mask=rann_water` |
| `GET /api/spatial/indicator-validation` | class separability (AUC + bootstrap CI); 404 `no_ground_truth` without labels |
| `GET /api/spatial/pixel-trend{,.png,.tif}?mask=rann_water&water_thr=10` | water-masked pixel statistics; GeoTIFF tags record the mask and geometry |
| `GET /api/spatial/difference{,.png}` | mean(B) − mean(A) change map with summary |
| `GET /api/spatial/export.png?kind=layer\|trend\|difference` | publication-style map image (axes, legend, CRS, provenance footer; watermark if synthetic) |
| `GET /api/spatial/layer.tif` | single-year or mean layer as GeoTIFF |
| `GET /api/spatial/trend-agreement` | fine (Landsat) vs coarse (MODIS) trend agreement on the coarse grid |
| `GET /api/spatial/qc` | raster quality control report (CRS, pixel shape, extent, band years, valid fraction) |
| `GET /api/statistics/compare?variables=a,b,c&response=&detrend=` | correlation matrices (BH-adjusted), partial correlations, regression + VIF, leave-one-out R², lagged correlations, coincident anomalies |
| `GET /api/statistics/region-comparison?regions=` | same variable over different geometries |
| `GET /api/statistics/event?adjust_rain=true` | raw and rainfall-adjusted event study |
| `GET /api/statistics/rainfall-adjusted?rain_season=monsoon\|annual\|prev_monsoon...` | choose the rainfall aggregate used as predictor |
| `GET /api/reports/manifest` | which report sections are available and what each needs |
| `GET /api/reports/pdf?maps=true` | full report (see METHODOLOGY/FINAL report for contents) |
