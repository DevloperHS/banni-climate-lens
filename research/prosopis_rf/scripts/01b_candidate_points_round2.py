"""Step 1b: a second, stricter round of candidates for the two classes that were short after visual review of round 1.

Round 1 Prosopis candidates were mostly trees around farms and villages in mainland Kutch (south of Banni), so only 17
of 70 survived visual review. Round 2 asks for solid tree cover in Banni proper:
  pros   WorldCover tree (10) over >= 80% of a 40 m radius, NDVI > 0.25, no cropland (40) or built-up (50) within 300 m,
         latitude 23.55-23.90 N
  water  WorldCover water/wetland (80/90) over >= 95% of a 60 m radius, MNDWI > 0 in the 2023 dry-season composite,
         latitude 23.50-23.78 N (inland Banni wetlands, away from the Rann salt works)
As in round 1, these are only candidates: each one is accepted, relabelled or rejected after looking at its image chip.
Run from the repository root:  .venv\\Scripts\\python research\\prosopis_rf\\scripts\\01b_candidate_points_round2.py
"""
import csv
import os
from pathlib import Path

import ee

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "research" / "prosopis_rf" / "labelling" / "candidates_round2.csv"
PROJECT = os.environ.get("GCL_EE_PROJECT") or next(l.split("=", 1)[1].strip() for l in (ROOT / ".env").read_text().splitlines() if l.startswith("GCL_EE_PROJECT="))
ee.Initialize(project=PROJECT)


def mask_s2(img):
    qa = img.select("QA60")
    return img.updateMask(qa.bitwiseAnd(1 << 10).eq(0).And(qa.bitwiseAnd(1 << 11).eq(0))).divide(10000)


roi = ee.Geometry.Rectangle([69.0, 23.4, 69.9, 23.9])
s2 = (ee.ImageCollection("COPERNICUS/S2_HARMONIZED").filterBounds(roi).filterDate("2022-11-01", "2023-03-31")
      .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20)).map(mask_s2).median())
ndvi = s2.normalizedDifference(["B8", "B4"])
mndwi = s2.normalizedDifference(["B3", "B11"])
wc = ee.ImageCollection("ESA/WorldCover/v200").first().select("Map")
near = lambda m, r: m.focalMax(r, "circle", "meters")          # any pixel of mask m within r metres
share = lambda m, r: m.focalMean(r, "circle", "meters")         # fraction of a radius-r window covered by mask m

pros = (share(wc.eq(10), 40).gte(0.80).And(ndvi.gt(0.25))
        .And(near(wc.eq(40).Or(wc.eq(50)), 300).Not()))
water = share(wc.eq(80).Or(wc.eq(90)), 60).gte(0.95).And(mndwi.gt(0))

rows = []
for name, mask, box, n in [("pros", pros, [69.0, 23.55, 69.9, 23.90], 60), ("water", water, [69.0, 23.50, 69.9, 23.78], 30)]:
    fc = mask.selfMask().rename("m").toInt().stratifiedSample(numPoints=n, classBand="m", region=ee.Geometry.Rectangle(box),
                                                               scale=30, seed=23, geometries=True, tileScale=4)
    for i, ft in enumerate(fc.getInfo()["features"], 1):
        lon, lat = ft["geometry"]["coordinates"]
        rows.append([f"{name}r2_{i:03d}", name, round(lon, 6), round(lat, 6)])
OUT.parent.mkdir(parents=True, exist_ok=True)
with OUT.open("w", newline="") as f:
    csv.writer(f).writerows([["cand_id", "stratum", "lon", "lat"], *rows])
print({s: sum(r[1] == s for r in rows) for s in ("pros", "water")}, "->", OUT)
