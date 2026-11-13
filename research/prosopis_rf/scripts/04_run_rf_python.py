"""Step 4: run banni_rf.js line for line through the Earth Engine Python API (cross-check of the Code Editor run).

Same ROI, Zenodo sites, Sentinel-2 composites, band list, 70/30 split (seed 7), 300-tree random forest, MODIS / CHIRPS
table and thresholds as research/prosopis_rf/gee/banni_rf.js, except that step D cannot run as written (see the report,
section 5). Step D here therefore reads the STORED 2023 class map written by the Code Editor run (gee/stage1_classmap.js,
asset banni_rf_classmap_2023) and adds tileScale=16 to the MODIS reductions, exactly like gee/stage2_table.js; with
--own-map it first exports this script's own class map (~7 EECU-hours) and uses that instead. The hand-picked points come from
labelling/training_points.csv (the same points as gee/manual_points.js).

Writes to research/prosopis_rf/results/:
  rf_accuracy_python.json                       training/test pixel counts, confusion matrix, accuracy, kappa, class counts
  banni_ndvi_by_prosopis_chirps_python.csv      year, ndvi_hi_pros, ndvi_lo_pros, chirps_monsoon_mm (2001-2024)
Run from the repository root:  .venv\\Scripts\\python research\\prosopis_rf\\scripts\\04_run_rf_python.py
"""
import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import ee

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / "research" / "prosopis_rf"
RES = BASE / "results"
PROJECT = os.environ.get("GCL_EE_PROJECT") or next(l.split("=", 1)[1].strip() for l in (ROOT / ".env").read_text().splitlines() if l.startswith("GCL_EE_PROJECT="))
ee.Initialize(project=PROJECT)

roi = ee.Geometry.Rectangle([69.0, 23.4, 69.9, 23.9])

# ---- STEP A: Zenodo transect sites (UTM 42N), exactly as in banni_rf.js
sites = [["LTM_10", 526996.321, 2620503.022, 1], ["GORE-PROS", 553000.756, 2626756.504, 1],
         ["LTM_15", 530767.138, 2612165.708, 2], ["LTM_18", 530747.459, 2624127.855, 2], ["LTM_26", 534745.173, 2624301.172, 2],
         ["LTM_44", 546264.782, 2611981.772, 2], ["LTM_29", 538760.270, 2608103.298, 4], ["LTM_30", 538757.873, 2612081.015, 4],
         ["LTM_36", 542770.005, 2608165.522, 4], ["LTM_43", 546741.904, 2608154.328, 4]]
siteFC = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([s[1], s[2]], "EPSG:32642").buffer(60), {"class": s[3]}) for s in sites])

# ---- STEP B: hand-picked points, buffered 20 m like the script does with the drawn imports
pts = list(csv.DictReader((BASE / "labelling" / "training_points.csv").open()))
manual = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([float(p["lon"]), float(p["lat"])]).buffer(20), {"class": int(p["class_code"])})
                               for p in pts])
training = siteFC.merge(manual)


def mask_s2(img):
    qa = img.select("QA60")
    m = qa.bitwiseAnd(1 << 10).eq(0).And(qa.bitwiseAnd(1 << 11).eq(0))
    return img.updateMask(m).divide(10000).copyProperties(img, ["system:time_start"])


def comp(year):
    c = (ee.ImageCollection("COPERNICUS/S2_HARMONIZED").filterBounds(roi)
         .filterDate(f"{year - 1}-11-01", f"{year}-03-31").filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20)).map(mask_s2))
    m = c.median()
    return (m.select(["B2", "B3", "B4", "B5", "B6", "B7", "B8", "B11", "B12"])
            .addBands([m.normalizedDifference(["B8", "B4"]).rename("NDVI"), m.normalizedDifference(["B3", "B11"]).rename("MNDWI"),
                       m.normalizedDifference(["B8", "B5"]).rename("NDRE")]).clip(roi))


s2proj = ee.Image(ee.ImageCollection("COPERNICUS/S2_HARMONIZED").filterBounds(roi).first()).select("B2").projection()
bands = ["B2", "B3", "B4", "B5", "B6", "B7", "B8", "B11", "B12", "NDVI", "MNDWI", "NDRE"]

# ---- STEP C: train on 2023, test on held-out 30 %
img23 = comp(2023)
samples = img23.select(bands).sampleRegions(collection=training, properties=["class"], scale=10, tileScale=4).randomColumn("r", 7)
trainSet = samples.filter(ee.Filter.lt("r", 0.7))
testSet = samples.filter(ee.Filter.gte("r", 0.7))
rf = ee.Classifier.smileRandomForest(300).train(trainSet, "class", bands)
cm = testSet.classify(rf).errorMatrix("class", "classification")
acc = ee.Dictionary({"train_pixels": trainSet.size(), "test_pixels": testSet.size(), "confusion_matrix": cm.array(),
                     "overall_accuracy": cm.accuracy(), "kappa": cm.kappa(), "producers_accuracy": cm.producersAccuracy(),
                     "consumers_accuracy": cm.consumersAccuracy(), "class_counts": training.aggregate_histogram("class")}).getInfo()
