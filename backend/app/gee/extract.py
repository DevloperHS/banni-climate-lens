"""Earth Engine extraction. Server-side work is limited to quality masking, scale factors and
a regional mean per image; all temporal aggregation and unit conversion runs in
`science.processing` (unit-tested without Earth Engine).

NOTE: this module needs live credentials (docs/SETUP.md). It was run against the live service on
12-13 Nov 2026; `verify_dataset_bands()` is a metadata sanity check.
"""
from __future__ import annotations
import json
import logging
from datetime import date, datetime, timezone
from typing import Callable
import numpy as np

from ..core.catalog import CATALOG, spec_dict
from ..core.regions import get_region
from ..science import processing as P
from .cancel import check_cancel
from .client import get_ee

log = logging.getLogger("gcl.gee")
SENTINEL = -9999.0


def _geom(ee, region: dict):
    if region.get("polygon"):
        return ee.Geometry(region["polygon"], "EPSG:4326", False)
    b = region["bbox"]
    return ee.Geometry.Rectangle([b["west"], b["south"], b["east"], b["north"]], proj="EPSG:4326", geodesic=False)


# ----------------------------------------------------------------- masking / scaling per product
def _mask_modis_ndvi(ee, img):
    qa = img.select("SummaryQA")
    ndvi = img.select("NDVI").updateMask(img.select("NDVI").neq(P.MODIS_NDVI_FILL)).multiply(P.MODIS_NDVI_SCALE)
    return ndvi.updateMask(qa.eq(0)).rename("v").copyProperties(img, ["system:time_start"])


def _mask_lst(ee, img, band: str, qc_band: str):
    qc = img.select(qc_band)
    ok = qc.bitwiseAnd(3).lte(1).And(qc.rightShift(6).bitwiseAnd(3).lte(1))
    k = img.select(band).multiply(P.LST_SCALE)
    return k.subtract(273.15).updateMask(ok.And(img.select(band).gt(0))).rename("v").copyProperties(img, ["system:time_start"])


def _mask_et(ee, img):
    et = img.select("ET")
    return et.updateMask(et.lte(P.ET_FILL_MIN)).multiply(P.ET_SCALE).rename("v").copyProperties(img, ["system:time_start"])


def _landsat_ndvi_collection(ee, geom, year: int):
    """Peak-season (Sep-Oct) clear-sky NDVI median composite, one per year."""
    start, end = f"{year}-09-01", f"{year}-11-01"
    sets = []
    if 1999 <= year <= 2011:
        sets.append(("LANDSAT/LT05/C02/T1_L2", "SR_B4", "SR_B3"))
    if 1999 <= year <= 2024:
        sets.append(("LANDSAT/LE07/C02/T1_L2", "SR_B4", "SR_B3"))
    if year >= 2013:
        sets.append(("LANDSAT/LC08/C02/T1_L2", "SR_B5", "SR_B4"))
    if year >= 2021:
        sets.append(("LANDSAT/LC09/C02/T1_L2", "SR_B5", "SR_B4"))

    def make_prep(nir, red):          # factory: returns the ONE-argument map callback
        def f(img):
            qa = img.select("QA_PIXEL")
            clear = qa.bitwiseAnd(1 << 1).eq(0).And(qa.bitwiseAnd(1 << 3).eq(0)) \
                .And(qa.bitwiseAnd(1 << 4).eq(0)).And(qa.bitwiseAnd(1 << 5).eq(0))
            n = img.select(nir).multiply(P.LANDSAT_SR_SCALE).add(P.LANDSAT_SR_OFFSET)
            r = img.select(red).multiply(P.LANDSAT_SR_SCALE).add(P.LANDSAT_SR_OFFSET)
            return n.subtract(r).divide(n.add(r)).rename("v").updateMask(clear)
        return f

    colls = [ee.ImageCollection(cid).filterBounds(geom).filterDate(start, end).map(make_prep(n, r)) for cid, n, r in sets]
    merged = colls[0]
    for c in colls[1:]:
        merged = merged.merge(c)
    return merged


# ----------------------------------------------------------------- generic reducers
def _per_image_means(ee, coll, geom, scale: int, chunk_years: tuple[int, int]) -> list[tuple[date, float | None]]:
    y0, y1 = chunk_years
    sub = coll.filterDate(f"{y0}-01-01", f"{y1 + 1}-01-01")

    def f(img):
        d = img.reduceRegion(reducer=ee.Reducer.mean(), geometry=geom, scale=scale, maxPixels=int(1e9), bestEffort=True)
        return ee.Feature(None, {"t": img.get("system:time_start"), "v": ee.Algorithms.If(d.contains("v"), d.get("v"), SENTINEL)})

    feats = sub.map(f).getInfo()["features"]
    out = []
    for ft in feats:
        pr = ft["properties"]
        v = pr.get("v")
        out.append((P.ms_to_date(pr["t"]), None if v is None or v == SENTINEL else float(v)))
    return sorted(out)


def _collect(ee, coll, geom, scale, start_year, end_year, step=4):
    rows = []
    for y in range(start_year, end_year + 1, step):
        check_cancel()
        rows += _per_image_means(ee, coll, geom, scale, (y, min(y + step - 1, end_year)))
    return rows


