"""Step 8: robustness of the high- vs low-Prosopis NDVI comparison (reviewer requests, 2026-11-13).

1. Circularity. The 2023 map picks pixels that are woody AND green in the 2022-23 dry season, so a rising monsoon-NDVI
   trend in those pixels could be partly built in. Two independent checks:
     a) masks from the 2017 map (same model applied to the Nov 2016-Mar 2017 composite)
     b) the outcome measured in a different season: dry-season (Mar-May) NDVI instead of monsoon (Jun-Sep) NDVI
2. Cutoff sensitivity. banni_rf.js fixed hi = Prosopis share > 0.4, lo = share < 0.05 (water share < 0.1 for both)
   before any run. Repeated at 0.3 / 0.1 and 0.5 / 0.02; the answer should point the same way.

Inputs: the class-fraction asset written by 04_run_rf_python.py (f<class>_<year> on the MODIS grid; same thresholds and
reductions as banni_rf.js). NDVI: MOD13Q1 with SummaryQA <= 1 (as the script); rain: CHIRPS Jun-Sep total over the ROI.
Tests: Hamed-Rao Mann-Kendall + Sen slope; rain removed by OLS residuals (dry season uses the PREVIOUS monsoon's rain).

Run from the repository root:  .venv\\Scripts\\python research\\prosopis_rf\\scripts\\08_robustness_checks.py
Writes research/prosopis_rf/results/robustness_series.csv and robustness_tests.json.
"""
import csv
import json
import os
from pathlib import Path

import ee
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
RES = ROOT / "research" / "prosopis_rf" / "results"
PROJECT = os.environ.get("GCL_EE_PROJECT") or next(l.split("=", 1)[1].strip() for l in (ROOT / ".env").read_text().splitlines() if l.startswith("GCL_EE_PROJECT="))
ee.Initialize(project=PROJECT)

# trend helpers shared with step 5
_g = {"__file__": str(ROOT / "research/prosopis_rf/scripts/05_analyse_trends.py")}
exec((ROOT / "research/prosopis_rf/scripts/05_analyse_trends.py").read_text().split("def imerg_monsoon")[0], _g)
trend, rain_removed = _g["trend"], _g["rain_removed"]

roi = ee.Geometry.Rectangle([69.0, 23.4, 69.9, 23.9])
modis = ee.ImageCollection("MODIS/061/MOD13Q1")
mp = ee.Image(modis.first()).select("NDVI").projection().getInfo()

# Input: the multi-year fraction asset if it exists (adds the 2017-map check); otherwise the Code Editor stage-1 asset
# banni_prosopis_fractions_2023 (bands frac_pros, frac_water), which covers the cutoff and dry-season checks.
MULTI = f"projects/{PROJECT}/assets/banni_prosopis_class_fractions_python"
ONE = f"projects/{PROJECT}/assets/banni_prosopis_fractions_2023"
CLASSMAP = f"projects/{PROJECT}/assets/banni_rf_classmap_{{}}"          # 10 m class map, band 'classification' (1-4)
have = {a["name"] for a in ee.data.listAssets({"parent": f"projects/{PROJECT}/assets"}).get("assets", [])}
map_years = {y for y in (2023, 2017) if CLASSMAP.format(y) in have}
if MULTI in have:
    F = ee.Image(MULTI)
    band = lambda cls, yr: F.select(f"f{cls}_{yr}")
    map_years = {2023, 2017}
elif map_years:
    # share of each class per MODIS pixel, derived from the stored 10 m class map (no classifier in the request)
    band = lambda cls, yr: (ee.Image(CLASSMAP.format(yr)).select("classification").eq(cls)
                            .reduceResolution(reducer=ee.Reducer.mean(), maxPixels=1024))
elif ONE in have:
    F = ee.Image(ONE)
    band = lambda cls, yr: F.select("frac_pros" if cls == 1 else "frac_water")
    map_years = {2023}
else:
    raise SystemExit("No class-map or fraction asset yet (banni_rf_classmap_2023 expected from the main session).")

# (name, map year, hi cutoff, lo cutoff); "main" is the pre-registered setting of banni_rf.js
CONFIGS = [("main_2023_40_5", 2023, 0.4, 0.05), ("map2017_40_5", 2017, 0.4, 0.05),
           ("cut_2023_30_10", 2023, 0.3, 0.10), ("cut_2023_50_2", 2023, 0.5, 0.02)]
