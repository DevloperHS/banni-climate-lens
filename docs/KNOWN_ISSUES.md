# Known issues

- The raw artifact [`data/raw/banni/handover_water_table_20261112T214756Z.json`](../data/raw/banni/handover_water_table_20261112T214756Z.json:1) is named `handover_water_table`, but its provenance metadata says `key: ndvi` and describes MODIS NDVI. The artifact contains ET and GLDAS soil-moisture fields, not well measurements or depth-to-water.
- IMERG monsoon totals are unusually high (2020 is approximately 1,000 mm versus an approximately 300 mm climatology). Verify the rainfall series against CHIRPS or IMD before interpreting the rainfall trend.
- `ndvi_qa` and `ndvi_nowater` are sensitivity/masked series; neither is used in the headline trend. The headline uses `ndvi`.
- The general seasonal mean aggregation applies a 75% valid-month coverage rule (`backend/app/science/timeseries.py::seasonal_aggregate`), while handover reproduction uses its separate protocol (`backend/app/science/handover.py::handover_annual`). These are not interchangeable.
- `research/prosopis_rf/gee/banni_rf.js` cannot export its table as written ("Reprojection output too large"; with `tileScale`, "User memory limit exceeded"). Use the two-stage version (`stage1_classmap.js`, then `stage2_table.js`); see `research/prosopis_rf/REPORT.md`.
- CHIRPS and IMERG monsoon totals agree year to year (r = 0.95) but IMERG is about 1.8 times CHIRPS (2001-2024 means 526 vs 288 mm). Greening trends hold with either source; rainfall magnitudes should be checked against IMD before quoting them.
- The Prosopis random forest has no cropland class, and its held-out-location accuracy is 76 % (the script's pixel-split figure, 96 %, is optimistic). See `research/prosopis_rf/REPORT.md` section 4.
