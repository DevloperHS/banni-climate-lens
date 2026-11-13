"""Step 1: propose CANDIDATE locations for each class, to be checked by eye on high-resolution imagery.

The candidates only make the visual search efficient. A candidate's class is NOT trusted: every point that ends up in
training_points.csv was accepted, relabelled or rejected after looking at a sub-metre image chip (02_make_chips.py).

Strata (ESA WorldCover 2021 + Sentinel-2 dry-season 2023 composite, same as banni_rf.js comp(2023)):
  pros   tree cover (10) and NDVI > 0.30            -> likely Prosopis woodland
  mix    shrub/grass (20/30) and 0.17 < NDVI < 0.30 -> likely Prosopis + grass mosaic
  water  water (80) or herbaceous wetland (90), MNDWI > 0
  brush  grass/bare (30/60) and NDVI < 0.15, MNDWI < 0 -> likely saline brushland / bare saline flats
Run from the repository root:  .venv\Scripts\python research\prosopis_rf\scripts\01_candidate_points.py
"""
import csv, os, sys
from pathlib import Path
import ee

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "research" / "prosopis_rf" / "labelling" / "candidates.csv"
PROJECT = os.environ.get("GCL_EE_PROJECT") or next(l.split("=", 1)[1].strip() for l in (ROOT / ".env").read_text().splitlines() if l.startswith("GCL_EE_PROJECT="))
ee.Initialize(project=PROJECT)

roi = ee.Geometry.Rectangle([69.0, 23.4, 69.9, 23.9])          # same ROI as banni_rf.js


def mask_s2(img):
    qa = img.select("QA60")
    m = qa.bitwiseAnd(1 << 10).eq(0).And(qa.bitwiseAnd(1 << 11).eq(0))
    return img.updateMask(m).divide(10000)


s2 = (ee.ImageCollection("COPERNICUS/S2_HARMONIZED").filterBounds(roi).filterDate("2022-11-01", "2023-03-31")
      .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20)).map(mask_s2).median())
ndvi = s2.normalizedDifference(["B8", "B4"])
mndwi = s2.normalizedDifference(["B3", "B11"])
wc = ee.ImageCollection("ESA/WorldCover/v200").first().select("Map")

strata = (ee.Image(0)
          .where(wc.eq(10).And(ndvi.gt(0.30)), 1)
          .where(wc.eq(20).Or(wc.eq(30)).And(ndvi.gt(0.17)).And(ndvi.lt(0.30)), 2)
          .where(wc.eq(80).Or(wc.eq(90)).And(mndwi.gt(0)), 3)
          .where(wc.eq(30).Or(wc.eq(60)).And(ndvi.lt(0.15)).And(mndwi.lt(0)), 4)
          .selfMask().rename("stratum").toInt())

pts = strata.stratifiedSample(numPoints=70, classBand="stratum", region=roi, scale=30, seed=11, geometries=True, tileScale=4)
feats = pts.getInfo()["features"]
names = {1: "pros", 2: "mix", 3: "water", 4: "brush"}
OUT.parent.mkdir(parents=True, exist_ok=True)
with OUT.open("w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["cand_id", "stratum", "lon", "lat"])
    counts = {}
    for ft in feats:
        s = names[ft["properties"]["stratum"]]
        counts[s] = counts.get(s, 0) + 1
        lon, lat = ft["geometry"]["coordinates"]
        w.writerow([f"{s}_{counts[s]:03d}", s, round(lon, 6), round(lat, 6)])
print("candidates:", counts, "->", OUT)