# ----------------------------------------------------------------- per-dataset monthly series
def monthly_ndvi(ee, region, y0, y1):
    """HANDOVER PROTOCOL (handover p.5): for each calendar month, mean of all MOD13Q1 images whose date falls in
    the month (no SummaryQA mask), x0.0001, then regional mean at 250 m. Returns (months, raw) where raw keeps the
    number of composites behind every month."""
    return monthly_modis_vi(ee, region, y0, y1, "MODIS/061/MOD13Q1", "NDVI")


def monthly_modis_vi(ee, region, y0, y1, collection: str, band: str):
    """The handover NDVI protocol applied to any 250 m MODIS vegetation-index band (MOD13Q1 / MYD13Q1, NDVI or EVI;
    both bands share the 0.0001 scale). Used for the cross-sensor (Aqua) and cross-index (EVI) checks so that the only
    difference from `ndvi` is the satellite or the index."""
    geom = _geom(ee, region)
    coll = ee.ImageCollection(collection).select(band)
    months, raw = {}, []
    for y in range(y0, y1 + 1):
        check_cancel()
        def per_month(m):
            s = ee.Date.fromYMD(y, m, 1)
            sub = coll.filterDate(s, s.advance(1, "month"))
            # A month with no composites (Aqua before 4 Jul 2002) gives a band-less mean image; substitute a fully
            # masked image of the same band so the reduction returns nothing and the month is recorded as missing.
            img = ee.Image(ee.Algorithms.If(sub.size().gt(0), sub.mean(), ee.Image.constant(0).rename(band).updateMask(0)))
            d = img.multiply(P.MODIS_NDVI_SCALE).reduceRegion(ee.Reducer.mean(), geom, 250, maxPixels=int(1e9))
            return ee.Feature(None, {"m": m, "n": sub.size(), "v": ee.Algorithms.If(d.contains(band), d.get(band), SENTINEL)})
        for ft in ee.FeatureCollection(ee.List.sequence(1, 12).map(per_month)).getInfo()["features"]:
            pr = ft["properties"]
            ok = pr.get("n", 0) > 0 and pr.get("v") not in (None, SENTINEL)
            raw.append({"month": f"{y:04d}-{pr['m']:02d}", "n_images": pr.get("n", 0), "value": float(pr["v"]) if ok else None})
            if ok:
                months[f"{y:04d}-{pr['m']:02d}"] = float(pr["v"])
    return months, raw


def annual_ndvi_image_mean(ee, region, y0, y1):
    """Handover p.4 'mini test': per calendar year the PIXEL-WISE mean of every MOD13Q1 image (filterDate(YYYY-01-01,
    YYYY-12-31), x0.0001), then the regional mean at 250 m. Differs from an average of monthly means wherever pixels are
    masked in some composites but not others, so it is retrieved directly. Saved as a raw artifact, not a series."""
    geom = _geom(ee, region)
    coll = ee.ImageCollection("MODIS/061/MOD13Q1").select("NDVI")
    rows = []
    for y in range(y0, y1 + 1):
        check_cancel()
        sub = coll.filterDate(f"{y}-01-01", f"{y}-12-31")
        d = sub.mean().multiply(P.MODIS_NDVI_SCALE).reduceRegion(ee.Reducer.mean(), geom, 250, maxPixels=int(1e9)).getInfo()
        rows.append({"year": y, "n_images": sub.size().getInfo(), "value": (d or {}).get("NDVI")})
    return rows


def annual_handover_water_table(ee, region, y0, y1):
    """Handover pp.10-11 water table, computed exactly as its script does (geometry: the rectangle):
       et_annual_mm      = regional mean (500 m) of the pixel-wise SUM of all MOD16A2GF ET composites in the year x 0.1
       sm_root_annual    = regional mean (27830 m) of the mean of all GLDAS RootMoist_inst images in the year
       sm_surface_annual = same for SoilMoi0_10cm_inst;  sm_root_dry = RootMoist_inst mean over 1 Mar - 1 Jun."""
    geom = _geom(ee, region)
    et = ee.ImageCollection("MODIS/061/MOD16A2GF").select("ET")
    gl = ee.ImageCollection("NASA/GLDAS/V021/NOAH/G025/T3H").select(["RootMoist_inst", "SoilMoi0_10cm_inst"])

    def rm(img, scale):
        return img.reduceRegion(reducer=ee.Reducer.mean(), geometry=geom, scale=scale, maxPixels=int(1e9), bestEffort=True)

    rows = []
    for y in range(y0, y1 + 1):
        check_cancel()
        s0, s1 = ee.Date.fromYMD(y, 1, 1), ee.Date.fromYMD(y + 1, 1, 1)
        et_v = rm(et.filterDate(s0, s1).sum().multiply(0.1), 500).get("ET")
        sm = rm(gl.filterDate(s0, s1).mean(), 27830)
        dry = rm(gl.filterDate(ee.Date.fromYMD(y, 3, 1), ee.Date.fromYMD(y, 6, 1)).mean(), 27830)
        r = ee.Dictionary({"et": et_v, "root": sm.get("RootMoist_inst"), "surf": sm.get("SoilMoi0_10cm_inst"), "dry": dry.get("RootMoist_inst"),
                           "n_et": et.filterDate(s0, s1).size()}).getInfo()
        rows.append({"year": y, "et_annual_mm": r.get("et"), "sm_root_annual": r.get("root"), "sm_surface_annual": r.get("surf"),
                     "sm_root_dry": r.get("dry"), "n_et_composites": r.get("n_et")})
    return rows


