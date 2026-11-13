"""Step 12a: farmland shares per MODIS pixel, stored once as an Earth Engine asset (input for 12_farming_test.py).

The random-forest map has no cropland class, so farmland comes from two independent global maps:
  wc_crop       ESA WorldCover v200 (2021), class 40 "Cropland", 10 m
  dw_crop_early Google Dynamic World V1, 10 m: share of 10 m pixels whose most common label (mode) from August to December
                of 2016 and 2017 is "crops" (label 4). Aug-Dec covers the kharif (monsoon) crop and its harvest.
  dw_crop_late  the same for 2023 and 2024
  wc_water      ESA WorldCover classes 80 (permanent water) + 90 (herbaceous wetland), used to leave out watery pixels
Each band is the mean of the 0/1 10 m map inside each MODIS MOD13Q1 pixel (reduceResolution), exported on the MODIS grid
over the platform rectangle (68.80-69.95 E, 23.20-23.95 N), which also contains the script ROI.

Run from the repository root:  .venv\\Scripts\\python research\\prosopis_rf\\scripts\\12a_export_cropland.py
Creates projects/<project>/assets/banni_cropland_fractions_modis and waits for the task to finish.
"""
import os
import time
from pathlib import Path

import ee

ROOT = Path(__file__).resolve().parents[3]
PROJECT = os.environ.get("GCL_EE_PROJECT") or next(l.split("=", 1)[1].strip() for l in (ROOT / ".env").read_text().splitlines() if l.startswith("GCL_EE_PROJECT="))
ee.Initialize(project=PROJECT)
ASSET = f"projects/{PROJECT}/assets/banni_cropland_fractions_modis"

box = ee.Geometry.Rectangle([68.80, 23.20, 69.95, 23.95])
mp = ee.Image(ee.ImageCollection("MODIS/061/MOD13Q1").first()).select("NDVI").projection().getInfo()
mproj = ee.Projection(mp["crs"], mp["transform"])
utm10 = ee.Projection("EPSG:32642").atScale(10)

wc = ee.ImageCollection("ESA/WorldCover/v200").first().select("Map")
wc_proj = wc.projection()


def dw_crop(years):
    col = ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterBounds(box)
    parts = [col.filterDate(f"{y}-08-01", f"{y + 1}-01-01") for y in years]
    merged = parts[0]
    for p in parts[1:]:
        merged = merged.merge(p)
    return merged.select("label").mode().eq(4).setDefaultProjection(utm10)


def to_modis(img, proj):
    return img.setDefaultProjection(proj).reduceResolution(reducer=ee.Reducer.mean(), maxPixels=1024).reproject(mproj)


bands = ee.Image.cat([
    to_modis(wc.eq(40), wc_proj).rename("wc_crop"),
    to_modis(wc.eq(80).Or(wc.eq(90)), wc_proj).rename("wc_water"),
    to_modis(dw_crop([2016, 2017]), utm10).rename("dw_crop_early"),
    to_modis(dw_crop([2023, 2024]), utm10).rename("dw_crop_late"),
]).toFloat()

try:
    ee.data.deleteAsset(ASSET)
    print("old asset removed")
except ee.EEException:
    pass
task = ee.batch.Export.image.toAsset(image=bands, description="banni_cropland_fractions_modis", assetId=ASSET, region=box,
                                     crs=mp["crs"], crsTransform=mp["transform"], maxPixels=1e10)
task.start()
print("started", task.id, flush=True)
while task.status()["state"] in ("UNSUBMITTED", "READY", "RUNNING"):
    time.sleep(30)
st = task.status()
print(st["state"], st.get("error_message", ""), "EECU-seconds:", st.get("batch_eecu_usage_seconds"))
