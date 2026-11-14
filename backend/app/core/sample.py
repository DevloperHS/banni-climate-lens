"""SYNTHETIC sample data generator.

Purpose: exercise the UI, API and statistics end-to-end when no Earth Engine access exists.
Everything written here lives in data/sample/ and is stamped kind="synthetic". It is NOT an
observation and must never be presented as one. Values come from an explicit toy model:
    rain ~ gamma monsoon cycle,  NDVI = a + b*rain_lagged + trend_patch + noise.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from . import store
from .catalog import spec_dict, CATALOG
from .regions import get_region
from ..science.pixel import write_geotiff
from ..science.processing import days_in_month

DISCLAIMER = ("SYNTHETIC SAMPLE DATA generated from a toy model for software testing. "
              "These are not satellite observations and carry no scientific meaning.")


def _prov(key, region_id, y0, y1):
    return {**spec_dict(key), "region": region_id, "processing_period": f"{y0}-{y1}", "kind": "synthetic",
            "retrieval_date": None, "disclaimer": DISCLAIMER,
            "processing_config": {"generator": "app.core.sample", "seed": 42}}


def generate(region_id: str = "banni", seed: int = 42) -> dict:
    region = get_region(region_id)
    y0, y1 = region["study_period"]["start"], region["study_period"]["end"]
    rng = np.random.default_rng(seed)
    idx = pd.date_range(f"{y0}-01-01", f"{y1}-12-01", freq="MS")
    mon = idx.month.values
    # monsoon-dominated rainfall: annual wetness factor x seasonal shape
    wet = {y: rng.gamma(2.0, 0.5) for y in range(y0, y1 + 1)}
    seas = {1: .005, 2: .005, 3: .005, 4: .005, 5: .01, 6: .12, 7: .38, 8: .32, 9: .12, 10: .02, 11: .005, 12: .005}
    precip = np.array([wet[d.year] * 380 * seas[d.month] * rng.gamma(4, 0.25) for d in idx])
    p = pd.Series(precip, index=idx)
    lag = p.rolling(3, min_periods=1).sum().values
    t = (idx.year - y0 + (mon - 1) / 12).values
    ndvi = 0.08 + 0.00028 * lag + 0.0035 * t + rng.normal(0, 0.008, len(idx))
    ndvi = np.clip(ndvi, 0.02, 0.9)
    lst_d = 33 + 9 * np.sin(2 * np.pi * (mon - 3.5) / 12) + 0.03 * t + rng.normal(0, 0.6, len(idx))
    lst_n = 19 + 8 * np.sin(2 * np.pi * (mon - 3.5) / 12) + 0.02 * t + rng.normal(0, 0.5, len(idx))
    et = np.maximum(3 + 0.22 * lag * 0.35 + rng.normal(0, 2, len(idx)), 0)
    sm_s = 12 + 0.02 * lag + rng.normal(0, 0.4, len(idx))
    sm_r = 90 + 0.07 * lag + rng.normal(0, 1.5, len(idx))
    water = np.maximum(0.5 + 0.02 * lag + rng.normal(0, 0.3, len(idx)), 0)
    series = {"ndvi": ndvi, "precip": precip, "lst_day": lst_d, "lst_night": lst_n, "et": et,
              "sm_surface": sm_s, "sm_root": sm_r, "water_extent": water}
    for key, vals in series.items():
        store.save_series("sample", region_id, key, {d.strftime("%Y-%m"): float(v) for d, v in zip(idx, vals)},
                          _prov(key, region_id, y0, y1), kind="synthetic")
    # Landsat-like: October value per year = Sep-Oct MODIS-like mean + offset + noise, with gaps
    ls = {}
    for y in range(y0, y1 + 1):
        if rng.uniform() < 0.85:
            m = ndvi[(idx.year == y) & np.isin(mon, [9, 10])].mean()
            ls[f"{y}-10"] = float(m * 1.05 + rng.normal(0, 0.01))
    store.save_series("sample", region_id, "ndvi_landsat", ls, _prov("ndvi_landsat", region_id, y0, y1), kind="synthetic")

    # --- raster stacks (small synthetic grid) with a gradient of NDVI trends
    from rasterio.transform import from_bounds
    from rasterio.crs import CRS
    b = region["bbox"]; H, W = 60, 90
    tr = from_bounds(b["west"], b["south"], b["east"], b["north"], W, H)
    yy, xx = np.mgrid[0:H, 0:W]
    patch = np.exp(-(((xx - 25) / 14) ** 2 + ((yy - 20) / 10) ** 2)) - 0.6 * np.exp(-(((xx - 65) / 10) ** 2 + ((yy - 42) / 9) ** 2))
    years = np.arange(y0, y1 + 1)
    for key, season in [("ndvi", "annual"), ("ndvi", "monsoon"), ("precip", "monsoon"), ("lst_day", "summer"),
                        ("et", "annual"), ("sm_root", "annual")]:
        base = {"ndvi": 0.22, "precip": 400, "lst_day": 40, "et": 250, "sm_root": 95}[key]
        amp = {"ndvi": 0.0035, "precip": 3.0, "lst_day": 0.04, "et": 1.5, "sm_root": 0.1}[key]
        noise = {"ndvi": 0.015, "precip": 40, "lst_day": 0.6, "et": 12, "sm_root": 1.2}[key]
        arr = np.stack([base + (yv - y0) * amp * (1 + 2 * patch) + 0.15 * base * np.sin(xx / 17.0) * 0.3
                        + rng.normal(0, noise, (H, W)) for yv in years]).astype("float32")
        path = store.raster_path("sample", region_id, key, season)
        write_geotiff(path, {f"y{yv}": arr[i] for i, yv in enumerate(years)}, tr, CRS.from_epsg(4326),
                      {"kind": "synthetic", "disclaimer": DISCLAIMER, "key": key, "season": season})
    # --- extra synthetic series
    nowater = {d.strftime("%Y-%m"): float(v) * 0.97 for d, v in zip(idx, ndvi)}
    store.save_series("sample", region_id, "ndvi_nowater", nowater, _prov("ndvi_nowater", region_id, y0, y1), kind="synthetic")
    sal = {f"{y}-04": float(0.30 + 0.002 * (y - y0) + rng.normal(0, 0.01)) for y in range(y0, y1 + 1)}
    store.save_series("sample", region_id, "salinity_index", sal, _prov("salinity_index", region_id, y0, y1), kind="synthetic")
    # --- extra rasters: dry-season NDVI, Landsat-like finer NDVI (2x grid), salinity proxy, static water occurrence
    def stack(key, season, base, amp, noise, Hh, Ww, patchscale=2.0):
        trh = from_bounds(b["west"], b["south"], b["east"], b["north"], Ww, Hh)
        yy2, xx2 = np.mgrid[0:Hh, 0:Ww]
        k = Ww / 90.0
        p2 = np.exp(-(((xx2 / k - 25) / 14) ** 2 + ((yy2 / k - 20) / 10) ** 2)) - 0.6 * np.exp(-(((xx2 / k - 65) / 10) ** 2 + ((yy2 / k - 42) / 9) ** 2))
        arr = np.stack([base + (yv - y0) * amp * (1 + patchscale * p2) + rng.normal(0, noise, (Hh, Ww)) for yv in years]).astype("float32")
        write_geotiff(store.raster_path("sample", region_id, key, season), {f"y{yv}": arr[i] for i, yv in enumerate(years)}, trh, CRS.from_epsg(4326),
                      {"kind": "synthetic", "disclaimer": DISCLAIMER, "key": key, "season": season})
    stack("ndvi", "summer", 0.12, 0.004, 0.012, H, W, 3.0)                 # dry-season greenness grows most where the patch is (toy 'evergreen' signal)
    stack("ndvi", "peak", 0.25, 0.0035, 0.015, H, W)                      # MODIS-like Sep-Oct stack for the Landsat comparison
    stack("ndvi_landsat", "peak", 0.25, 0.0035, 0.02, 2 * H, 2 * W)
    stack("salinity_index", "summer", 0.30, 0.0015, 0.01, H, W)
    occ = np.zeros((H, W), "float32"); occ[:6, :] = 85; occ[:, :4] = 60; occ += rng.uniform(0, 3, (H, W)).astype("float32")
    write_geotiff(store.raster_path("sample", region_id, "water_occurrence", "static"), {"occurrence": occ}, tr, CRS.from_epsg(4326),
                  {"kind": "synthetic", "disclaimer": DISCLAIMER, "key": "water_occurrence", "season": "static"})
    # --- cross-sensor / cross-index check series (own generator, so the series above are unchanged).
    # Toy 'Aqua' NDVI = Terra + small offset + noise, starting Jul 2002 like the real record; toy EVI = scaled NDVI.
    rng2 = np.random.default_rng(seed + 1)
    aqua = {d.strftime("%Y-%m"): float(v - 0.004 + rng2.normal(0, 0.006)) for d, v in zip(idx, ndvi) if d >= pd.Timestamp("2002-07-01")}
    store.save_series("sample", region_id, "ndvi_aqua", aqua, _prov("ndvi_aqua", region_id, y0, y1), kind="synthetic")
    evi = {d.strftime("%Y-%m"): float(0.62 * v + 0.01 + rng2.normal(0, 0.005)) for d, v in zip(idx, ndvi)}
    store.save_series("sample", region_id, "evi", evi, _prov("evi", region_id, y0, y1), kind="synthetic")
    return {"series": len(series) + 5, "rasters": 11, "disclaimer": DISCLAIMER}