def raw_artifact_provenance_base(key: str) -> dict:
    """Dataset description for a raw artifact. Each artifact describes the products it actually read: the water table holds
    MODIS ET and GLDAS soil moisture (not wells, not NDVI), so it must not inherit the NDVI catalogue entry."""
    if key == "ndvi_annual_image_mean":
        return {**spec_dict("ndvi"),
                "processing_config": {"protocol": "handover p.4: pixel-wise mean of all images in the calendar year, regional mean at 250 m"}}
    if key == "handover_water_table":
        et, sm = spec_dict("et"), spec_dict("sm_root")
        return {"key": key, "label": "Handover water table: annual ET and GLDAS soil moisture (not well measurements)",
                "group": "water", "ee_id": f"{et['ee_id']} + {sm['ee_id']}", "provider": f"{et['provider']}; {sm['provider']}",
                "variable": "ET (annual sum of 8-day composites x 0.1); RootMoist_inst and SoilMoi0_10cm_inst (annual and Mar-May means)",
                "spatial_resolution": f"ET {et['spatial_resolution']}; GLDAS {sm['spatial_resolution']}", "temporal_resolution": "annual",
                "unit": "ET mm/yr; soil moisture kg/m2", "scale_factor": "ET 0.1; GLDAS 1", "quality_filter": "ET fill values masked; GLDAS none",
                "limitations": "Contains no groundwater or depth-to-water observations. ET partly echoes NDVI (MOD16 uses MODIS LAI); GLDAS is a ~28 km model.",
                "processing_config": {"protocol": "handover pp.10-11: ET = pixel-wise sum of the year's composites x 0.1 at 500 m; "
                                                  "soil moisture = mean of all 3-hourly GLDAS images in the year (and Mar-May) at 27830 m"}}
    raise KeyError(key)


def run_raw_artifact(key: str, region_id: str, y0: int, y1: int) -> dict:
    from ..core import store
    ee = get_ee()
    fn = {"ndvi_annual_image_mean": annual_ndvi_image_mean, "handover_water_table": annual_handover_water_table}[key]
    rows = fn(ee, get_region(region_id), y0, y1)
    bad = [r["year"] for r in rows if any(v is None for k, v in r.items() if k not in ("year", "n_images", "n_et_composites"))]
    if bad:
        raise RuntimeError(f"{key}: missing values for years {bad}; nothing stored")
    prov = {**raw_artifact_provenance_base(key), "region": region_id, "processing_period": f"{y0}-{y1}",
            "retrieval_date": datetime.now(timezone.utc).date().isoformat(),
            "geometry": get_region(region_id)["geometry"], "artifact": key, "kind": "observed"}
    p = store.save_raw(region_id, key, rows, prov)
    return {"key": key, "years": len(rows), "file": p.name}


def monthly_ndvi_qa(ee, region, y0, y1):
    """Sensitivity: SummaryQA==0 per pixel, regional mean per composite, month by composite midpoint."""
    geom = _geom(ee, region)
    coll = ee.ImageCollection("MODIS/061/MOD13Q1").filterBounds(geom).map(lambda i: _mask_modis_ndvi(ee, i))
    rows = _collect(ee, coll, geom, 250, y0, y1)
    raw = [{"date": d.isoformat(), "value": v} for d, v in rows]
    return P.composites_to_monthly([d for d, _ in rows], [v for _, v in rows], "mean", [16] * len(rows)), raw


def monthly_lst(ee, region, y0, y1, night: bool):
    band, qc = ("LST_Night_1km", "QC_Night") if night else ("LST_Day_1km", "QC_Day")
    coll = ee.ImageCollection("MODIS/061/MOD11A2").filterBounds(_geom(ee, region)).map(lambda i: _mask_lst(ee, i, band, qc))
    rows = _collect(ee, coll, _geom(ee, region), 1000, y0, y1)
    return P.composites_to_monthly([d for d, _ in rows], [v for _, v in rows], "mean", [8] * len(rows))


def monthly_et(ee, region, y0, y1):
    coll = ee.ImageCollection("MODIS/061/MOD16A2GF").filterBounds(_geom(ee, region)).map(lambda i: _mask_et(ee, i))
    rows = _collect(ee, coll, _geom(ee, region), 500, y0, y1)
    spans = [P.composite_span_days(d) for d, _ in rows]
    return P.composites_to_monthly([d for d, _ in rows], [v for _, v in rows], "sum", spans)


def monthly_precip(ee, region, y0, y1):
    """HANDOVER PROTOCOL (handover p.6): total = rate(mm/hr; unit verified against the Earth Engine catalogue)
    x 24 x days, days = (system:time_end - system:time_start) in days; regional mean at 11132 m. The day count is
    compared with the calendar month length and any disagreement is recorded in `raw`."""
    geom = _geom(ee, region)
    coll = ee.ImageCollection("NASA/GPM_L3/IMERG_MONTHLY_V07").select("precipitation")
    out, raw = {}, []
    for y in range(y0, y1 + 1):
        check_cancel()
        def f(img):
            d = img.reduceRegion(ee.Reducer.mean(), geom, 11132, maxPixels=int(1e9))
            return ee.Feature(None, {"t": img.get("system:time_start"), "t1": img.get("system:time_end"),
                                     "v": ee.Algorithms.If(d.contains("precipitation"), d.get("precipitation"), SENTINEL)})
        for ft in coll.filterDate(f"{y}-01-01", f"{y + 1}-01-01").map(f).getInfo()["features"]:
            pr = ft["properties"]; d0 = P.ms_to_date(pr["t"])
            days = (pr["t1"] - pr["t"]) / 86400000.0
            rate = pr.get("v")
            ok = rate not in (None, SENTINEL)
            cal = P.days_in_month(d0.year, d0.month)
            raw.append({"month": f"{d0.year:04d}-{d0.month:02d}", "rate_mm_hr": rate if ok else None,
                        "days_end_minus_start": days, "days_calendar": cal, "days_agree": abs(days - cal) < 1e-6})
            if ok:
                out[f"{d0.year:04d}-{d0.month:02d}"] = float(rate) * 24.0 * days
    return out, raw


