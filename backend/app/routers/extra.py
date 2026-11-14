"""Phase 1/3/4 endpoints: groundwater wells, salinity, Prosopis-investigation indicator + ground truth, difference maps,
map export, resolution agreement, multi-variable comparison, region comparison."""
from __future__ import annotations
import io
import tempfile
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile

from .. import services as svc
from ..core import fielddata, groundwater as GW, store
from ..core.catalog import CATALOG
from ..core.regions import get_region, list_regions
from ..core.security import require_write, safe_text
from ..science import multivar as MV
from ..science import pixel as PX
from ..science import raster_qc as RQ
from ..science import stats as S
from ..science import validation as VA
from .analysis import LAYER_META, _pixel, _stack
from .core_routes import read_limited
from .variables import make_router, water

Source = Literal["processed", "sample"]
Season = Literal["annual", "monsoon", "summer", "postmonsoon", "winter", "peak"]

salinity = make_router("salinity", "salinity", "salinity_index")
spatial2 = APIRouter(prefix="/api/spatial", tags=["spatial"])
stats2 = APIRouter(prefix="/api/statistics", tags=["statistics"])


# ------------------------------------------------------------------ groundwater
@water.get("/groundwater/wells")
def groundwater_wells(region: str = "banni", source: Source = "processed"):
    """Per-well series, the validation report from upload, and per-well trend tests (BH-FDR across wells)."""
    svc.check(region)
    w = GW.load_wells(source, region)
    if not w:
        raise svc.AppError("no_data", "No measured groundwater uploaded. Upload CGWB / India-WRIS well readings (CSV: date,value[,well_id]) in Water Resources.", 404)
    return {"result": {"wells": w["wells"], "validation": w["validation"], "unit": w["unit"], "trends": GW.per_well_trends(w),
                       "note": "Depth to water: an INCREASING trend means the water table is getting deeper. Only measured levels can support a groundwater claim."},
            "meta": {"region": region, "kind": "user-supplied", "synthetic": False, "source_note": w.get("source_note"), "uploaded": w.get("uploaded")}}


