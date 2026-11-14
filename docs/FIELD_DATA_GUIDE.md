# Field data guide

Three datasets cannot come from satellites and are **not available in this project**. Until they are supplied, the corresponding analyses stay **BLOCKED / NOT VALIDATED**; the platform never fabricates them. Header-only templates are in `data-templates/` (they contain no example rows on purpose).

Check a file **before uploading** (offline, no Earth Engine, nothing stored):
```powershell
cd backend
python -m app.cli validate-csv ground-truth ..\my_labels.csv     # exit 0 = sufficient, 9 = insufficient, 8 = invalid
python -m app.cli validate-csv field-ec     ..\my_ec.csv
python -m app.cli validate-csv groundwater  ..\my_wells.csv
```
Upload in the app (Vegetation > Prosopis investigation, Water Resources > Salinity / Groundwater) or via the API (`POST /api/spatial/ground-truth`, `/api/salinity/field-ec`, `/api/datasets/upload`; send the API token if one is configured).

## 1. *Prosopis* vs native grassland labels
| | |
|---|---|
| File | CSV `lat,lon,class` (WGS84 decimal degrees). Classes are free text (e.g. `prosopis`, `grass`, `bare`, `water`); use consistent lower-case names |
| Minimum | **≥ 10 valid points per class** for any statistic to be reported (classes below that are listed but not scored) |
| Sampling | Independent of the satellite indicator. Stratified random across the study area is best. Avoid sampling where the map "looks like" Prosopis (circular) and avoid clusters of neighbouring points |
| Ground truth quality | Visited in the field by someone able to identify *Prosopis juliflora*, or verified on very-high-resolution imagery with a documented protocol. Record date and observer outside this file |
| What you get | per-class distribution of the dry-season persistence index, pairwise ROC-AUC with a bootstrap 95% CI, Mann-Whitney p. **Not** a classification map or an accuracy assessment of one |
| Rejected / warned | out-of-range coordinates, empty class, exact duplicate points (removed); < 10 points in a class (warning; class not scored) |
| Caveat | Spatial autocorrelation makes the intervals optimistic; a good AUC is evidence for further work, not a validated species map |

## 2. Soil / water electrical conductivity (salinity validation)
| | |
|---|---|
| File | CSV `lat,lon,ec` with `ec` in **dS/m** (0-500) |
| Minimum | **≥ 10 valid points**; otherwise the salinity index stays **UNVALIDATED** |
| Notes | State depth, soil vs water, and date in your own records. The proxy (Landsat SI1, dry-season composite) is compared with the multi-year mean at each point, so match the season (Mar-May) and avoid points that changed land use |
| What you get | Spearman ρ with an approximate 95% CI and p; the message is conservative when the relationship is weak. Validity applies only to similar soils, dates and depths |

## 3. Groundwater (CGWB / India-WRIS)
| | |
|---|---|
| File | CSV `date,value[,well_id]`; `value` = **depth to water level in metres below ground level** (larger = deeper) |
| Source | Central Ground Water Board or India-WRIS well data for wells inside/near the study region. No automatic download exists in this project |
| Validation applied | dates parseable and after 1950, not in the future; depth 0-300 m; duplicates per well/date removed; step changes flagged (pumping, well deepening, datum change); well ids sanitised |
| Analysis | per-well Mann-Kendall + Sen on annual means with BH-FDR across wells; combined series = mean of per-well anomalies + grand mean. At least 8 readings per well are needed for a per-well trend |
| Interpretation | An **increasing** depth trend means a deepening water table. Groundwater conclusions must come from these measurements, never from ET or modelled soil moisture |

## What "sufficient" does and does not mean
Reaching the minimum counts allows the platform to *compute* a statistic; it does not make the result a validation. A domain scientist should review the sampling design before any claim is published.
