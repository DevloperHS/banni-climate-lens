"""Step 1c: third candidate round, Prosopis woodland only, spread over NEW patches.

After spacing (03_build_training_points.py) round 2 left only 24 distinct Prosopis points because its candidates
clustered on a few woodland patches. Round 3 samples tree cover across the whole ROI with a different seed and keeps
only candidates more than 400 m from every point already in training_points.csv.
  pros   WorldCover tree (10) over >= 70% of a 30 m radius, NDVI > 0.25, no cropland (40) or built-up (50) within 300 m
Run from the repository root:  .venv\\Scripts\\python research\\prosopis_rf\\scripts\\01c_candidate_points_round3.py
"""
import csv
import math
import os
from pathlib import Path

import ee

ROOT = Path(__file__).resolve().parents[3]
LAB = ROOT / "research" / "prosopis_rf" / "labelling"
PROJECT = os.environ.get("GCL_EE_PROJECT") or next(l.split("=", 1)[1].strip() for l in (ROOT / ".env").read_text().splitlines() if l.startswith("GCL_EE_PROJECT="))
ee.Initialize(project=PROJECT)


def mask_s2(img):
    qa = img.select("QA60")
    return img.updateMask(qa.bitwiseAnd(1 << 10).eq(0).And(qa.bitwiseAnd(1 << 11).eq(0))).divide(10000)


roi = ee.Geometry.Rectangle([69.0, 23.4, 69.9, 23.9])
s2 = (ee.ImageCollection("COPERNICUS/S2_HARMONIZED").filterBounds(roi).filterDate("2022-11-01", "2023-03-31")
      .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20)).map(mask_s2).median())
ndvi = s2.normalizedDifference(["B8", "B4"])
wc = ee.ImageCollection("ESA/WorldCover/v200").first().select("Map")
pros = (wc.eq(10).focalMean(30, "circle", "meters").gte(0.70).And(ndvi.gt(0.25))
        .And(wc.eq(40).Or(wc.eq(50)).focalMax(300, "circle", "meters").Not()))
fc = pros.selfMask().rename("m").toInt().stratifiedSample(numPoints=150, classBand="m", region=roi, scale=30, seed=41,
                                                          geometries=True, tileScale=4)

existing = [(float(r["lon"]), float(r["lat"])) for r in csv.DictReader((LAB / "training_points.csv").open())]


def dist_m(a, b):
    lat = math.radians((a[1] + b[1]) / 2)
    return math.hypot((a[0] - b[0]) * 111320 * math.cos(lat), (a[1] - b[1]) * 110540)


rows = []
for ft in fc.getInfo()["features"]:
    p = tuple(ft["geometry"]["coordinates"])
    if all(dist_m(p, e) > 400 for e in existing) and all(dist_m(p, (r[2], r[3])) > 400 for r in rows):
        rows.append([f"prosr3_{len(rows) + 1:03d}", "pros", round(p[0], 6), round(p[1], 6)])
    if len(rows) == 32:
        break
with (LAB / "candidates_round3.csv").open("w", newline="") as f:
    csv.writer(f).writerows([["cand_id", "stratum", "lon", "lat"], *rows])
print(len(rows), "round-3 Prosopis candidates ->", LAB / "candidates_round3.csv")