CONFIGS = [c for c in CONFIGS if c[1] in map_years]
if 2017 not in map_years:
    print("2017-map check skipped: no 2017 class map yet.")
masks = {}
for name, yr, h, l in CONFIGS:
    p, w = band(1, yr), band(3, yr)
    masks[f"{name}_hi"] = p.gt(h).And(w.lt(0.1))
    masks[f"{name}_lo"] = p.lt(l).And(w.lt(0.1))
counts = ee.Image.cat([m.rename(k) for k, m in masks.items()]).selfMask().reduceRegion(
    reducer=ee.Reducer.count(), geometry=roi, crs=mp["crs"], crsTransform=mp["transform"], maxPixels=1e9).getInfo()


def season_ndvi(y, m0, m1):
    col = modis.filterDate(ee.Date.fromYMD(y, m0, 1), ee.Date.fromYMD(y, m1, 1)).map(lambda i: i.updateMask(i.select("SummaryQA").lte(1)))
    return col.select("NDVI").mean().multiply(0.0001)


def per_year(y):
    y = ee.Number(y)
    bands = []
    for season, (m0, m1) in (("mon", (6, 10)), ("dry", (3, 6))):
        nd = season_ndvi(y, m0, m1)
        bands += [nd.updateMask(m).rename(f"{season}_{k}") for k, m in masks.items()]
    vals = ee.Image.cat(bands).reduceRegion(reducer=ee.Reducer.mean(), geometry=roi, crs=mp["crs"], crsTransform=mp["transform"], maxPixels=1e9)
    rain = (ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY").filterDate(ee.Date.fromYMD(y, 6, 1), ee.Date.fromYMD(y, 10, 1)).sum()
            .reduceRegion(reducer=ee.Reducer.mean(), geometry=roi, scale=5566, maxPixels=1e9))
    return ee.Feature(None, vals.set("year", y).set("chirps_monsoon_mm", rain.get("precipitation")))


rows = [f["properties"] for f in ee.FeatureCollection(ee.List.sequence(2000, 2024).map(per_year)).getInfo()["features"]]
rows.sort(key=lambda r: r["year"])
keys = ["year", "chirps_monsoon_mm"] + sorted(k for k in rows[0] if k not in ("year", "chirps_monsoon_mm"))
RES.mkdir(parents=True, exist_ok=True)
with (RES / "robustness_series.csv").open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=keys)
    w.writeheader(); w.writerows({k: r.get(k) for k in keys} for r in rows)

by = {r["year"]: r for r in rows}
years = [y for y in range(2001, 2025)]
out = {"pixel_counts_modis_grid": counts, "configs": {}}
for name, *_ in CONFIGS:
    res = {}
    for season in ("mon", "dry"):
        hi = np.array([by[y][f"{season}_{name}_hi"] for y in years], float)
        lo = np.array([by[y][f"{season}_{name}_lo"] for y in years], float)
        # rain control: monsoon NDVI ~ same monsoon; dry-season NDVI ~ previous monsoon
        rain = np.array([by[y if season == "mon" else y - 1]["chirps_monsoon_mm"] for y in years], float)
        yr = np.array(years, float)
        res[season] = {"hi": {"trend": trend(hi, yr), **rain_removed(hi, rain, yr)},
                       "lo": {"trend": trend(lo, yr), **rain_removed(lo, rain, yr)},
                       "gap_hi_minus_lo": {"trend": trend(hi - lo, yr)},
                       "mean_hi": float(hi.mean()), "mean_lo": float(lo.mean())}
    out["configs"][name] = res
(RES / "robustness_tests.json").write_text(json.dumps(out, indent=2))

f = lambda t: f"{t['sen_slope_per_year']:+.5f}/yr p={t['p']:.4f}"
print("MODIS pixels per mask:", counts)
for name, res in out["configs"].items():
    for season, lab in (("mon", "monsoon NDVI"), ("dry", "dry-season NDVI")):
        r = res[season]
        print(f"{name:<16} {lab:<16} hi raw {f(r['hi']['trend'])} | hi rain-removed {f(r['hi']['residual_trend'])} || "
              f"lo raw {f(r['lo']['trend'])} | lo rain-removed {f(r['lo']['residual_trend'])} || gap {f(r['gap_hi_minus_lo']['trend'])}")
