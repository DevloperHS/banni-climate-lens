"""Step 12: the farming test. Does farmland explain the greening trend?

Uses the farmland shares from 12a_export_cropland.py (ESA WorldCover 2021 cropland; Dynamic World "crops" in 2016-17
and 2023-24). Everything below was fixed before the run.

Areas: script_box  = banni_rf.js ROI (69.0-69.9 E, 23.4-23.9 N)
       platform_box = handover / platform rectangle (68.80-69.95 E, 23.20-23.95 N), the box behind the +0.0017 figure
In both, pixels with a WorldCover water + wetland share of 0.1 or more are left out.

Series:
  all            every pixel                                                                 -> baseline
  minus_farm     without any pixel that has 5 % or more farmland in ANY of the three farmland layers   -> the 25 % rule
  minus_farm_wc  without pixels with WorldCover cropland >= 5 %                              -> sensitivity
  minus_farm_dw  without pixels with Dynamic World crops >= 5 % in 2016-17 or 2023-24        -> sensitivity
  farm           farmland-dominated pixels: WorldCover cropland >= 50 % or Dynamic World crops 2023-24 >= 50 %
  new_farm       farmland that grew: Dynamic World crops share up by 20 points or more from 2016-17 to 2023-24
Effect rule (as for Prosopis, step 11), applied to the rain-removed trend:
  positive effect = removing farmland lowers the trend by 25 % or more, or the trend is no longer significant
  negative effect = removing farmland raises the trend by 25 % or more
  neutral         = change within 25 % and still significant
Outcome and tests as in 05_analyse_trends.py: monsoon (Jun-Sep) MOD13Q1 NDVI with SummaryQA <= 1; Hamed-Rao Mann-Kendall
+ Sen slope; rain removed by OLS residuals with CHIRPS (over each area) and with the platform's IMERG.

Run from the repository root:  .venv\\Scripts\\python research\\prosopis_rf\\scripts\\12_farming_test.py
Writes research/prosopis_rf/results/farming_series.csv and farming_tests.json.
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
a05 = importlib.util.module_from_spec(spec); spec.loader.exec_module(a05)

THRESHOLD = 0.25
AREAS = {"script_box": ee.Geometry.Rectangle([69.0, 23.4, 69.9, 23.9]),
         "platform_box": ee.Geometry.Rectangle([68.80, 23.20, 69.95, 23.95])}
modis = ee.ImageCollection("MODIS/061/MOD13Q1")
fr = ee.Image(f"projects/{PROJECT}/assets/banni_cropland_fractions_modis")
wc, dwe, dwl = fr.select("wc_crop"), fr.select("dw_crop_early"), fr.select("dw_crop_late")
base = fr.select("wc_water").lt(0.1)
groups = {
    "all": base,
    "minus_farm": base.And(wc.lt(0.05)).And(dwe.lt(0.05)).And(dwl.lt(0.05)),
    "minus_farm_wc": base.And(wc.lt(0.05)),
    "minus_farm_dw": base.And(dwe.lt(0.05)).And(dwl.lt(0.05)),
    "farm": base.And(wc.gte(0.5).Or(dwl.gte(0.5))),
    "new_farm": base.And(dwl.subtract(dwe).gte(0.2)),
}
cat = ee.Image.cat([g.rename(k) for k, g in groups.items()]).selfMask()


def per_year(y, geom):
    y = ee.Number(y)
    nd = (modis.filterDate(ee.Date.fromYMD(y, 6, 1), ee.Date.fromYMD(y, 10, 1))
          .map(lambda i: i.updateMask(i.select("SummaryQA").lte(1))).select("NDVI").mean().multiply(0.0001))
    props = {k: nd.updateMask(g).reduceRegion(reducer=ee.Reducer.mean(), geometry=geom, scale=250, maxPixels=1e9, tileScale=16).get("NDVI")
             for k, g in groups.items()}
    rain = (ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY").filterDate(ee.Date.fromYMD(y, 6, 1), ee.Date.fromYMD(y, 10, 1)).sum()
            .reduceRegion(reducer=ee.Reducer.mean(), geometry=geom, scale=5566, maxPixels=1e9).get("precipitation"))
    return ee.Feature(None, {"year": y, "chirps_monsoon_mm": rain, **props})


def effect(b, t):
    change = (t["sen_slope_per_year"] - b["sen_slope_per_year"]) / abs(b["sen_slope_per_year"])
    if t["p"] >= 0.05 or change <= -THRESHOLD:
        label = "positive effect (farmland was raising the trend)"
    elif change >= THRESHOLD:
        label = "negative effect (farmland was holding the trend down)"
    else:
        label = "neutral"
    return {"change_vs_all_pct": float(100 * change), "effect": label}


im = a05.imerg_monsoon()
out, frames = {"threshold_pct": 100 * THRESHOLD}, []
fmt = lambda t: f"{t['sen_slope_per_year']:+.5f}/yr p={t['p']:.4f}"
for area, geom in AREAS.items():
    counts = cat.reduceRegion(reducer=ee.Reducer.count(), geometry=geom, scale=250, maxPixels=1e9, tileScale=16).getInfo()
    shares = fr.updateMask(base).reduceRegion(reducer=ee.Reducer.mean(), geometry=geom, scale=250, maxPixels=1e9, tileScale=16).getInfo()
    print(f"\n{area}: pixels {counts}\n  mean farmland share (non-water pixels) {shares}", flush=True)
    rows = []
    for y in range(2001, 2025):  # one year per request (Earth Engine's concurrent-aggregation limit)
        rows.append(per_year(y, geom).getInfo()["properties"])
        print(y, end=" ", flush=True)
    print()
    df = pd.DataFrame(rows).astype({"year": int}).sort_values("year").set_index("year")
    frames.append(df.assign(area=area))
    yrs = df.index.to_numpy(float)
    res = {"modis_pixels": counts, "mean_shares_non_water": shares, "series": {}}
    for k in groups:
        s = df[k].dropna()
        if len(s) < 10:
            res["series"][k] = {"note": "too few years with data"}
            continue
        y_ = s.index.to_numpy(float)
        r = {"mean_ndvi": float(s.mean()), "raw": a05.trend(s, y_),
             "rain_removed_chirps": a05.rain_removed(s, df.loc[s.index, "chirps_monsoon_mm"], y_)["residual_trend"],
             "rain_removed_imerg": a05.rain_removed(s, im.reindex(s.index), y_)["residual_trend"]}
        r["relative_pct_per_decade"] = float(1000 * r["raw"]["sen_slope_per_year"] / s.mean())
        res["series"][k] = r
    b = res["series"]["all"]
    for k in ("minus_farm", "minus_farm_wc", "minus_farm_dw"):
        res["series"][k]["effect"] = {m: effect(b[m], res["series"][k][m]) for m in ("raw", "rain_removed_chirps", "rain_removed_imerg")}
    res["gap_farm_minus_minus_farm"] = a05.trend(df["farm"] - df["minus_farm"], yrs)
    out[area] = res
    for k, s in res["series"].items():
        if "raw" not in s:
            print(f"  {k:<14} {s['note']}"); continue
        print(f"  {k:<14}{counts.get(k, 0):>7} px  mean {s['mean_ndvi']:.3f}  raw {fmt(s['raw'])}  {s['relative_pct_per_decade']:+.1f}%/dec  "
              f"CHIRPS-removed {fmt(s['rain_removed_chirps'])}  IMERG-removed {fmt(s['rain_removed_imerg'])}")
        for m, e in s.get("effect", {}).items():
            print(f"      {m:<20} change {e['change_vs_all_pct']:+6.1f}%  -> {e['effect']}")
    print(f"  gap farm - minus_farm {fmt(res['gap_farm_minus_minus_farm'])}")

pd.concat(frames).to_csv(RES / "farming_series.csv")
(RES / "farming_tests.json").write_text(json.dumps(out, indent=2))
