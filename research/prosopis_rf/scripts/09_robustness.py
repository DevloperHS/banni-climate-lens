"""Step 9: robustness of the high- vs low-Prosopis comparison.

1. Cutoff sensitivity (2023 map): hi/lo = Prosopis share >0.4/<0.05 (banni_rf.js), plus 0.3/0.1 and 0.5/0.02.
2. Circularity: masks from the 2017 map (same RF applied to the Nov 2016-Mar 2017 composite) instead of 2023, so pixel
   selection does not depend on the 2022-23 greenness. Needs one export (banni_rf_classmap_2017), done here if missing.
Everything else as stage2_table.js: monsoon MOD13Q1 NDVI (SummaryQA<=1), CHIRPS Jun-Sep total, tileScale 16.
Tests: Hamed-Rao MK + Sen; rain removed by OLS residuals (CHIRPS).
Run from the repository root:  .venv\\Scripts\\python research\\prosopis_rf\\scripts\\09_robustness.py
Writes results/robustness_series.csv and results/robustness_tests.json.
"""
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pymannkendall as mk
import statsmodels.api as sm

ROOT = Path(__file__).resolve().parents[3]
RES = ROOT / "research" / "prosopis_rf" / "results"
p4 = ROOT / "research" / "prosopis_rf" / "scripts" / "04_run_rf_python.py"
g = {"__file__": str(p4)}
exec(p4.read_text().split("acc = ee.Dictionary")[0], g)          # ROI, training, comp(), RF (steps A-C)
ee, roi, comp, bands, rf, s2proj, PROJECT = (g[k] for k in ("ee", "roi", "comp", "bands", "rf", "s2proj", "PROJECT"))

asset17 = f"projects/{PROJECT}/assets/banni_rf_classmap_2017"
try:
    ee.data.getAsset(asset17)
    print("2017 class map exists", flush=True)
except ee.EEException:
    t = ee.batch.Export.image.toAsset(image=comp(2017).select(bands).classify(rf).rename("classification").toByte(),
                                      description="banni_rf_classmap_2017", assetId=asset17, region=roi, crs="EPSG:32642",
                                      scale=10, pyramidingPolicy={"classification": "mode"}, maxPixels=1e10)
    t.start()
    while t.status()["state"] in ("READY", "RUNNING"):
        time.sleep(30)
    st = t.status()
    print("2017 export:", st["state"], st.get("error_message", ""), flush=True)
    if st["state"] != "COMPLETED":
        raise SystemExit(1)

modis = ee.ImageCollection("MODIS/061/MOD13Q1")
mproj = ee.Image(modis.first()).select("NDVI").projection()
maps = {y: ee.Image(f"projects/{PROJECT}/assets/banni_rf_classmap_{y}").select("classification") for y in (2023, 2017)}
VARIANTS = [("2023_40_5", 2023, 0.4, 0.05), ("2023_30_10", 2023, 0.3, 0.1), ("2023_50_2", 2023, 0.5, 0.02), ("2017_40_5", 2017, 0.4, 0.05)]


def masks(year, h, l):
    cm = maps[year]
    f = cm.eq(1).reduceResolution(reducer=ee.Reducer.mean(), maxPixels=1024).reproject(mproj)
    w = cm.eq(3).reduceResolution(reducer=ee.Reducer.mean(), maxPixels=1024).reproject(mproj)
    return f.gt(h).And(w.lt(0.1)), f.lt(l).And(w.lt(0.1))


rows, counts = [], {}
for name, year, h, l in VARIANTS:
    hi, lo = masks(year, h, l)
    counts[name] = ee.Image.cat([hi.rename("hi"), lo.rename("lo")]).selfMask().reduceRegion(
        reducer=ee.Reducer.count(), geometry=roi, scale=250, maxPixels=1e9, tileScale=16).getInfo()

    def make_per_year(hi, lo):                      # Earth Engine map() needs a ONE-argument function
        def per_year(y):
            y = ee.Number(y)
            nd = (modis.filterDate(ee.Date.fromYMD(y, 6, 1), ee.Date.fromYMD(y, 10, 1))
                  .map(lambda i: i.updateMask(i.select("SummaryQA").lte(1))).select("NDVI").mean().multiply(0.0001))
            rr = lambda m: nd.updateMask(m).reduceRegion(reducer=ee.Reducer.mean(), geometry=roi, scale=250, maxPixels=1e9, tileScale=16).get("NDVI")
            return ee.Feature(None, {"year": y, "hi": rr(hi), "lo": rr(lo)})
        return per_year

    py = make_per_year(hi, lo)
    for yr in range(2001, 2025):                    # one year per request: the free tier caps concurrent aggregations
        for attempt in range(6):
            try:
                rows.append({"variant": name, **py(yr).getInfo()["properties"]})
                break
            except ee.EEException as e:
                if "Too many concurrent" not in str(e) or attempt == 5:
                    raise
                time.sleep(15)
    print(name, "done", counts[name], flush=True)

df = pd.DataFrame(rows)
rain = pd.read_csv(RES / "banni_ndvi_by_prosopis_chirps.csv").set_index("year")["chirps_monsoon_mm"]
df["chirps_monsoon_mm"] = df["year"].astype(int).map(rain)
df.to_csv(RES / "robustness_series.csv", index=False)


def trend(y):
    r = mk.hamed_rao_modification_test(np.asarray(y, float))
    return {"direction": r.trend if r.p < 0.05 else "no significant trend", "p": float(r.p), "sen_slope": float(mk.sens_slope(np.asarray(y, float)).slope)}


out = {}
for name, d in df.groupby("variant", sort=False):
    d = d.sort_values("year")
    res = {"modis_pixels": counts[name]}
    for k in ("hi", "lo"):
        resid = sm.OLS(d[k].to_numpy(float), sm.add_constant(d["chirps_monsoon_mm"].to_numpy(float))).fit().resid
        res[k] = {"raw": trend(d[k]), "rain_removed": trend(resid)}
    res["gap_hi_minus_lo"] = trend(d["hi"] - d["lo"])
    out[name] = res
(RES / "robustness_tests.json").write_text(json.dumps(out, indent=2))
for name, r in out.items():
    f = lambda t: f"{t['sen_slope']:+.4f} p={t['p']:.3f}"
    print(f"{name:11} n_hi={r['modis_pixels'].get('hi')} n_lo={r['modis_pixels'].get('lo')} | hi raw {f(r['hi']['raw'])} rr {f(r['hi']['rain_removed'])} | "
          f"lo raw {f(r['lo']['raw'])} rr {f(r['lo']['rain_removed'])} | gap {f(r['gap_hi_minus_lo'])}")