acc.update(run_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"), project="(from .env)", manual_points=len(pts),
           note="Rows/columns of the confusion matrix are class codes 0-4; row/column 0 is unused (no class 0).")
RES.mkdir(parents=True, exist_ok=True)
(RES / "rf_accuracy_python.json").write_text(json.dumps(acc, indent=2))
print(f"Training pixels {acc['train_pixels']}  Test pixels {acc['test_pixels']}")
print(f"Overall accuracy {acc['overall_accuracy']:.4f}  Kappa {acc['kappa']:.4f}")
print("Class counts", acc["class_counts"])

# ---- STEP D: MODIS monsoon NDVI for high- vs low-Prosopis pixels + CHIRPS monsoon rain
# The 10 m map is used from a stored asset; recomputing it inside the loop (as banni_rf.js does) fails on Earth Engine.
import sys
import time

asset = f"projects/{PROJECT}/assets/banni_rf_classmap_2023"
if "--own-map" in sys.argv:
    asset = f"projects/{PROJECT}/assets/banni_rf_classmap_2023_python"
    try:
        ee.data.deleteAsset(asset)
    except ee.EEException:
        pass
    map_now = img23.select(bands).classify(rf).setDefaultProjection(s2proj).rename("classification").toByte()
    task = ee.batch.Export.image.toAsset(image=map_now, description="banni_rf_classmap_2023_python", assetId=asset, region=roi,
                                         crs="EPSG:32642", scale=10, pyramidingPolicy={"classification": "mode"}, maxPixels=1e10)
    task.start()
    while task.status()["state"] in ("READY", "RUNNING"):
        time.sleep(30)
    if task.status()["state"] != "COMPLETED":
        raise SystemExit(f"class-map export failed: {task.status().get('error_message')}")
map23 = ee.Image(asset).select("classification")
modis = ee.ImageCollection("MODIS/061/MOD13Q1")
mproj = ee.Image(modis.first()).select("NDVI").projection()
frac = map23.eq(1).reduceResolution(reducer=ee.Reducer.mean(), maxPixels=1024).reproject(mproj)
wfrac = map23.eq(3).reduceResolution(reducer=ee.Reducer.mean(), maxPixels=1024).reproject(mproj)
hi = frac.gt(0.4).And(wfrac.lt(0.1))
lo = frac.lt(0.05).And(wfrac.lt(0.1))


def per_year(y):
    y = ee.Number(y)
    col = modis.filterDate(ee.Date.fromYMD(y, 6, 1), ee.Date.fromYMD(y, 10, 1)).map(lambda i: i.updateMask(i.select("SummaryQA").lte(1)))
    nd = col.select("NDVI").mean().multiply(0.0001)
    mHi = nd.updateMask(hi).reduceRegion(reducer=ee.Reducer.mean(), geometry=roi, scale=250, maxPixels=1e9, tileScale=16)
    mLo = nd.updateMask(lo).reduceRegion(reducer=ee.Reducer.mean(), geometry=roi, scale=250, maxPixels=1e9, tileScale=16)
    rain = (ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY").filterDate(ee.Date.fromYMD(y, 6, 1), ee.Date.fromYMD(y, 10, 1)).sum()
            .reduceRegion(reducer=ee.Reducer.mean(), geometry=roi, scale=5566, maxPixels=1e9))
    return ee.Feature(None, {"year": y, "ndvi_hi_pros": mHi.get("NDVI"), "ndvi_lo_pros": mLo.get("NDVI"),
                             "chirps_monsoon_mm": rain.get("precipitation")})


feats = ee.FeatureCollection(ee.List.sequence(2001, 2024).map(per_year)).getInfo()["features"]
with (RES / "banni_ndvi_by_prosopis_chirps_python.csv").open("w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["year", "ndvi_hi_pros", "ndvi_lo_pros", "chirps_monsoon_mm"])
    for ft in sorted(feats, key=lambda x: x["properties"]["year"]):
        q = ft["properties"]
        w.writerow([int(q["year"]), q.get("ndvi_hi_pros"), q.get("ndvi_lo_pros"), q.get("chirps_monsoon_mm")])
print("wrote", RES / "banni_ndvi_by_prosopis_chirps_python.csv", "from", asset)