def monthly_soil_moisture(ee, region, y0, y1, root_zone: bool):
    """GLDAS is 3-hourly (~70k images over the study period): average per month server-side."""
    geom = _geom(ee, region)
    bands = ["RootMoist_inst"] if root_zone else ["SoilMoi0_10cm_inst"]    # handover pp.10-11 use exactly these bands
    coll = ee.ImageCollection("NASA/GLDAS/V021/NOAH/G025/T3H").select(bands)
    out = {}
    for y in range(y0, y1 + 1):
        def per_month(m):
            s = ee.Date.fromYMD(y, m, 1)
            sub = coll.filterDate(s, s.advance(1, "month"))
            img = sub.mean().reduce(ee.Reducer.sum()).rename("v")
            d = img.reduceRegion(ee.Reducer.mean(), geom, 27830, maxPixels=int(1e9), bestEffort=True)
            return ee.Feature(None, {"m": m, "n": sub.size(), "v": ee.Algorithms.If(d.contains("v"), d.get("v"), SENTINEL)})
        feats = ee.FeatureCollection(ee.List.sequence(1, 12).map(per_month)).getInfo()["features"]
        for ft in feats:
            pr = ft["properties"]
            if pr.get("n", 0) > 0 and pr.get("v") not in (None, SENTINEL):
                out[f"{y:04d}-{pr['m']:02d}"] = float(pr["v"])
    return out


def monthly_water_extent(ee, region, y0, y1):
    geom = _geom(ee, region)
    coll = ee.ImageCollection("JRC/GSW1_4/MonthlyHistory").filterBounds(geom)
    area = ee.Image.pixelArea()

    def f(img):
        water = img.eq(2).multiply(area).rename("w")
        valid = img.gt(0).multiply(area).rename("a")
        d = water.addBands(valid).reduceRegion(ee.Reducer.sum(), geom, 30, maxPixels=int(1e10), bestEffort=True)
        return ee.Feature(None, {"t": img.get("system:time_start"), "w": d.get("w"), "a": d.get("a")})

    out = {}
    total = _geom(ee, region).area(1).getInfo()
    for y in range(y0, y1 + 1):
        feats = coll.filterDate(f"{y}-01-01", f"{y + 1}-01-01").map(f).getInfo()["features"]
        for ft in feats:
            pr = ft["properties"]
            if pr.get("w") is None or pr.get("a") is None:
                continue
            if pr["a"] / total < 0.5:      # < 50% valid optical coverage -> drop month
                continue
            d = P.ms_to_date(pr["t"])
            out[f"{d.year:04d}-{d.month:02d}"] = float(pr["w"]) / 1e6
    return out


def annual_landsat_ndvi(ee, region, y0, y1):
    geom = _geom(ee, region)
    out = {}
    for y in range(max(y0, 2000), y1 + 1):
        coll = _landsat_ndvi_collection(ee, geom, y)
        n = coll.size().getInfo()
        if n < 1:
            continue
        d = coll.median().reduceRegion(ee.Reducer.mean(), geom, 30, maxPixels=int(1e10), bestEffort=True, tileScale=4).getInfo()
        if d and d.get("v") is not None:
            out[f"{y:04d}-10"] = float(d["v"])      # Sep-Oct composite assigned to October
    return out



# ----------------------------------------------------------------- water mask, salinity, MNDWI (Landsat)
WATER_OCC_THRESHOLD = 10.0     # percent; pixels at/above this long-term occurrence are treated as Rann / open water


def _water_mask(ee, threshold: float = WATER_OCC_THRESHOLD):
    occ = ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence").unmask(0)
    return occ.lt(threshold)


def monthly_ndvi_nowater(ee, region, y0, y1):
    """Handover NDVI protocol with Rann-water pixels removed (see catalogue note on the threshold)."""
    geom = _geom(ee, region)
    keep = _water_mask(ee)
    coll = ee.ImageCollection("MODIS/061/MOD13Q1").select("NDVI")
    months, raw = {}, []
    for y in range(y0, y1 + 1):
        check_cancel()
        def per_month(m):
            st = ee.Date.fromYMD(y, m, 1)
            sub = coll.filterDate(st, st.advance(1, "month"))
            img = sub.mean().multiply(P.MODIS_NDVI_SCALE).updateMask(keep)
            d = img.reduceRegion(ee.Reducer.mean(), geom, 250, maxPixels=int(1e9))
            return ee.Feature(None, {"m": m, "n": sub.size(), "v": ee.Algorithms.If(d.contains("NDVI"), d.get("NDVI"), SENTINEL)})
        for ft in ee.FeatureCollection(ee.List.sequence(1, 12).map(per_month)).getInfo()["features"]:
            pr = ft["properties"]
            ok = pr.get("n", 0) > 0 and pr.get("v") not in (None, SENTINEL)
            raw.append({"month": f"{y:04d}-{pr['m']:02d}", "n_images": pr.get("n", 0), "value": float(pr["v"]) if ok else None,
                        "water_threshold_pct": WATER_OCC_THRESHOLD})
            if ok:
                months[f"{y:04d}-{pr['m']:02d}"] = float(pr["v"])
    return months, raw


