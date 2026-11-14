# Dataset verification (Task 3)

**Method.** Collection IDs, band names, scale factors, units, resolutions, QA bit definitions and temporal coverage were read from Google's official Earth Engine STAC records (`https://storage.googleapis.com/earthengine-stac/catalog/<provider>/<id>.json`), retrieved **2026-11-07**, and compared with `backend/app/core/catalog.py` and `backend/app/gee/extract.py`. Live confirmation (band names visible to *your* project, mask behaviour) needs Earth Engine access and is a separate, still-**pending** step (`python -m app.cli live-check`).

## Verified from the official catalogue

| Collection | Band(s) used | Catalogue unit | Scale | Resolution | Coverage (catalogue) | Implementation | Verdict |
|---|---|---|---|---|---|---|---|
| `MODIS/061/MOD13Q1` | `NDVI`, `SummaryQA` | – | **0.0001** | 250 m | 2000-02-18 → present | ×0.0001; SummaryQA classes 0 good, 1 marginal, 2 snow/ice, 3 cloudy | ✔ matches |
| `NASA/GPM_L3/IMERG_MONTHLY_V07` | `precipitation` | **mm/hr** | – | 11,132 m | 1998-01 → 2025-09 | rate × 24 × (time_end − time_start) days | ✔ **unit resolved**: mm/hr, so the conversion is correct. Covers 2001-2024 |
| `MODIS/061/MOD11A2` | `LST_Day_1km`, `LST_Night_1km`, `QC_*` | **K** | **0.02** | 1 km | 2000-02-18 → present | ×0.02 − 273.15 → °C; QC bits 0-1 and 6-7 | ✔ matches |
| `MODIS/061/MOD16A2GF` | `ET`, `ET_QC` | **kg/m²/8day** | **0.1** | 500 m | 2000-01-01 → 2025-12-27 | ×0.1 mm per composite; last composite of year is 5 or 6 days (catalogue text) | ✔ matches; composite-length handling is unit-tested |
| `NASA/GLDAS/V021/NOAH/G025/T3H` | `RootMoist_inst`, `SoilMoi0_10cm_inst` | **kg/m²** | – | 27,830 m (0.25°) | 2000-01-01 → present | now `RootMoist_inst` and `SoilMoi0_10cm_inst` | ✔ after change (see below) |
| `JRC/GSW1_4/MonthlyHistory` | `water` (0 no data, 1 not water, 2 water) | – | – | 30 m | **1984-03 → 2022-01-01** | water-class area per month | ⚠ **coverage ends 2022-01**; cannot support 2023 (Cyclone Biparjoy) analyses |

## Discrepancies found and what was done
1. **Root-zone soil moisture band.** The handover uses `RootMoist_inst`; the first implementation summed three `SoilMoi*` layers. *Fixed:* `sm_root` now reads `RootMoist_inst`.
2. **IMERG units.** The earlier assumption (mm/hr) is now *confirmed* by the catalogue. A runtime guard is added anyway: the extractor stores, for each month, the rate, `time_end − time_start` and the calendar day count; the quality report flags a mean annual rainfall outside 50–2000 mm as a possible unit error (unit-tested with a deliberately wrong conversion).
3. **NDVI quality filtering.** The handover applies no `SummaryQA` mask. The platform's `ndvi` series now follows the handover; the stricter `ndvi_qa` (SummaryQA == 0) series is kept as a sensitivity analysis.
4. **JRC water history ends 2022-01-01.** Recorded in the catalogue and the UI limitation text. Surface-water analysis of 2023 needs another source (e.g. Sentinel-2/Landsat water index); not implemented.
5. **Rainfall control for ET and soil moisture.** The handover regresses annual ET and soil moisture on *monsoon* rainfall; the adjusted-analysis endpoint now takes `rain_season` (default monsoon).

## Still to confirm live (cannot be done offline)
- [ ] `verify_dataset_bands()` returns `ok: true` for all six collections in your project.
- [ ] Earth Engine masks the MOD13Q1 fill value (−3000) in `NDVI`: compare pixel counts of the masked vs unmasked image for one month. The handover assumes it does.
- [ ] `system:time_end − system:time_start` equals the calendar month length for every IMERG month (the extractor records `days_agree` per month in `data/raw/`).
- [ ] Number of MOD13Q1 images per month (stored as `n_images` in the raw file) is the expected 1-3.
- [ ] Spot-check three monthly values against the Code Editor.

## Reproducing this verification
```bash
for p in NASA/NASA_GPM_L3_IMERG_MONTHLY_V07 NASA/NASA_GLDAS_V021_NOAH_G025_T3H MODIS/MODIS_061_MOD13Q1 MODIS/MODIS_061_MOD11A2 MODIS/MODIS_061_MOD16A2GF JRC/JRC_GSW1_4_MonthlyHistory; do
  curl -s -L -o "$(basename $p).json" "https://storage.googleapis.com/earthengine-stac/catalog/$p.json"; done
```
Units are under `summaries["eo:bands"][i]["gee:units"]`, scales under `gee:scale`, bit meanings under `gee:bitmask`.

## Automated re-verification (final phase)
`python -m app.cli verify-metadata` re-fetches the catalogue records and checks bands, `gee:units`, `gee:scale`, resolution and temporal coverage for **10 collections** (the six above plus `JRC/GSW1_4/GlobalSurfaceWater` and Landsat 5/7/8 L2). Result on 2026-11-07: **all passed**. Findings: MOD13Q1, IMERG, MOD11A2, MOD16A2GF and GLDAS cover 2001-2024; JRC water products end 2022-01-01; Landsat 7 ends 2024-01-19; Landsat 5 ends 2012-05-05 (so 2012 relies on Landsat 7). The checks are unit-tested against fixtures (network-free).
