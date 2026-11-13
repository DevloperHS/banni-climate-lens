# Report: Prosopis random forest and NDVI trend by Prosopis share (banni_rf.js)

Run 2026-11-13 in the Earth Engine Code Editor on project `banni-trend-2026`, cross-checked with the Python API.
All numbers below come from files in `results/`; nothing is typed in by hand.

## 1. Answer in one paragraph

Greening is **not confined to Prosopis**. Monsoon NDVI rose significantly from 2001 to 2024 both in MODIS pixels that are
mostly Prosopis woodland in 2023 (+0.0063 per year, p = 0.002) and in pixels with almost no Prosopis (+0.0048 per year,
p = 0.0003). Both stay significant after removing the rainfall effect, with CHIRPS (p = 0.021 and 0.003) and with IMERG
(p = 0.027 and 0.004). The high-Prosopis pixels rise somewhat faster, but the difference is not significant
(p = 0.063). By the rule in the task brief ("if the trend is in both, the reason is something else"), Prosopis
woodland does not explain the greening on its own; something that also acts on grass, mixed and saline-brush pixels does.
The data cannot yet say what: the classifier has no cropland class, and "low Prosopis in 2023" does not mean "no
Prosopis ever".

## 2. What was checked before starting (main, ashutosh, harsh)

| Claim in the research update | Verdict | Evidence |
|---|---|---|
| p = 0.0059, +0.0017/yr reproduced | True | All 9 handover figures reproduce from `data/processed` |
| Data is real, not placeholder | True | Retrieval metadata, live runs, exact reproduction |
| Old values in docs were wrong | True | Fixed on branch `ashutosh` (commit f0fd30d); now also in `main`'s working tree (not committed) |
| No well data; `water_table` file is ET + soil moisture | True | Its provenance also wrongly said NDVI: code fixed in `backend/app/gee/extract.py`, test added |
| Box is 9,751 km2, Banni about 2,500 km2 | True | `regions.json`, published figures |
| Dense Prosopis 1.4 % (2014) to 13.8 % (2023) | Not verifiable | Not in the Zenodo files; Mongabay's account of the same study gives about +2,000 ha. This run's own 2023 map gives 11.6 % Prosopis woodland in the script's ROI, a similar order for 2023, but no 2014 value exists here |
| Wet years like 2020 confuse NDVI | Partly | 2020 is the wettest monsoon in both rainfall sets (CHIRPS 524 mm, IMERG 1,001 mm) |

Branch `harsh` had no commits, i.e. this Earth Engine task had not been done.

## 3. Training points (task step 2)

* 378 candidate locations were proposed from ESA WorldCover 2021 and the same Sentinel-2 composite the script uses, then
  **each was judged by eye** on a ~330 m chip of Esri World Imagery (~1.1 m pixels) with the script's 20 m buffer drawn.
  Decisions: 159 accepted or relabelled, the rest rejected (edges, tracks, fields, villages, ambiguous).
  Record: `labelling/visual_labels.csv`.
* Labels were calibrated on the 10 Zenodo field sites (Bhan 2024, doi:10.5281/zenodo.11197850): saline brushland = pale
  open flats with sparse low shrubs; mixed = scattered Prosopis shrubs over grass or bare ground.
* Points closer than 150 m to each other or to a Zenodo site were dropped, so one patch is not counted twice.
* Final: **39 Prosopis woodland, 34 mixed, 53 wetland/water, 33 saline brushland** (all >= 30).
  `labelling/training_points.csv`, pasted into the Code Editor as `gee/manual_points.js`.
* Imagery used was Esri World Imagery, not the Google basemap named in the brief (Google's imagery cannot be read
  programmatically); both are sub-metre composites of similar date.

## 4. Classifier accuracy (task step 3)

| Measure | Overall accuracy | Kappa |
|---|---|---|
| Code Editor, script as written (30 % of **pixels** held out), run 1 | **0.966** | **0.948** |
| Code Editor, same script, later runs | 0.961 | 0.948 / 0.954 |
| Python cross-check, same script | 0.960 - 0.965 | 0.946 - 0.953 |
| Stricter: 30 % of **locations** held out, 5 seeds (`scripts/06`) | **0.763** (0.720 - 0.816) | 0.682 |

Screenshot of the console: `results/code_editor_console_accuracy.jpg`.

**Read this carefully.** The script's 96 % passes the 80 % bar, but its test pixels sit next to training pixels inside
the same 20 m or 60 m buffer, so it mostly measures how alike neighbouring pixels are. Holding out whole locations gives
**76 %**, below the bar. Per class under that stricter test, Prosopis woodland is the reliable class (recall 0.63 - 1.00,
precision 0.71 - 0.98 across seeds) and water is near perfect; the weak point is **mixed vs saline brushland**, which the
model confuses often. Small run-to-run differences (0.961 vs 0.966) come from Earth Engine's sampling, not from changes.

Field-site problems in the script's own table (`banni_rf.js` step A):
* LTM_10, LTM_18 and LTM_26 do not meet the script's own ">= 65 % dominant class" rule in the 2023 field counts
  (64.5 %, 59 %, 56 %); LTM_11 and LTM_23 do meet it but are not used.