def _landsat_prepared(ee, geom, start: str, end: str):
    """Cloud-masked Landsat surface reflectance with unified band names (B, G, R, N, S1), scaled to reflectance."""
    sets = [("LANDSAT/LT05/C02/T1_L2", ["SR_B1", "SR_B2", "SR_B3", "SR_B4", "SR_B5"]), ("LANDSAT/LE07/C02/T1_L2", ["SR_B1", "SR_B2", "SR_B3", "SR_B4", "SR_B5"]),
            ("LANDSAT/LC08/C02/T1_L2", ["SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B6"]), ("LANDSAT/LC09/C02/T1_L2", ["SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B6"])]
    merged = None
    def make_prep(bands):                 # Earth Engine map() needs a ONE-argument function: bind `bands` by closure
        def prep(img):
            qa = img.select("QA_PIXEL")
            clear = qa.bitwiseAnd(1 << 1).eq(0).And(qa.bitwiseAnd(1 << 3).eq(0)).And(qa.bitwiseAnd(1 << 4).eq(0)).And(qa.bitwiseAnd(1 << 5).eq(0))
            return img.select(bands, ["B", "G", "R", "N", "S1"]).multiply(P.LANDSAT_SR_SCALE).add(P.LANDSAT_SR_OFFSET).updateMask(clear)
        return prep

    for cid, bands in sets:
        c = ee.ImageCollection(cid).filterBounds(geom).filterDate(start, end).map(make_prep(bands))
        merged = c if merged is None else merged.merge(c)
    return merged


def annual_salinity_index(ee, region, y0, y1):
    """SI1 = sqrt(G*R) on the Mar-May (dry-season) median composite, regional mean at 120 m. One value per year (stored in April)."""
    geom = _geom(ee, region)
    out, raw = {}, []
    for y in range(max(y0, 2000), y1 + 1):
        check_cancel()
        coll = _landsat_prepared(ee, geom, f"{y}-03-01", f"{y}-06-01")
        n = coll.size().getInfo()
        if n < 1:
            raw.append({"year": y, "n_scenes": 0, "value": None}); continue
        si = coll.median().expression("sqrt(G * R)", {"G": coll.median().select("G"), "R": coll.median().select("R")}).rename("v")
        d = si.reduceRegion(ee.Reducer.mean(), geom, 120, maxPixels=int(1e10), bestEffort=True, tileScale=4).getInfo()
        v = (d or {}).get("v")
        raw.append({"year": y, "n_scenes": n, "value": v})
        if v is not None:
            out[f"{y:04d}-04"] = float(v)
    return out, raw


def monthly_water_mndwi(ee, region, y0, y1):
    """Monthly open-water area (km2) from Landsat 8/9 MNDWI > 0; months with <50% clear coverage are dropped."""
    geom = _geom(ee, region)
    total = geom.area(1).getInfo()
    out, raw = {}, []
    for y in range(max(y0, 2013), y1 + 1):
        check_cancel()
        for m in range(1, 13):
            st = ee.Date.fromYMD(y, m, 1)
            coll = _landsat_prepared(ee, geom, st.format("YYYY-MM-dd").getInfo(), st.advance(1, "month").format("YYYY-MM-dd").getInfo())
            if coll.size().getInfo() < 1:
                raw.append({"month": f"{y}-{m:02d}", "n_scenes": 0}); continue
            img = coll.median()
            mn = img.normalizedDifference(["G", "S1"])
            area = ee.Image.pixelArea()
            d = mn.gt(0).multiply(area).rename("w").addBands(mn.mask().multiply(area).rename("a")).reduceRegion(
                ee.Reducer.sum(), geom, 60, maxPixels=int(1e10), bestEffort=True, tileScale=4).getInfo()
            cov = (d.get("a") or 0) / total
            raw.append({"month": f"{y}-{m:02d}", "coverage": cov, "water_km2": (d.get("w") or 0) / 1e6})
            if cov >= 0.5:
                out[f"{y:04d}-{m:02d}"] = float(d["w"]) / 1e6
    return out, raw


LANDCOVER_CLASSES = {"lc_grassland": (10,), "lc_shrubland": (6, 7), "lc_savanna": (8, 9), "lc_cropland": (12, 14),
                     "lc_barren": (16,), "lc_water": (11, 17)}