# ------------------------------------------------------------------ salinity: field-EC validation of the spectral proxy
@salinity.post("/field-ec", dependencies=[Depends(require_write)])
async def upload_field_ec(region: str = Form(...), source: Source = Form("processed"), file: UploadFile = File(...)):
    """CSV: lat, lon, ec (dS/m) [, year]. Stored for validating the salinity proxy; does not by itself validate anything."""
    svc.check(region)
    raw = await read_limited(file)
    try:
        df = pd.read_csv(io.BytesIO(raw))
        df.columns = [c.strip().lower() for c in df.columns]
        for c in ("lat", "lon", "ec"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
    except Exception as e:
        raise svc.AppError("bad_csv", f"Need columns lat, lon, ec: {e}", 422)
    if len(df) > 20000:
        raise svc.AppError("bad_csv", "too many rows (max 20000)", 422)
    n0 = len(df)
    ok = df["lat"].between(-90, 90) & df["lon"].between(-180, 180) & df["ec"].between(0, 500)
    df = df[ok].drop_duplicates(["lat", "lon"])
    if len(df) < 3:
        raise svc.AppError("bad_csv", "fewer than 3 valid rows (EC must be 0-500 dS/m, lat/lon valid)", 422)
    fielddata.save(source, region, "field_ec", {"points": df.to_dict("records"), "unit": "dS/m", "filename": safe_text(file.filename or "", 80)})
    return {"rows_in": int(n0), "rows_valid": int(len(df)), "rejected": int(n0 - ok.sum()), "needed_for_validation": VA.MIN_PER_CLASS}


def _sample_points(info: dict, lats, lons, year_idx=None) -> np.ndarray:
    vals = []
    for la, lo in zip(lats, lons):
        v = [PX.sample_value(info, i, float(lo), float(la)) for i in range(info["data"].shape[0])]
        v = [x for x in v if x is not None]
        vals.append(float(np.mean(v)) if v else np.nan)
    return np.array(vals)


@salinity.get("/validation")
def salinity_validation(region: str = "banni", source: Source = "processed", season: Season = "summer"):
    """Spearman correlation between the Landsat SI1 proxy (mean over years at each point) and measured EC."""
    svc.check(region)
    ec = fielddata.load(source, region, "field_ec")
    if not ec:
        return {"result": {"status": "no_field_data", "message": "No field EC measurements uploaded. The salinity index is UNVALIDATED; no salinity claim can be made from it.",
                           "proxy": CATALOG["salinity_index"].variable}, "meta": {"region": region, "synthetic": False}}
    info = _stack(source, region, "salinity_index", season)
    pts = pd.DataFrame(ec["points"])
    idx = _sample_points(info, pts["lat"].values, pts["lon"].values)
    res = VA.ec_validation(idx, pts["ec"].values.astype(float))
    return {"result": {**res, "proxy": CATALOG["salinity_index"].variable, "n_uploaded": int(len(pts)), "limitations": CATALOG["salinity_index"].limitations},
            "meta": {"region": region, "synthetic": info["tags"].get("kind") == "synthetic"}}


# ------------------------------------------------------------------ Prosopis investigation: indicator + ground truth
@spatial2.post("/ground-truth", dependencies=[Depends(require_write)])
async def upload_ground_truth(region: str = Form(...), source: Source = Form("processed"), file: UploadFile = File(...)):
    """CSV: lat, lon, class (e.g. prosopis / grass / bare). Validated and stored. NO labels ship with the project."""
    svc.check(region)
    raw = await read_limited(file)
    try:
        df, rep = VA.parse_labels_csv(raw)
    except VA.ValidationError as e:
        raise svc.AppError("bad_csv", str(e), 422)
    fielddata.save(source, region, "ground_truth", {"points": df.to_dict("records"), "validation": rep, "filename": safe_text(file.filename or "", 80)})
    return rep


@spatial2.get("/ground-truth/status")
def ground_truth_status(region: str = "banni", source: Source = "processed"):
    svc.check(region)
    gt = fielddata.load(source, region, "ground_truth")
    if not gt:
        return {"available": False, "message": "No ground-truth labels exist for this project. Species-level classification (Prosopis juliflora vs native grassland) is therefore NOT possible and is not attempted; "
                                              "the dry-season persistence indicator is exploratory and unvalidated.",
                "required": "Georeferenced field points labelled by class, at least 10 per class, from an independent (ideally stratified random) survey, ideally by a botanist or from verified high-resolution imagery."}
    return {"available": True, **gt["validation"], "uploaded": gt["uploaded"]}


def _evergreen(region, source, start, end, mask, thr):
    dry, wet = _stack(source, region, "ndvi", "summer"), _stack(source, region, "ndvi", "monsoon")
    yd, yw = PX.band_years(dry["descriptions"], dry["data"].shape[0]), PX.band_years(wet["descriptions"], wet["data"].shape[0])
    common = [y for y in yd if y in yw and y >= (start or -1e9) and y <= (end or 1e9)]
    if len(common) < PX.MIN_VALID:
        raise svc.AppError("insufficient_data", f"Only {len(common)} common years between summer and monsoon NDVI stacks.", 422)
    d = dry["data"][[list(yd).index(y) for y in common]]; w = wet["data"][[list(yw).index(y) for y in common]]
    ev = RQ.evergreen_index(d, w)
    rep = None
    if mask == "rann_water":
        mp = store.raster_path(source, region, "water_occurrence", "static")
        if not mp.exists():
            raise svc.AppError("no_data", "Rann-water masking needs the water_occurrence/static raster.", 404)
        occ_info = _stack(source, region, "water_occurrence", "static")
        occ = occ_info["data"][0] if RQ.grids_aligned(dry, occ_info) else RQ.align_to(occ_info, dry)[0]
        ev, rep = RQ.apply_water_mask(ev, occ, thr)
    return ev, np.array(common, float), dry, rep


@spatial2.get("/evergreen")
def evergreen_summary(region: str = "banni", source: Source = "processed", start: int | None = None, end: int | None = None,
                      mask: Literal["none", "rann_water"] = "none", water_thr: float = Query(10.0, ge=1, le=100), q: float = Query(0.05, gt=0, lt=0.5)):
    """EXPLORATORY dry-season persistence indicator (summer NDVI / monsoon NDVI) and its pixel trend (BH-FDR)."""
    svc.check(region)
    ev, yrs, info, rep = _evergreen(region, source, start, end, mask, water_thr)
    res = PX.pixel_trends(ev, yrs, q)
    mean = np.nanmean(ev, axis=0)
    return {"result": {**PX.summarise(res, q), "years": [int(yrs.min()), int(yrs.max())], "mean_index": float(np.nanmean(mean)), "p10": float(np.nanpercentile(mean, 10)),
                       "p90": float(np.nanpercentile(mean, 90)), "mask": rep, "bounds": {"south": info["bounds"].bottom, "west": info["bounds"].left, "north": info["bounds"].top, "east": info["bounds"].right},
                       "status": "EXPLORATORY - hypothesis generating, not validated, not a species classification",
                       "interpretation": ("Higher values mean vegetation stays greener in the dry season relative to the monsoon. Deep-rooted evergreen shrubs such as Prosopis can show this, "
                                          "but so can groundwater-fed or irrigated vegetation, salt-tolerant shrubs and mixed pixels. Without field labels the index cannot tell them apart."),
                       "ground_truth": ground_truth_status(region, source)},
            "meta": {"region": region, "synthetic": info["tags"].get("kind") == "synthetic", "kind": info["tags"].get("kind", "observed")}}


@spatial2.get("/evergreen.png")
def evergreen_png(region: str = "banni", source: Source = "processed", product: Literal["mean", "trend"] = "mean", start: int | None = None, end: int | None = None,
                  mask: Literal["none", "rann_water"] = "none", water_thr: float = Query(10.0, ge=1, le=100), q: float = Query(0.05, gt=0, lt=0.5)):
    svc.check(region)
    ev, yrs, _, _ = _evergreen(region, source, start, end, mask, water_thr)
    if product == "trend":
        png = PX.render_class_png(PX.pixel_trends(ev, yrs, q)["cls"])
    else:
        png = PX.render_scalar_png(np.nanmean(ev, axis=0), 0.0, 1.0, "YlGnBu")
    return Response(png, media_type="image/png", headers={"Cache-Control": "no-store"})


@spatial2.get("/indicator-validation")
def indicator_validation(region: str = "banni", source: Source = "processed"):
    """Separability of the evergreen indicator between labelled classes. Refuses without labels."""
    svc.check(region)
    gt = fielddata.load(source, region, "ground_truth")
    if not gt:
        raise svc.AppError("no_ground_truth", "No ground-truth labels uploaded, so the indicator cannot be validated and no Prosopis/grassland claim can be made.", 404)
    ev, yrs, info, _ = _evergreen(region, source, None, None, "none", 10.0)
    mean = np.nanmean(ev, axis=0)
    pts = pd.DataFrame(gt["points"])
    fake = {"data": mean[None], "transform": info["transform"], "height": info["height"], "width": info["width"]}
    vals = np.array([PX.sample_value(fake, 0, float(lo), float(la)) or np.nan for la, lo in zip(pts["lat"], pts["lon"])], float)
    out = VA.indicator_separability(vals, pts["class"].astype(str).values)
    return {"result": {**out, "labels": gt["validation"]}, "meta": {"region": region, "synthetic": info["tags"].get("kind") == "synthetic"}}


# ------------------------------------------------------------------ difference maps, export, agreement, QC
def _period_arrays(region, source, variable, season, a0, a1, b0, b1, mask, thr):
    info = _stack(source, region, variable, season)
    yrs = PX.band_years(info["descriptions"], info["data"].shape[0])
    data = info["data"]
    if mask == "rann_water":
        mp = store.raster_path(source, region, "water_occurrence", "static")
        if not mp.exists():
            raise svc.AppError("no_data", "Rann-water masking needs the water_occurrence/static raster.", 404)
        occ_info = _stack(source, region, "water_occurrence", "static")
        occ = occ_info["data"][0] if RQ.grids_aligned(info, occ_info) else RQ.align_to(occ_info, info)[0]
        data, _ = RQ.apply_water_mask(data, occ, thr)
    try:
        return RQ.period_mean(data, yrs, a0, a1), RQ.period_mean(data, yrs, b0, b1), info
    except RQ.RasterError as e:
        raise svc.AppError("bad_period", str(e), 422)


@spatial2.get("/difference")
def difference(region: str = "banni", source: Source = "processed", variable: str = "ndvi", season: Season = "annual",
               a_start: int = 2001, a_end: int = 2005, b_start: int = 2020, b_end: int = 2024,
               mask: Literal["none", "rann_water"] = "none", water_thr: float = Query(10.0, ge=1, le=100)):
    """Change map: mean(B period) - mean(A period). Descriptive; no significance is implied (see pixel-trend for tests)."""
    svc.check(region, variable)
    a, b, info = _period_arrays(region, source, variable, season, a_start, a_end, b_start, b_end, mask, water_thr)
    try:
        d = RQ.difference_summary(a, b)
    except RQ.RasterError as e:
        raise svc.AppError("no_data", str(e), 422)
    return {"result": {**d, "periods": {"a": [a_start, a_end], "b": [b_start, b_end]}, "unit": LAYER_META.get(variable, ("", "", ""))[1],
                       "bounds": {"south": info["bounds"].bottom, "west": info["bounds"].left, "north": info["bounds"].top, "east": info["bounds"].right},
                       "note": "Difference of period means. Descriptive only: not a significance test, and sensitive to the chosen periods and to rainfall differences between them."},
            "meta": {"region": region, "variable": variable, "season": season, "synthetic": info["tags"].get("kind") == "synthetic", "kind": info["tags"].get("kind", "observed")}}


@spatial2.get("/difference.png")
def difference_png(region: str = "banni", source: Source = "processed", variable: str = "ndvi", season: Season = "annual",
                   a_start: int = 2001, a_end: int = 2005, b_start: int = 2020, b_end: int = 2024,
                   mask: Literal["none", "rann_water"] = "none", water_thr: float = Query(10.0, ge=1, le=100)):
    svc.check(region, variable)
    a, b, _ = _period_arrays(region, source, variable, season, a_start, a_end, b_start, b_end, mask, water_thr)
    d = b - a
    m = float(np.nanpercentile(np.abs(d), 98)) or 1.0
    return Response(PX.render_scalar_png(d, -m, m, "RdBu"), media_type="image/png", headers={"Cache-Control": "no-store"})


@spatial2.get("/layer.tif")
def layer_tif(region: str = "banni", source: Source = "processed", variable: str = "ndvi", season: Season = "annual", year: int | None = None):
    """One year (or the all-year mean) of a layer as a GeoTIFF on the stack grid (EPSG:4326, NaN = no data)."""
    svc.check(region, variable)
    info = _stack(source, region, variable, season)
    yrs = PX.band_years(info["descriptions"], info["data"].shape[0])
    if year is None:
        arr, name = np.nanmean(info["data"], axis=0), "mean"
    else:
        idx = np.where(yrs == year)[0]
        if not len(idx):
            raise svc.AppError("bad_year", f"Year {year} not in stack.", 422)
        arr, name = info["data"][idx[0]], f"y{year}"
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "l.tif"
        PX.write_geotiff(p, {f"{variable}_{season}_{name}": arr}, info["transform"], info["crs"],
                         {"variable": variable, "season": season, "kind": info["tags"].get("kind", "observed"), "geometry_id": get_region(region)["geometry"]["id"]})
        data = p.read_bytes()
    return Response(data, media_type="image/tiff", headers={"Content-Disposition": f'attachment; filename="{region}_{variable}_{season}_{name}.tif"'})


def figure_png(arr, bounds, title, cmap, vmin, vmax, unit, footer, synthetic=False, classes=False) -> bytes:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap
    fig, ax = plt.subplots(figsize=(7.2, 5.6))
    ext = [bounds["west"], bounds["east"], bounds["south"], bounds["north"]]
    if classes:
        cm = ListedColormap(["#d95f02", "#bdbdbd", "#1b9e77"])
        im = ax.imshow(np.where(np.isfinite(arr), arr, np.nan), extent=ext, cmap=cm, vmin=-1, vmax=1, interpolation="nearest")
        cb = fig.colorbar(im, ax=ax, ticks=[-1, 0, 1], shrink=0.8); cb.ax.set_yticklabels(["decrease", "n.s.", "increase"])
    else:
        im = ax.imshow(arr, extent=ext, cmap=cmap, vmin=vmin, vmax=vmax, interpolation="nearest")
        fig.colorbar(im, ax=ax, shrink=0.8, label=unit)
    ax.set_xlabel("Longitude (°E, EPSG:4326)"); ax.set_ylabel("Latitude (°N)"); ax.set_title(title, fontsize=10); ax.grid(alpha=0.3)
    fig.text(0.01, 0.01, footer, fontsize=6.5, color="#444")
    if synthetic:
        fig.text(0.5, 0.5, "SYNTHETIC SAMPLE DATA", fontsize=26, color="red", alpha=0.25, ha="center", va="center", rotation=25)
    buf = io.BytesIO(); fig.savefig(buf, format="png", dpi=150, bbox_inches="tight"); plt.close(fig)
    return buf.getvalue()


@spatial2.get("/export.png")
def export_map(region: str = "banni", source: Source = "processed", variable: str = "ndvi", season: Season = "annual",
               kind: Literal["layer", "trend", "difference"] = "layer", year: int | None = None, start: int | None = None, end: int | None = None,
               a_start: int = 2001, a_end: int = 2005, b_start: int = 2020, b_end: int = 2024, q: float = Query(0.05, gt=0, lt=0.5),
               mask: Literal["none", "rann_water"] = "none", water_thr: float = Query(10.0, ge=1, le=100)):
    """Publication-style map image with axes, legend, units, CRS, data kind and provenance footer."""
    svc.check(region, variable)
    info = _stack(source, region, variable, season)
    label, unit, cmap = LAYER_META.get(variable, (variable, "", "viridis"))
    b = {"south": info["bounds"].bottom, "west": info["bounds"].left, "north": info["bounds"].top, "east": info["bounds"].right}
    syn = info["tags"].get("kind") == "synthetic"
    reg = get_region(region)
    foot = f"{reg['name']} | geometry: {reg['geometry']['id']} | {label} ({season}) | source: {source} | CRS EPSG:4326 | generated by GlobalClimateLens"
    if kind == "trend":
        res, _, yrs, rep = _pixel(region, source, variable, season, start, end, q, mask, water_thr)
        png = figure_png(res["cls"], b, f"{label}: significant pixel trends {int(yrs.min())}-{int(yrs.max())} (BH-FDR q={q})", None, -1, 1, "", foot, syn, True)
    elif kind == "difference":
        a, bb, _ = _period_arrays(region, source, variable, season, a_start, a_end, b_start, b_end, mask, water_thr)
        d = bb - a; m = float(np.nanpercentile(np.abs(d), 98)) or 1.0
        png = figure_png(d, b, f"{label}: mean {b_start}-{b_end} minus {a_start}-{a_end}", "RdBu", -m, m, unit, foot, syn)
    else:
        yrs = PX.band_years(info["descriptions"], info["data"].shape[0])
        if year is None:
            arr, t = np.nanmean(info["data"], axis=0), f"{label}: all-year mean ({season})"
        else:
            idx = np.where(yrs == year)[0]
            if not len(idx):
                raise svc.AppError("bad_year", f"Year {year} not in stack.", 422)
            arr, t = info["data"][idx[0]], f"{label} ({season}) {year}"
        allv = info["data"][np.isfinite(info["data"])]
        png = figure_png(arr, b, t, cmap, float(np.percentile(allv, 2)), float(np.percentile(allv, 98)), unit, foot, syn)
    return Response(png, media_type="image/png", headers={"Content-Disposition": f'attachment; filename="{region}_{variable}_{season}_{kind}.png"'})


@spatial2.get("/trend-agreement")
def trend_agreement(region: str = "banni", source: Source = "processed", coarse: str = "ndvi", coarse_season: Season = "peak",
                    fine: str = "ndvi_landsat", fine_season: Season = "peak", q: float = Query(0.05, gt=0, lt=0.5)):
    """Do greening patterns seen by the coarse sensor (MODIS) also appear in the fine one (Landsat)? Fine slopes/classes are
    averaged onto the coarse grid; compared over the common years."""
    svc.check(region, coarse); svc.check(region, fine)
    ci, fi = _stack(source, region, coarse, coarse_season), _stack(source, region, fine, fine_season)
    yc, yf = PX.band_years(ci["descriptions"], ci["data"].shape[0]), PX.band_years(fi["descriptions"], fi["data"].shape[0])
    common = sorted(set(yc) & set(yf))
    if len(common) < PX.MIN_VALID:
        raise svc.AppError("insufficient_data", f"Only {len(common)} common years.", 422)
    c = PX.pixel_trends(ci["data"][[list(yc).index(y) for y in common]], np.array(common, float), q)
    f = PX.pixel_trends(fi["data"][[list(yf).index(y) for y in common]], np.array(common, float), q)
    on_c = {k: RQ.align_to({"data": f[k][None], "transform": fi["transform"], "crs": fi["crs"]}, ci, "average")[0] for k in ("slope", "cls")}
    try:
        ag = RQ.trend_agreement({"slope": c["slope"], "cls": c["cls"]}, on_c)
    except RQ.RasterError as e:
        raise svc.AppError("insufficient_data", str(e), 422)
    return {"result": {**ag, "common_years": [int(common[0]), int(common[-1])], "n_years": len(common), "coarse": f"{coarse}/{coarse_season}", "fine": f"{fine}/{fine_season}",
                       "fine_pixel_size_m": fi["qc"]["pixel_size_m_approx"],
                       "coarse_pixel_size_m": ci["qc"]["pixel_size_m_approx"]},
            "meta": {"region": region, "synthetic": fi["tags"].get("kind") == "synthetic"}}


@spatial2.get("/qc")
def raster_qc(region: str = "banni", source: Source = "processed", variable: str = "ndvi", season: Season = "annual"):
    svc.check(region, variable)
    info = _stack(source, region, variable, season)
    return {"result": info["qc"], "meta": {"region": region, "variable": variable, "season": season}}


# ------------------------------------------------------------------ statistics: multi-variable + regional comparison
@stats2.get("/compare")
def compare(region: str = "banni", source: Source = "processed", variables: str = "ndvi,precip,lst_day,et", agg: Season = "monsoon",
            response: str | None = "ndvi", detrend: bool = False, start: int | None = None, end: int | None = None, alpha: float = Query(0.05, gt=0, lt=0.5)):
    """Integrated comparison of 2-6 variables on aggregated years: correlation matrices (BH-adjusted), partial correlations,
    regression with VIF, leave-one-out prediction skill, lagged correlations and coincident anomalies."""
    keys = [k.strip() for k in variables.split(",") if k.strip()]
    if not 2 <= len(keys) <= 6 or len(set(keys)) != len(keys):
        raise svc.AppError("bad_request", "Choose 2-6 distinct variables.", 422)
    svc.check(region)
    cols, meta = {}, {}
    for k in keys:
        svc.check(region, k)
        cols[k], rec = svc.annual(region, k, source, agg, start, end)
        meta[k] = svc.meta_of(rec)
    df = pd.concat(cols, axis=1)
    if response and response not in keys:
        response = None
    try:
        res = MV.compare(df, response, detrend, alpha)
    except ValueError as e:
        raise svc.AppError("insufficient_data", str(e), 422)
    return {"result": {**res, "labels": {k: CATALOG[k].label for k in keys}, "units": {k: CATALOG[k].unit for k in keys}, "aggregation": agg,
                       "statement": "ASSOCIATION (matrices, partial correlations), PREDICTION (leave-one-out R2) and CAUSATION (not assessed) are reported separately."},
            "meta": {"region": region, "synthetic": any(m["synthetic"] for m in meta.values()), "kind": "observed" if not any(m["synthetic"] for m in meta.values()) else "synthetic",
                     "datasets": {k: m["dataset"] for k, m in meta.items()}}}


@stats2.get("/region-comparison")
def region_comparison(regions: str = "banni,banni_grassland", variable: str = "ndvi", agg: Season = "monsoon", source: Source = "processed"):
    """Trend of the same variable over different geometries (e.g. handover rectangle vs grassland polygon)."""
    out = []
    for rid in [r.strip() for r in regions.split(",") if r.strip()][:5]:
        try:
            reg = get_region(rid)
        except KeyError:
            out.append({"region": rid, "status": "unknown region"}); continue
        try:
            t = svc.trend_payload(rid, variable, source, agg, None, None, 0.05)["result"]
            p = t[t["recommended"]]
            out.append({"region": rid, "name": reg["name"], "geometry": reg["geometry"], "status": "ok", "direction": p["direction"], "p": p["p"],
                        "slope": p["slope"], "ci_low": p["slope_ci_low"], "ci_high": p["slope_ci_high"], "test": p["test"], "n": p["n"],
                        "mean": float(np.mean(t["values"]))})
        except svc.AppError as e:
            out.append({"region": rid, "name": reg["name"], "geometry": reg["geometry"], "status": e.code, "message": e.message})
    pending = [r for r in list_regions() if r.get("pending_geometry")]
    return {"result": {"variable": variable, "aggregation": agg, "items": out,
                       "pending_geometries": [{"region": r["id"], "needed": r["pending_geometry"]["needed"]} for r in pending],
                       "note": "Different geometries answer different questions. The handover rectangle includes non-grassland land (e.g. Rann salt flats)."},
            "meta": {"synthetic": False}}
