"""Step 11: the "remove the factor" test for Prosopis.

Question: if we take the Prosopis pixels OUT of the area, how much does the area's greening trend change?
Effect rule (fixed before running):
  positive effect  = removing Prosopis lowers the trend by 25 % or more, or the trend stops being significant
  negative effect  = removing Prosopis raises the trend by 25 % or more
  neutral          = change within 25 % and the trend is still significant
The rule is applied to the rain-removed trend (CHIRPS and IMERG), and also shown for the raw trend.

Area: the script ROI (69.0-69.9 E, 23.4-23.9 N), the only area the stored class map covers. Pixels with a water share
of 0.1 or more are left out everywhere, as in banni_rf.js. Series:
  all            every MODIS pixel in the ROI (water share < 0.1)                      -> baseline
  minus_high     all, without the script's "high Prosopis" pixels (woodland share > 0.4)
  minus_any_wood all, without pixels with woodland share >= 0.05 (= the script's "low Prosopis" group)
  minus_woody    all, without pixels with woodland >= 0.01 or mixed >= 0.10 (no Prosopis trees or shrubs)
Fractions come from projects/<project>/assets/banni_rf_classmap_2023. Outcome and tests as in 05_analyse_trends.py.

Run from the repository root:  .venv\\Scripts\\python research\\prosopis_rf\\scripts\\11_remove_prosopis.py
Writes research/prosopis_rf/results/remove_prosopis_series.csv and remove_prosopis_tests.json.
"""
import importlib.util
import json
import os
from pathlib import Path

import ee
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
RES = ROOT / "research" / "prosopis_rf" / "results"
PROJECT = os.environ.get("GCL_EE_PROJECT") or next(l.split("=", 1)[1].strip() for l in (ROOT / ".env").read_text().splitlines() if l.startswith("GCL_EE_PROJECT="))
ee.Initialize(project=PROJECT)
spec = importlib.util.spec_from_file_location("a05", ROOT / "research" / "prosopis_rf" / "scripts" / "05_analyse_trends.py")
a05 = importlib.util.module_from_spec(spec); spec.loader.exec_module(a05)           # trend(), rain_removed(), imerg_monsoon()

THRESHOLD = 0.25
roi = ee.Geometry.Rectangle([69.0, 23.4, 69.9, 23.9])
modis = ee.ImageCollection("MODIS/061/MOD13Q1")
mproj = ee.Image(modis.first()).select("NDVI").projection()
cm = ee.Image(f"projects/{PROJECT}/assets/banni_rf_classmap_2023").select("classification")
f = {c: cm.eq(k).reduceResolution(reducer=ee.Reducer.mean(), maxPixels=1024).reproject(mproj)
     for k, c in ((1, "wood"), (2, "mix"), (3, "water"), (4, "brush"))}
base = f["water"].lt(0.1)
groups = {
    "all": base,
    "minus_high": base.And(f["wood"].lte(0.4)),
    "minus_any_wood": base.And(f["wood"].lt(0.05)),
    "minus_woody": base.And(f["wood"].lt(0.01)).And(f["mix"].lt(0.10)),
}
counts = ee.Image.cat([g.rename(k) for k, g in groups.items()]).selfMask().reduceRegion(
    reducer=ee.Reducer.count(), geometry=roi, scale=250, maxPixels=1e9, tileScale=16).getInfo()
print("MODIS pixels per series:", counts, flush=True)


def per_year(y):
    y = ee.Number(y)
    nd = (modis.filterDate(ee.Date.fromYMD(y, 6, 1), ee.Date.fromYMD(y, 10, 1))
          .map(lambda i: i.updateMask(i.select("SummaryQA").lte(1))).select("NDVI").mean().multiply(0.0001))
    props = {k: nd.updateMask(g).reduceRegion(reducer=ee.Reducer.mean(), geometry=roi, scale=250, maxPixels=1e9, tileScale=16).get("NDVI")
             for k, g in groups.items()}
    rain = (ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY").filterDate(ee.Date.fromYMD(y, 6, 1), ee.Date.fromYMD(y, 10, 1)).sum()
            .reduceRegion(reducer=ee.Reducer.mean(), geometry=roi, scale=5566, maxPixels=1e9).get("precipitation"))
    return ee.Feature(None, {"year": y, "chirps_monsoon_mm": rain, **props})


rows = []
for y in range(2001, 2025):  # one year per request (Earth Engine's concurrent-aggregation limit)
    rows.append(per_year(y).getInfo()["properties"])
    print(y, end=" ", flush=True)
print()
df = pd.DataFrame(rows).astype({"year": int}).sort_values("year").set_index("year")
df.to_csv(RES / "remove_prosopis_series.csv")
yrs = df.index.to_numpy(float)
im = a05.imerg_monsoon().reindex(df.index)


def effect(base_t, t):
    change = (t["sen_slope_per_year"] - base_t["sen_slope_per_year"]) / abs(base_t["sen_slope_per_year"])
    if t["p"] >= 0.05 or change <= -THRESHOLD:
        label = "positive effect (Prosopis was raising the trend)"
    elif change >= THRESHOLD:
        label = "negative effect (Prosopis was holding the trend down)"
    else:
        label = "neutral"
    return {"change_vs_all_pct": float(100 * change), "effect": label}


out = {"modis_pixels": counts, "threshold_pct": 100 * THRESHOLD, "series": {}}
for k in groups:
    s = df[k]
    out["series"][k] = {"mean_ndvi": float(s.mean()), "raw": a05.trend(s, yrs),
                        "rain_removed_chirps": a05.rain_removed(s, df["chirps_monsoon_mm"], yrs)["residual_trend"],
                        "rain_removed_imerg": a05.rain_removed(s, im, yrs)["residual_trend"]}
    out["series"][k]["relative_pct_per_decade"] = float(1000 * out["series"][k]["raw"]["sen_slope_per_year"] / s.mean())
b = out["series"]["all"]
for k in list(groups)[1:]:
    out["series"][k]["effect"] = {m: effect(b[m], out["series"][k][m]) for m in ("raw", "rain_removed_chirps", "rain_removed_imerg")}
(RES / "remove_prosopis_tests.json").write_text(json.dumps(out, indent=2))

fmt = lambda t: f"{t['sen_slope_per_year']:+.5f}/yr p={t['p']:.4f}"
for k, s in out["series"].items():
    print(f"{k:<15}{counts.get(k, 0):>7} px  mean {s['mean_ndvi']:.3f}  raw {fmt(s['raw'])}  {s['relative_pct_per_decade']:+.1f}%/decade  "
          f"CHIRPS-removed {fmt(s['rain_removed_chirps'])}  IMERG-removed {fmt(s['rain_removed_imerg'])}")
    for m, e in s.get("effect", {}).items():
        print(f"    {m:<20} change {e['change_vs_all_pct']:+6.1f}%  -> {e['effect']}")
