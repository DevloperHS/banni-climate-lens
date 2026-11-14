# Final-phase task checklist

Superseded by `FINAL_COMPLETION_REPORT.md`, which carries the authoritative COMPLETE / BLOCKED / NOT IMPLEMENTED status for each item. The legend below is the original planning notation.

Legend: [x] done and tested | [~] implemented, needs external resource | [ ] open

## Phase 1 science
- [~] verified Banni polygon - **no open source exists** (OSM, Wikidata checked); drop-in GeoJSON file with strict validation built
- [x] keep rectangle and grassland separate (separate regions)
- [~] Rann-water masking (JRC occurrence): raster masking tested; EE extraction of `water_occurrence` + `ndvi_nowater` needs credentials
- [x] seasonal NDVI (summer/monsoon/peak, previous-monsoon rainfall control)
- [x] pixel trends + BH-FDR (+ water mask option)
- [~] Landsat investigation: tiled stack export + MODIS/Landsat spatial agreement (tested on synthetic) - real run needs credentials
- [~] Prosopis vs native: exploratory dry-season-persistence indicator + ground-truth validation tool; **no labels exist**, no classification claimed
- [~] salinity: Landsat spectral proxy + field-EC validation tool; no validated salinity product integrated
- [x] groundwater CSV import / validation / per-well visualisation
- [x] Cyclone Biparjoy pre/post incl. rainfall-adjusted comparison; [~] post-2022 water extent needs credentials
- [x] automated metadata verification against the official catalogue (network)

## Phase 2 UI: consistent region/period selectors + data availability, functional features on all 11 pages
## Phase 3 maps: difference maps, regional comparison, map export (PNG/GeoTIFF), raster QC
## Phase 4 multi-variable comparison (correlation matrices, partial correlation, VIF, CV-R2, lagged, anomalies)
## Phase 5 PDF report generator (maps, CIs, quality, references)
## Phase 6 pipeline: progress, cancel, retry, logs, atomic writes, completeness gate
## Phase 7 security + performance: API token, headers, sanitisation, upload limits, audits, benchmarks
## Phase 8 deployment: Dockerfile, compose, production env, health, backup, clean-install test
## Phase 9 tests; Phase 10 FINAL_COMPLETION_REPORT.md