def annual_landcover_share(ee, region, y0, y1, key: str):
    """Yearly share (%) of the region's classified 500 m pixels in the IGBP classes of `key` (MCD12Q1 LC_Type1). One
    frequency histogram per year; the full histogram is kept as the raw artifact. Value stored at YYYY-01 (product date)."""
    geom = _geom(ee, region)
    coll = ee.ImageCollection("MODIS/061/MCD12Q1").select("LC_Type1").filterDate(f"{y0}-01-01", f"{y1 + 1}-01-01")

    def f(img):
        h = img.reduceRegion(ee.Reducer.frequencyHistogram(), geom, 500, maxPixels=int(1e9)).get("LC_Type1")
        return ee.Feature(None, {"t": img.get("system:time_start"), "hist": h})
    out, raw = {}, []
    for ft in coll.map(f).getInfo()["features"]:
        pr = ft["properties"]
        d = datetime.fromtimestamp(pr["t"] / 1000, timezone.utc).date()
        hist = {int(k): float(v) for k, v in (pr.get("hist") or {}).items()}
        tot = sum(hist.values())
        raw.append({"year": d.year, "histogram": hist, "total": tot})
        if tot > 0:
            out[f"{d.year:04d}-01"] = 100 * sum(hist.get(c, 0.0) for c in LANDCOVER_CLASSES[key]) / tot
    return out, raw


def monthly_grace(ee, region, y0, y1):
    """Monthly liquid-water-equivalent anomaly (cm) from the CRI-filtered JPL mascons, regional mean at the 0.5 deg grid.
    Several solutions can fall in one calendar month; their mean is used (month by time_start)."""
    geom = _geom(ee, region)
    coll = ee.ImageCollection("NASA/GRACE/MASS_GRIDS_V04/MASCON_CRI").select("lwe_thickness").filterDate(f"{y0}-01-01", f"{y1 + 1}-01-01")

    def f(img):
        v = img.reduceRegion(ee.Reducer.mean(), geom, 55660, maxPixels=int(1e9)).get("lwe_thickness")
        return ee.Feature(None, {"t": img.get("system:time_start"), "v": v})
    acc, raw = {}, []
    for ft in coll.map(f).getInfo()["features"]:
        pr = ft["properties"]
        d = datetime.fromtimestamp(pr["t"] / 1000, timezone.utc).date()
        raw.append({"date": d.isoformat(), "value": pr.get("v")})
        if pr.get("v") is not None:
            acc.setdefault(f"{d.year:04d}-{d.month:02d}", []).append(float(pr["v"]))
    return {k: float(np.mean(v)) for k, v in sorted(acc.items())}, raw


# ----------------------------------------------------------------- grid + tiling (pure, unit-tested)
DEG_PER_M = 1 / 111319.49
MAX_TILE_BYTES = 30_000_000            # Earth Engine direct-download cap is ~32 MB per request


def grid_for(bbox: dict, scale_m: float) -> dict:
    """A common pixel grid anchored at the region's NW corner. Every variable exported at the same scale shares this
    grid exactly, so rasters are aligned by construction."""
    dx = scale_m * DEG_PER_M
    W = int(np.ceil((bbox["east"] - bbox["west"]) / dx - 1e-9))
    H = int(np.ceil((bbox["north"] - bbox["south"]) / dx - 1e-9))
    return {"dx": dx, "x0": bbox["west"], "y0": bbox["north"], "W": W, "H": H}


def plan_tiles(grid: dict, n_bands: int, max_bytes: int = MAX_TILE_BYTES) -> list[dict]:
    """Split the grid into pixel-aligned tiles whose float32 download stays under the cap."""
    W, H = grid["W"], grid["H"]
    for k in range(1, 200):
        cols = max(1, int(round(np.sqrt(k * W / max(H, 1)))))
        rows = int(np.ceil(k / cols))
        tw, th = int(np.ceil(W / cols)), int(np.ceil(H / rows))
        if tw * th * n_bands * 4 * 1.15 <= max_bytes:
            break
    else:
        raise ValueError("region/scale too large to tile within the download cap")
    tiles = []
    for r in range(rows):
        for c in range(cols):
            c0, c1, r0, r1 = c * tw, min((c + 1) * tw, W), r * th, min((r + 1) * th, H)
            if c1 > c0 and r1 > r0:
                x0 = grid["x0"] + c0 * grid["dx"]; y0 = grid["y0"] - r0 * grid["dx"]
                tiles.append({"c0": c0, "c1": c1, "r0": r0, "r1": r1, "west": x0, "north": y0,
                              "east": grid["x0"] + c1 * grid["dx"], "south": grid["y0"] - r1 * grid["dx"]})
    return tiles


def mosaic_tiles(paths: list, out_path) -> None:
    """Merge GeoTIFF tiles into one raster, preserving band descriptions."""
    import rasterio
    from rasterio.merge import merge
    srcs = [rasterio.open(p) for p in paths]
    try:
        data, transform = merge(srcs, nodata=np.nan)
        desc = list(srcs[0].descriptions)
        profile = srcs[0].profile.copy()
        profile.update(driver="GTiff", height=data.shape[1], width=data.shape[2], transform=transform, count=data.shape[0], dtype="float32", nodata=np.nan, compress="deflate")
        with rasterio.open(out_path, "w", **profile) as dst:
            dst.write(data.astype("float32"))
            for i, d in enumerate(desc, 1):
                if d:
                    dst.set_band_description(i, d)
    finally:
        for s in srcs:
            s.close()


STACK_SCALE = {"ndvi_landsat": 120, "salinity_index": 120}


