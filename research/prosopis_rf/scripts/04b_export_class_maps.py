"""Step 4b: export the class maps in two light stages (replaces the one-shot fraction export that ran out of memory).

Classifying the 10 m Sentinel-2 composite AND averaging it to the MODIS grid in one task fails ("Execution failed; out of
memory"), and so does banni_rf.js's own export. Split into:
  stage A  classified maps 2023 and 2017 at 10 m (UTM 42N), uint8, one band per year -> asset (classifier runs per tile)
  stage B  share of each class per MODIS pixel, from the stage-A asset (no classifier involved) -> asset
           bands f<class>_<year>, the input of 08_robustness_checks.py
Training, composites, bands and the 300-tree random forest are exactly as in 04_run_rf_python.py / banni_rf.js.
Run from the repository root:  .venv\\Scripts\\python research\\prosopis_rf\\scripts\\04b_export_class_maps.py
"""
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
p = ROOT / "research" / "prosopis_rf" / "scripts" / "04_run_rf_python.py"
g = {"__file__": str(p)}
src = p.read_text()
exec(src.split("acc = ee.Dictionary")[0], g)              # ee init, training, comp(), bands, rf trained on 2023
ee, rf, comp, bands, roi, PROJECT = (g[k] for k in ("ee", "rf", "comp", "bands", "roi", "PROJECT"))
YEARS = (2023, 2017)
MAPS = f"projects/{PROJECT}/assets/banni_prosopis_rf_classmaps_10m"
FRAC = f"projects/{PROJECT}/assets/banni_prosopis_class_fractions_python"


def run(task, asset):
    try:
        ee.data.deleteAsset(asset)
    except ee.EEException:
        pass
    task.start()
    while task.status()["state"] in ("READY", "RUNNING"):
        time.sleep(30)
    st = task.status()
    print(f"{task.config.get('description')}: {st['state']} {st.get('error_message', '')}", flush=True)
    if st["state"] != "COMPLETED":
        raise SystemExit("export failed")


maps = ee.Image.cat([comp(y).select(bands).classify(rf).rename(f"class_{y}") for y in YEARS]).toUint8()
run(ee.batch.Export.image.toAsset(image=maps, description="banni_prosopis_rf_classmaps_10m", assetId=MAPS, region=roi,
                                  crs="EPSG:32642", scale=10, maxPixels=1e10, pyramidingPolicy={".default": "mode"}), MAPS)

M = ee.Image(MAPS)
mp = ee.Image(ee.ImageCollection("MODIS/061/MOD13Q1").first()).select("NDVI").projection().getInfo()
fr = ee.Image.cat([M.select(f"class_{y}").eq(c).reduceResolution(reducer=ee.Reducer.mean(), maxPixels=1024).rename(f"f{c}_{y}")
                   for y in YEARS for c in (1, 2, 3, 4)]).toFloat()
run(ee.batch.Export.image.toAsset(image=fr, description="banni_prosopis_class_fractions_python", assetId=FRAC, region=roi,
                                  crs=mp["crs"], crsTransform=mp["transform"], maxPixels=1e10), FRAC)

shares = ee.Image(FRAC).reduceRegion(reducer=ee.Reducer.mean(), geometry=roi, crs=mp["crs"], crsTransform=mp["transform"],
                                     maxPixels=1e9).getInfo()
out = ROOT / "research" / "prosopis_rf" / "results" / "class_shares_python.json"
out.write_text(json.dumps({"mean_class_fraction_over_script_roi": shares,
                           "classes": {"1": "Prosopis woodland", "2": "Mixed", "3": "Wetland/water", "4": "Saline brushland"},
                           "note": "Script ROI 69.0-69.9 E, 23.4-23.9 N (includes farmland south of Banni). 2017 = the 2023 model "
                                   "applied to the Nov 2016-Mar 2017 composite. Map accuracy on new locations is ~76 %; do not "
                                   "quote these shares as precise areas."}, indent=2))
print("class shares:", {k: round(v, 4) for k, v in sorted(shares.items())})