* LTM_29 is labelled saline brush (field count 121/121) but the imagery shows dense woody canopy on the point.
* LTM_36 lies on a railway line; LTM_10 is beside a village and a pond.

## 5. The export bug, and how the CSV was made (task step 4)

`banni_rf.js` as received **cannot export its table**. The export fails with
`Reprojection output too large (14637x5634 pixels)`; adding `tileScale` gives `User memory limit exceeded`, and
exporting MODIS-grid fractions straight from the classifier gives `Execution failed; out of memory`. Cause: the script
recomputes the 10 m random-forest map on MODIS's sinusoidal grid inside the 24-year loop, and that grid is strongly
slanted at 69 E, so each request needs a ~146 km wide block of the 10 m map.

Fix, with no threshold or reduction changed:

1. `gee/stage1_classmap.js`: steps A-C unchanged; the 2023 class map is exported once as an asset at its native 10 m UTM
   grid (`projects/banni-trend-2026/assets/banni_rf_classmap_2023`, about 6.8 EECU-hours).
2. `gee/stage2_table.js`: step D unchanged except that it reads the stored map and adds `tileScale: 16` to the two MODIS
   reductions. Exported to Drive as `banni_ndvi_by_prosopis_chirps.csv` (root of the signed-in account).

The Drive CSV was opened from Drive and saved locally; a full-precision recomputation from the same asset matches it to a
relative difference of 4e-10. Local copies: `data/extras/prosopis_rf/` and `results/`.

## 6. Results

### Class shares, 2023 (script ROI 69.0 - 69.9 E, 23.4 - 23.9 N)

| Class | Share |
|---|---|
| Prosopis woodland | 11.6 % |
| Mixed Prosopis + grass | 45.9 % |
| Wetland / water | 13.6 % |
| Saline brushland | 29.0 % |

MODIS pixels: 8,763 "high Prosopis" (share > 0.4; on average 65 % woodland, 33 % mixed) and 43,105 "low Prosopis"
(share < 0.05; about half mixed, half saline brush). Map: `results/rf_classmap_2023.png`.

### Trends 2001-2024 (Hamed-Rao Mann-Kendall + Sen slope; `results/trend_tests.json`)

| Series | Trend | With CHIRPS rain removed | With IMERG rain removed |
|---|---|---|---|
| Monsoon NDVI, high-Prosopis pixels | +0.0063/yr, p = 0.002 | +0.0034/yr, p = 0.021 (R2 rain 0.59) | +0.0032/yr, p = 0.027 |
| Monsoon NDVI, low-Prosopis pixels | +0.0048/yr, p = 0.0003 | +0.0029/yr, p = 0.003 (R2 rain 0.59) | +0.0026/yr, p = 0.004 |
| Gap, high minus low | +0.0015/yr, **p = 0.063 (not significant)** | | |
| CHIRPS monsoon rain | +7.3 mm/yr, p = 0.21 (not significant) | | |

The second method (NDVI ~ rain + year) agrees: year term +0.0041/yr (p = 0.006) for high and +0.0033/yr (p = 0.0005) for
low pixels with CHIRPS.

### CHIRPS vs IMERG

Year-to-year they agree closely (r = 0.95), but IMERG's totals are about 1.8 times CHIRPS's (mean 526 vs 288 mm;
2020: 1,001 vs 524 mm). The areas differ slightly (IMERG over the platform rectangle, CHIRPS over the script ROI), which
cannot explain a factor of 1.8. This supports `docs/KNOWN_ISSUES.md`: IMERG over Kutch looks high and should be checked
against IMD. The greening result does not depend on which rainfall set is used.

## 7. What this does and does not show

* **Shows:** monsoon greening since 2001 is present in pixels that are low-Prosopis today, and survives removing rain
  with two independent rainfall products. A Prosopis-only explanation does not fit.
* **Does not show:** what drives it. The classifier has **no cropland class**, so farmland in mainland Kutch (south part of
  the ROI) is filed under mixed or Prosopis; the "fields" explanation in the brief therefore cannot be separated here.
* "Low Prosopis in 2023" pixels could have held Prosopis earlier (cleared) or hold scattered shrubs below the 250 m
  resolution. The 2017 map and a dry-season check (planned by the parallel review session, `scripts/08`) address this.
* The masks come from a 2023 map that selects pixels green in the dry season; a circularity check with an earlier map is
  still to do.
* The ROI is a rectangle that includes mainland Kutch and the Rann edge, not the Banni boundary.

## 8. Recommended next steps

1. Add a **cropland class** (and possibly open grassland) and re-run; without it the "fields" question cannot be answered.
2. Add points for **mixed vs saline brushland** until the location-holdout accuracy passes 80 %.
3. Repeat with the 2017 class map (same two-stage pattern) to test circularity.
4. Restrict the analysis to a Banni boundary polygon once one is available.

## 9. Files

See [README.md](README.md) for the folder layout and how to re-run every step.