EXTRACTORS: dict[str, Callable] = {
    "ndvi": monthly_ndvi,
    "ndvi_qa": monthly_ndvi_qa,
    "ndvi_aqua": lambda ee, r, a, b: monthly_modis_vi(ee, r, a, b, "MODIS/061/MYD13Q1", "NDVI"),
    "evi": lambda ee, r, a, b: monthly_modis_vi(ee, r, a, b, "MODIS/061/MOD13Q1", "EVI"),
    "ndvi_nowater": monthly_ndvi_nowater,
    "salinity_index": annual_salinity_index,
    "water_extent_mndwi": monthly_water_mndwi,
    "ndvi_landsat": annual_landsat_ndvi,
    "precip": monthly_precip,
    "lst_day": lambda ee, r, a, b: monthly_lst(ee, r, a, b, night=False),
    "lst_night": lambda ee, r, a, b: monthly_lst(ee, r, a, b, night=True),
    "et": monthly_et,
    "sm_surface": lambda ee, r, a, b: monthly_soil_moisture(ee, r, a, b, root_zone=False),
    "sm_root": lambda ee, r, a, b: monthly_soil_moisture(ee, r, a, b, root_zone=True),
    "water_extent": monthly_water_extent,
    "grace_tws": monthly_grace,
    **{k: (lambda ee, r, a, b, _k=k: annual_landcover_share(ee, r, a, b, _k)) for k in LANDCOVER_CLASSES},
}


# Catalogue coverage limits (first, last calendar year with data). The completeness gate counts only these years, so a
# product that starts after the study period begins (Landsat 8 MNDWI, GRACE) is not rejected for years it cannot have.
COVERAGE_YEARS: dict[str, tuple[int | None, int | None]] = {
    "water_extent_mndwi": (2013, None), "water_extent": (None, 2021), "ndvi_aqua": (2002, None), "grace_tws": (2002, 2024), **{k: (2001, 2024) for k in LANDCOVER_CLASSES},
}


def build_provenance(key: str, region_id: str, y0: int, y1: int) -> dict:
    return {**spec_dict(key), "region": region_id, "processing_period": f"{y0}-{y1}",
            "retrieval_date": datetime.now(timezone.utc).date().isoformat(),
            "geometry": get_region(region_id)["geometry"],
            "processing_config": {"region_bbox": get_region(region_id)["bbox"], "geometry_id": get_region(region_id)["geometry"]["id"], "spatial_reducer": "mean",
                                  "tool": "Google Earth Engine Python API", "quality_filter": spec_dict(key)["quality_filter"]},
            "kind": "observed"}


def run_series_job(key: str, region_id: str, y0: int, y1: int) -> dict:
    """Extract one series from Earth Engine, aggregate, and persist under data/processed."""
    from ..core import store
    if key not in EXTRACTORS:
        raise ValueError(f"No Earth Engine extractor for '{key}' (groundwater is upload-only).")
    ee = get_ee()
    region = get_region(region_id)
    res = EXTRACTORS[key](ee, region, y0, y1)
    months, raw = res if isinstance(res, tuple) else (res, None)
    if not months:
        raise RuntimeError(f"Earth Engine returned no valid observations for {key} {y0}-{y1}.")
    prov = build_provenance(key, region_id, y0, y1)
    from ..core.config import get_settings
    one_per_year = key in ("ndvi_landsat", "salinity_index") or key in LANDCOVER_CLASSES
    c0, c1 = COVERAGE_YEARS.get(key, (None, None))
    ey0, ey1 = max(y0, c0 or y0), min(y1, c1 or y1)          # count only years the product can cover
    expected = max(ey1 - ey0 + 1, 0) * (1 if one_per_year else 12)
    frac = len(months) / max(expected, 1)
    if frac < get_settings().min_completeness:
        raise RuntimeError(f"{key}: only {len(months)} of {expected} expected values ({100 * frac:.0f}%) were obtained, below the "
                           f"{100 * get_settings().min_completeness:.0f}% completeness gate. NOTHING was stored (an incomplete series could mislead).")
    if raw is not None:      # raw observations are kept apart from processed series
        store.save_raw(region_id, key, raw, prov)
    store.save_series("processed", region_id, key, months, prov)
    return {"key": key, "n_months": len(months), "n_raw": None if raw is None else len(raw)}


# ----------------------------------------------------------------- raster stacks (pixel analysis & map layers)
def _annual_image(ee, key: str, geom, year: int, season: str):
    from ..science.timeseries import SEASONS
    months = SEASONS[season]
    s = ee.Date.fromYMD(year, 1, 1)
    if season == "annual":
        start, end = s, s.advance(1, "year")
    else:
        start = ee.Date.fromYMD(year, months[0], 1)
        end = ee.Date.fromYMD(year, months[-1], 1).advance(1, "month")
    if key == "ndvi":
        return ee.ImageCollection("MODIS/061/MOD13Q1").filterDate(start, end).select("NDVI").mean().multiply(P.MODIS_NDVI_SCALE)
    if key in ("lst_day", "lst_night"):
        band, qc = ("LST_Night_1km", "QC_Night") if key == "lst_night" else ("LST_Day_1km", "QC_Day")
        return ee.ImageCollection("MODIS/061/MOD11A2").filterDate(start, end).map(lambda i: _mask_lst(ee, i, band, qc)).mean()
    if key == "et":   # mean daily ET * days in window = window total (mm), via 8-day sums scaled to daily
        c = ee.ImageCollection("MODIS/061/MOD16A2GF").filterDate(start, end).map(lambda i: _mask_et(ee, i))
        days = end.difference(start, "day")
        return c.mean().divide(8).multiply(days)
    if key == "precip":
        c = ee.ImageCollection("NASA/GPM_L3/IMERG_MONTHLY_V07").filterDate(start, end).select("precipitation")
        days = end.difference(start, "day")
        return c.mean().multiply(24).multiply(days).rename("v")
    if key in ("sm_surface", "sm_root"):
        bands = ["RootMoist_inst"] if key == "sm_root" else ["SoilMoi0_10cm_inst"]
        return ee.ImageCollection("NASA/GLDAS/V021/NOAH/G025/T3H").filterDate(start, end).select(bands).mean().reduce(ee.Reducer.sum()).rename("v")
    if key == "ndvi_landsat":
        return _landsat_ndvi_collection(ee, geom, year).median()
    if key == "salinity_index":
        c = _landsat_prepared(ee, geom, f"{year}-03-01", f"{year}-06-01").median()
        return c.expression("sqrt(G * R)", {"G": c.select("G"), "R": c.select("R")}).rename("v")
    raise ValueError(f"No raster stack definition for '{key}'")


