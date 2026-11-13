# Prosopis random forest and NDVI trend by Prosopis share

Work for the task "banni_rf.js" (Earth Engine, 2026-11-13): map *Prosopis juliflora* in and around Banni with a
Sentinel-2 random forest, then compare the 2001-2024 monsoon-NDVI trend of high-Prosopis and low-Prosopis MODIS pixels,
with CHIRPS rainfall as a second rainfall source next to IMERG.

The findings and their limits are in [REPORT.md](REPORT.md).

## Folder layout

| Path | What it is |
|---|---|
| `gee/banni_rf.js` | The script as received (copy of `data/extras/banni_rf.js`, unchanged) |
| `gee/manual_points.js` | The hand-picked points as the four FeatureCollections the script expects (`manualPros`, `manualMix`, `manualWater`, `manualBrush`) |
| `gee/banni_rf_with_points.js` | `manual_points.js` + `banni_rf.js`: what was pasted into the Code Editor first (gives the accuracy and kappa) |
| `gee/stage1_classmap.js` | Steps A-C unchanged; step D exports the 2023 class map at 10 m as an asset (`banni_rf_classmap_2023`) |
| `gee/stage2_table.js` | Step D, reading the stored class map (plus `tileScale: 16`); exports `banni_ndvi_by_prosopis_chirps` to Drive |
| `labelling/candidates*.csv` | Candidate locations proposed from ESA WorldCover + Sentinel-2 (three rounds) |
| `labelling/visual_labels.csv` | One decision per candidate after looking at its image chip: accepted, relabelled or rejected |
| `labelling/training_points.csv` | Final points (at least 150 m apart): 39 Prosopis, 34 mixed, 53 water, 33 saline brush |
| `labelling/sheets/` | Image chips used for labelling (git-ignored: Esri imagery; regenerate with `02_make_chips.py`) |
| `scripts/` | Reproducible steps 01-06; 07 runs one location-holdout split in detail; 09 checks other cutoffs and a 2017 map; 04b and 08 are earlier drafts, superseded by 09; 10 compares pure saline-brush (no woody) pixels with woody ones; 11 removes Prosopis pixels from the area and applies the 25 % effect rule; 12a exports farmland shares and 12 applies the same rule to farmland |
| `results/` | Accuracy (`rf_accuracy_*.json`), class shares, the exported CSV (Drive copy + full precision), trend tests, class map image, console screenshot, run logs |
| `../../data/extras/prosopis_rf/` | Local copies of the exported CSV |

## Steps

The full, ordered commands to reproduce every result (training points, the three Code Editor runs, and scripts 04 to 12)
are in the main README: [Reproduce the Prosopis research](../../README.md#8-reproduce-the-prosopis-research).

## Why there are two stages

`banni_rf.js` as received cannot export its table: the export fails with
`Reprojection output too large (14637x5634 pixels)` (with `tileScale`, `User memory limit exceeded`; exporting the MODIS-grid
fractions straight from the classifier, `out of memory`). The script recomputes the 10 m classification on the MODIS grid
inside the 24-year loop; MODIS's sinusoidal grid is strongly slanted at 69 E, so each request needs a block of the 10 m map
about 146 km wide. Storing the class map first, then running step D on it with `tileScale: 16`, removes the problem
without changing any threshold or reduction.

Imagery used for labelling: Esri World Imagery (Maxar, Earthstar Geographics). Field calibration: Bhan (2024), Zenodo
[10.5281/zenodo.11197850](https://doi.org/10.5281/zenodo.11197850), CC BY 4.0.
