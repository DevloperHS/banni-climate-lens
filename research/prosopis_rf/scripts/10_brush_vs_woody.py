"""Step 10: does greening also happen where there is no woody cover at all?

The "low-Prosopis" pixels of banni_rf.js (woodland share < 5 %) are about half "mixed Prosopis + grass", which contains
scattered Prosopis shrubs, so their greening could still be Prosopis thickening. This compares MODIS pixels whose 10 m
class mix (from the stored random-forest maps) is almost entirely SALINE BRUSHLAND, i.e. no woodland and almost no mixed
cover, with the woody groups.

Groups (fractions of the 10 m classes inside each MODIS pixel; water share < 0.1 everywhere, as in banni_rf.js):
  brush_pure     saline brush >= 0.90, woodland = 0 (< 0.01), mixed < 0.10        -> no woody cover
  brush_loose    saline brush >= 0.80, woodland < 0.02, mixed < 0.20              -> sensitivity
  brush_stable   brush_pure in BOTH the 2023 and 2017 maps                        -> no woody cover in 2017 or 2023
  mixed          mixed >= 0.80, woodland < 0.05                                   -> scattered Prosopis + grass
  woodland       woodland > 0.40 (the script's "high Prosopis")
Outcome and tests as in 05_analyse_trends.py: monsoon (Jun-Sep) MOD13Q1 NDVI with SummaryQA <= 1; Hamed-Rao Mann-Kendall
+ Sen slope; rain removed by OLS residuals with CHIRPS (script ROI) and with the platform's IMERG.

Inputs: projects/<project>/assets/banni_rf_classmap_2023 (stage 1) and banni_rf_classmap_2017 (robustness run).
Run from the repository root:  .venv\\Scripts\\python research\\prosopis_rf\\scripts\\10_brush_vs_woody.py
Writes research/prosopis_rf/results/brush_vs_woody_series.csv and brush_vs_woody_tests.json.
"""
import importlib.util
import json
import os
from pathlib import Path

import ee
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
RES = ROOT / "research" / "prosopis_rf" / "results"
PROJECT = os.environ.get("GCL_EE_PROJECT") or next(l.split("=", 1)[1].strip() for l in (ROOT / ".env").read_text().splitlines() if l.startswith("GCL_EE_PROJECT="))
ee.Initialize(project=PROJECT)
spec = importlib.util.spec_from_file_location("a05", ROOT / "research" / "prosopis_rf" / "scripts" / "05_analyse_trends.py")
a05 = importlib.util.module_from_spec(spec); spec.loader.exec_module(a05)           # trend(), rain_removed(), imerg_monsoon()

roi = ee.Geometry.Rectangle([69.0, 23.4, 69.9, 23.9])
modis = ee.ImageCollection("MODIS/061/MOD13Q1")
mproj = ee.Image(modis.first()).select("NDVI").projection()


def fractions(year):
    cm = ee.Image(f"projects/{PROJECT}/assets/banni_rf_classmap_{year}").select("classification")
    return {c: cm.eq(k).reduceResolution(reducer=ee.Reducer.mean(), maxPixels=1024).reproject(mproj)
            for k, c in ((1, "wood"), (2, "mix"), (3, "water"), (4, "brush"))}


f23, f17 = fractions(2023), fractions(2017)
dry = lambda f: f["water"].lt(0.1)
pure = lambda f: f["brush"].gte(0.90).And(f["wood"].lt(0.01)).And(f["mix"].lt(0.10)).And(dry(f))
groups = {
    "brush_pure": pure(f23),
    "brush_loose": f23["brush"].gte(0.80).And(f23["wood"].lt(0.02)).And(f23["mix"].lt(0.20)).And(dry(f23)),
    "brush_stable": pure(f23).And(pure(f17)),
    "mixed": f23["mix"].gte(0.80).And(f23["wood"].lt(0.05)).And(dry(f23)),
    "woodland": f23["wood"].gt(0.40).And(dry(f23)),
}
counts = ee.Image.cat([g.rename(k) for k, g in groups.items()]).selfMask().reduceRegion(
    reducer=ee.Reducer.count(), geometry=roi, scale=250, maxPixels=1e9, tileScale=16).getInfo()
print("MODIS pixels per group:", counts, flush=True)


def per_year(y):
    y = ee.Number(y)
    nd = (modis.filterDate(ee.Date.fromYMD(y, 6, 1), ee.Date.fromYMD(y, 10, 1))
          .map(lambda i: i.updateMask(i.select("SummaryQA").lte(1))).select("NDVI").mean().multiply(0.0001))
    props = {k: nd.updateMask(g).reduceRegion(reducer=ee.Reducer.mean(), geometry=roi, scale=250, maxPixels=1e9, tileScale=16).get("NDVI")
             for k, g in groups.items()}
    rain = (ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY").filterDate(ee.Date.fromYMD(y, 6, 1), ee.Date.fromYMD(y, 10, 1)).sum()
            .reduceRegion(reducer=ee.Reducer.mean(), geometry=roi, scale=5566, maxPixels=1e9).get("precipitation"))
    return ee.Feature(None, {"year": y, "chirps_monsoon_mm": rain, **props})


# one year per request: all 24 years at once trips Earth Engine's "Too many concurrent aggregations" limit
rows = []
for y in range(2001, 2025):
    rows.append(per_year(y).getInfo()["properties"])
    print(y, end=" ", flush=True)
print()
df = pd.DataFrame(rows).astype({"year": int}).sort_values("year").set_index("year")
df.to_csv(RES / "brush_vs_woody_series.csv")
yrs = df.index.to_numpy(float)
im = a05.imerg_monsoon().reindex(df.index)

out = {"modis_pixels": counts, "groups": {}}
for k in groups:
    s = df[k]
    g = {"mean_ndvi": float(s.mean()), "raw": a05.trend(s, yrs),
         "rain_removed_chirps": a05.rain_removed(s, df["chirps_monsoon_mm"], yrs),
         "rain_removed_imerg": a05.rain_removed(s, im, yrs)}
    g["raw"]["relative_slope_pct_per_decade"] = float(100 * 10 * g["raw"]["sen_slope_per_year"] / s.mean())
    out["groups"][k] = g
for k in ("brush_pure", "brush_stable", "mixed"):
    out[f"gap_woodland_minus_{k}"] = a05.trend(df["woodland"] - df[k], yrs)
(RES / "brush_vs_woody_tests.json").write_text(json.dumps(out, indent=2))

f = lambda t: f"{t['sen_slope_per_year']:+.5f}/yr p={t['p']:.3f}"
print(f"{'group':<13}{'pixels':>8}{'mean NDVI':>11}  {'raw':<22}{'%/decade':>9}  {'rain removed (CHIRPS)':<24}{'rain removed (IMERG)':<24}")
for k, g in out["groups"].items():
    print(f"{k:<13}{counts.get(k, 0):>8}{g['mean_ndvi']:>11.3f}  {f(g['raw']):<22}{g['raw']['relative_slope_pct_per_decade']:>8.1f}%  "
          f"{f(g['rain_removed_chirps']['residual_trend']):<24}{f(g['rain_removed_imerg']['residual_trend']):<24}")
for k in ("brush_pure", "brush_stable", "mixed"):
    print(f"gap woodland - {k:<13} {f(out[f'gap_woodland_minus_{k}'])}")