def run_stack_job(key: str, region_id: str, y0: int, y1: int, season: str) -> dict:
    """Export a (years x pixels) GeoTIFF stack of seasonal means (ET/precip: totals) on a shared, region-anchored grid.
    Large requests are split into pixel-aligned tiles under the ~32 MB download cap and mosaicked, so one variable is
    never silently truncated. Nothing is written unless every tile downloaded."""
    import tempfile
    import requests
    from pathlib import Path
    from ..core import store
    ee = get_ee()
    region = get_region(region_id)
    geom = _geom(ee, region)
    scale = STACK_SCALE.get(key, CATALOG[key].scale_m)
    static = key == "water_occurrence"
    years = [0] if static else list(range(y0, y1 + 1))
    grid = grid_for(region["bbox"], scale)
    tiles = plan_tiles(grid, len(years))
    if static:
        img = ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence").unmask(0).rename("occurrence").toFloat()
        names = ["occurrence"]
    else:
        imgs = []
        for y in years:
            check_cancel()
            imgs.append(_annual_image(ee, key, geom, y, season).select([0]).rename(f"y{y}"))
        img = ee.Image.cat(imgs).toFloat()
        names = [f"y{y}" for y in years]
    img = img.clip(geom)
    out = store.raster_path("processed", region_id, key, season)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out.parent) as td:
        paths = []
        for i, t in enumerate(tiles):
            check_cancel()
            url = img.getDownloadURL({"region": ee.Geometry.Rectangle([t["west"], t["south"], t["east"], t["north"]], "EPSG:4326", False),
                                       "crs": "EPSG:4326", "crs_transform": [grid["dx"], 0, t["west"], 0, -grid["dx"], t["north"]], "format": "GEO_TIFF"})
            resp = requests.get(url, timeout=900)
            resp.raise_for_status()
            p = Path(td) / f"tile{i}.tif"
            p.write_bytes(resp.content)
            paths.append(p)
        tmp = out.with_suffix(".tmp")
        if len(paths) == 1:
            tmp.write_bytes(paths[0].read_bytes())
        else:
            mosaic_tiles(paths, tmp)
        import rasterio
        with rasterio.open(tmp, "r+") as ds:
            for i, nm in enumerate(names, 1):
                ds.set_band_description(i, nm)
            ds.update_tags(provenance=str(build_provenance(key, region_id, y0, y1)), season=season, kind="observed", scale_m=str(scale),
                           geometry_id=region["geometry"]["id"], grid=json.dumps({k: grid[k] for k in ("dx", "x0", "y0", "W", "H")}))
        tmp.replace(out)            # atomic commit
    return {"key": key, "season": season, "bands": len(names), "tiles": len(tiles), "scale_m": scale, "shape": [grid["H"], grid["W"]]}


STATIC_IMAGES = {"JRC/GSW1_4/GlobalSurfaceWater"}

EXPECTED_BANDS = {
    "MODIS/061/MOD13Q1": ["NDVI", "EVI", "SummaryQA"], "MODIS/061/MYD13Q1": ["NDVI", "EVI"], "NASA/GPM_L3/IMERG_MONTHLY_V07": ["precipitation"],
    "MODIS/061/MOD11A2": ["LST_Day_1km", "LST_Night_1km", "QC_Day", "QC_Night"], "MODIS/061/MOD16A2GF": ["ET", "ET_QC"],
    "NASA/GLDAS/V021/NOAH/G025/T3H": ["RootMoist_inst", "SoilMoi0_10cm_inst"], "JRC/GSW1_4/MonthlyHistory": ["water"], "JRC/GSW1_4/GlobalSurfaceWater": ["occurrence"],
    "MODIS/061/MCD12Q1": ["LC_Type1"], "NASA/GRACE/MASS_GRIDS_V04/MASCON_CRI": ["lwe_thickness"],
}


def verify_dataset_bands() -> dict:
    """Live check that every collection exists and exposes the bands we read (names only; units and scales are
    recorded in docs/DATASET_VERIFICATION.md from the official catalogue)."""
    ee = get_ee()
    report = {}
    for cid, bands in EXPECTED_BANDS.items():
        try:
            # static single-image assets (e.g. the JRC occurrence layer) are Images, not collections
            obj = ee.Image(cid) if cid in STATIC_IMAGES else ee.ImageCollection(cid).first()
            names = obj.bandNames().getInfo()
            report[cid] = {"ok": all(b in names for b in bands), "missing": [b for b in bands if b not in names], "n_bands": len(names)}
        except Exception as e:
            report[cid] = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    return report
