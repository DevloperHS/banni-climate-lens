# Datasets

Defined in `backend/app/core/catalog.py` (single source of truth; also served by `GET /api/datasets` and shown on the Methodology page). Each stored series records the fields below plus `retrieval_date`, `processing_period` and `processing_config`.

| Key | Earth Engine ID | Provider | Variable | Resolution | Unit | Scale / conversion | Quality filter |
|---|---|---|---|---|---|---|---|
| `ndvi` | `MODIS/061/MOD13Q1` | NASA LP DAAC | NDVI | 250 m, 16-day | dimensionless | ×0.0001 | handover protocol: **none** (EE fill mask only) |
| `ndvi_qa` | `MODIS/061/MOD13Q1` | NASA LP DAAC | NDVI | 250 m, 16-day | dimensionless | ×0.0001 | `SummaryQA == 0` (sensitivity series) |
| `ndvi_landsat` | `LANDSAT/LT05,LE07,LC08,LC09/C02/T1_L2` | USGS/NASA | NDVI from SR | 30 m, annual Sep–Oct median | dimensionless | SR = DN×0.0000275 − 0.2 | `QA_PIXEL` bits 1,3,4,5 clear |
| `precip` | `NASA/GPM_L3/IMERG_MONTHLY_V07` | NASA GES DISC | `precipitation` | 0.1°, monthly | mm/month | mm/hr × 24 × days in month | product-level |
| `lst_day` | `MODIS/061/MOD11A2` | NASA LP DAAC | `LST_Day_1km` | 1 km, 8-day | °C | ×0.02 K − 273.15 | `QC_Day` bits0-1 ∈{0,1}; bits6-7 ≤ 1 (≤2 K) |
| `lst_night` | `MODIS/061/MOD11A2` | NASA LP DAAC | `LST_Night_1km` | 1 km, 8-day | °C | as above | `QC_Night` same rule |
| `et` | `MODIS/061/MOD16A2GF` | NASA LP DAAC / UMT | `ET` | 500 m, 8-day gap-filled | mm/month | ×0.1 kg m⁻² per composite; daily rate × days | DN > 32700 masked |
| `sm_surface` | `NASA/GLDAS/V021/NOAH/G025/T3H` | NASA GSFC | `SoilMoi0_10cm_inst` | 0.25°, 3-hourly | kg m⁻² (≈ mm) | 1 | model output |
| `sm_root` | same | NASA GSFC | `RootMoist_inst` | 0.25° | kg m⁻² (≈ mm) | 1 | model output |
| `water_extent` | `JRC/GSW1_4/MonthlyHistory` | EC JRC / Google | `water` (class 2) | 30 m, monthly | km² | pixel-area sum | months with <50% valid coverage dropped; **catalogue coverage ends 2022-01-01** |
| `groundwater` | user CSV (CGWB / India-WRIS) | CGWB | depth to water | wells | m b.g.l. | 1 | none automatic |

## Processing rules (implemented in `science/processing.py`, tested)
- **Composites → months**: each composite is assigned to the month containing its midpoint.
  - NDVI, LST: mean of valid composites in the month.
  - ET: composite totals are converted to a daily rate using the true composite length (8 days; 5 or 6 for the final composite of the year), averaged, and multiplied by days in month. A constant 1 mm/day input reproduces exactly `days_in_month` mm (unit test).
- **IMERG**: the monthly product's rate is converted with the actual number of days (leap years handled).
- **GLDAS** 3-hourly fields are averaged per calendar month server-side; root zone = the model's `RootMoist_inst` band (as in the handover).
- **JRC water**: area of class "water" per monthly image; months with less than half of the region optically observed are dropped (not zero-filled).
- **Missing data** are `null` in stored series, never interpolated. Annual/seasonal values require full coverage for sums and ≥75% of months for means (`timeseries.MIN_COVERAGE`).
- **Landsat**: one Sep–Oct composite per year stored in the October slot; years without clear scenes are absent.

## Limitations by dataset
- **NDVI** is a greenness index; it saturates at high canopy cover and mixes species. It cannot identify *Prosopis juliflora* versus native grasses.
- **Landsat** TM/ETM+/OLI differ radiometrically (no harmonisation applied); ETM+ after 2003 has SLC-off gaps; monsoon cloud limits clear scenes.
- **IMERG** is a satellite-gauge estimate; ~11 km cells; biases in arid regions possible.
- **LST** is skin temperature (clear-sky only), not air temperature; day/night overpass times differ.
- **MOD16 ET** is a model driven by reanalysis meteorology; low skill in arid land; not a measurement.
- **GLDAS** is a land-surface model at 0.25° - roughly 4×3 cells over the Banni box. Coarse by construction. It is not observed soil moisture.
- **JRC water**: cloud gaps; salt crust and very shallow water can be misclassified.
- **Groundwater**: point measurements; spatial representativeness depends on the well network. ET/GLDAS must never be used to infer groundwater trends.
- **Salinity**: no satellite product is integrated.

## Banni region
Bounding box 23.20–23.95 °N, 68.80–69.95 °E. The WGS84 ellipsoidal area of the rectangle is **9,751 km²** (verified by numerical integration of the ellipsoid; an earlier figure of 9,727 was slightly off). The 9,751 km² figure is the rectangle's area, not Banni grassland area. Published grassland-area figures (about 2,497–2,618 km²) must not be presented as the rectangle area. The platform treats the rectangle purely as the analysis window. Replace it with the true boundary polygon if one is available (extend `regions.json` and `_geom()` in `gee/extract.py`).


Units, scale factors, band names and coverage were verified against the official Earth Engine catalogue on 2026-11-07: see `DATASET_VERIFICATION.md`.

## Additional series and rasters (final phase)
| Key | Source | What it is | Status |
|---|---|---|---|
| `ndvi_nowater` | MOD13Q1 + `JRC/GSW1_4/GlobalSurfaceWater` (`occurrence`) | handover NDVI with pixels of long-term water occurrence ≥ 10% removed | code written; needs Earth Engine |
| `water_occurrence` (static raster) | `JRC/GSW1_4/GlobalSurfaceWater` | mask layer on the same grid as the NDVI stack | code written; needs Earth Engine |
| `water_extent_mndwi` | Landsat 8/9 SR | monthly water area from MNDWI > 0 (covers 2013+, including 2023) | code written; unvalidated generic threshold; needs Earth Engine |
| `salinity_index` | Landsat SR (TM/ETM+/OLI) | SI1 = √(Green × Red), Mar-May median composite | proxy; **unvalidated** until field EC is supplied |
| `ndvi_landsat` stack | Landsat SR | Sep-Oct NDVI composite at 120 m (tiled export) for resolution-agreement analysis | code written; needs Earth Engine |

All collection IDs, bands, units, scale factors, resolutions and coverage were verified against Google's catalogue by `python -m app.cli verify-metadata` (all 10 collections passed on 2026-11-07). Landsat 7 coverage ends 2024-01-19 (later years rely on Landsat 8/9); JRC water products end 2022-01-01.

User-supplied data: measured groundwater (CGWB / India-WRIS), field EC, ground-truth labels. None ship with the project.
