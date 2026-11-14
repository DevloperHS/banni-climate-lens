"""statistics and spatial routers."""
from __future__ import annotations
from typing import Literal
import numpy as np
import pandas as pd
from fastapi import APIRouter, Query, Response
from pydantic import BaseModel, Field

from .. import services as svc
from ..core import store
from ..core.catalog import CATALOG
from ..core.regions import get_region
from ..science import pixel as PX
from ..science import raster_qc as RQ
from ..science import stats as S
from ..science import timeseries as TS
from .variables import _mt, water

Source = Literal["processed", "sample"]
Season = Literal["annual", "monsoon", "summer", "postmonsoon", "winter", "peak"]

statistics = APIRouter(prefix="/api/statistics", tags=["statistics"])
spatial = APIRouter(prefix="/api/spatial", tags=["spatial"])


# ------------------------------------------------------------------ statistics
class TrendRequest(BaseModel):
    values: list[float | None] = Field(min_length=4, max_length=5000)
    times: list[float] | None = None
    alpha: float = Field(0.05, gt=0, lt=0.5)


@statistics.post("/trend")
def trend_arbitrary(req: TrendRequest):
    """Run Mann-Kendall / Hamed-Rao / Sen on user-supplied values (no stored data needed)."""
    vals = np.array([np.nan if v is None else v for v in req.values], float)
    if req.times is not None and len(req.times) != len(vals):
        raise svc.AppError("bad_request", "times and values must have the same length", 422)
    try:
        rep = S.trend_report(vals, req.times, req.alpha)
    except ValueError as e:
        raise svc.AppError("insufficient_data", str(e), 422)
    return {"result": rep, "meta": {"method": "Mann-Kendall, Hamed-Rao, Sen slope", "alpha": req.alpha, "user_supplied": True}}


@statistics.get("/rainfall-adjusted")
def rainfall_adjusted(region: str = "banni", source: Source = "processed", response: str = "ndvi", season: Season = "monsoon",
                      start: int | None = Query(None, ge=1980), end: int | None = Query(None, le=2100),
                      alpha: float = Query(0.05, gt=0, lt=0.5), rain_season: Literal["annual", "monsoon", "summer", "postmonsoon", "winter", "peak", "prev_monsoon"] = "monsoon"):
    svc.check(region, response)
    return svc.cached(("adj", region, source, response, season, rain_season, start, end, alpha, _mt(source, region, response), _mt(source, region, "precip")),
                      lambda: svc.rainfall_adjusted_payload(region, source, response, season, start, end, alpha, rain_season))


@statistics.get("/handover-reproduction")
def handover_reproduction(region: str = "banni", source: Source = "processed", start: int | None = None, end: int | None = None):
    """Run the handover's exact protocol on the stored data and compare with the numbers it reports."""
    svc.check(region)
    return svc.handover_payload(region, source, start, end)


@statistics.get("/sensor-index-checks")
def sensor_index_checks(region: str = "banni", source: Source = "processed", start: int | None = None, end: int | None = None,
                        alpha: float = Query(0.05, gt=0, lt=0.5)):
    """Research brief s.7: repeat the NDVI trend and rain-removed tests with Aqua (MYD13Q1) NDVI and with EVI, over
    the years all series share, and say whether each agrees with Terra NDVI."""
    return svc.sensor_index_checks_payload(region, source, start, end, alpha)


@statistics.get("/regression")
def regression(region: str = "banni", source: Source = "processed", y: str = "ndvi", x: str = "precip",
               agg: Season = "monsoon", start: int | None = None, end: int | None = None,
               alpha: float = Query(0.05, gt=0, lt=0.5)):
    """OLS y ~ x1 [+ x2 ...] on aggregated years. `x` may be comma-separated (max 3)."""
    xs = [k.strip() for k in x.split(",") if k.strip()]
    if not 1 <= len(xs) <= 3:
        raise svc.AppError("bad_request", "Provide 1-3 predictors", 422)
    svc.check(region, y)
    series, recs = {}, {}
    for k in [y] + xs:
        svc.check(region, k)
        series[k], recs[k] = svc.annual(region, k, source, agg, start, end)
    df = pd.concat(series, axis=1).dropna()
    if len(df) < len(xs) + 5:
        raise svc.AppError("insufficient_data", f"Only {len(df)} complete years for {len(xs)} predictor(s).", 422)
    fit = S.ols(df[y].values, {k: df[k].values for k in xs}, alpha)
    resid = np.array(fit["residuals"])
    return {"result": {**fit, "y": y, "x": xs, "years": [int(i) for i in df.index], "observed": df[y].tolist(),
                       "residual_trend": S.trend_report(resid, df.index.values.astype(float), alpha),
                       "units": {k: CATALOG[k].unit for k in [y] + xs},
                       "interpretation": ("Regression and correlation describe association. They do not show that the predictor causes the response; "
                                          "shared trends, lags and omitted variables can produce the same coefficients.")},
            "meta": svc.meta_of(recs[y], aggregation=agg, predictors={k: svc.meta_of(recs[k])["dataset"] for k in xs}, method="OLS with HAC robustness")}


@statistics.get("/correlation")
def correlation(region: str = "banni", source: Source = "processed", a: str = "ndvi", b: str = "precip",
                agg: Season = "monsoon", start: int | None = None, end: int | None = None, detrend: bool = False):
    """Pearson / Spearman correlation between two aggregated variables. detrend=true first removes
    each series' linear time trend so shared trends do not masquerade as co-variability."""
    sa, ra = svc.annual(region, a, source, agg, start, end)
    sb, rb = svc.annual(region, b, source, agg, start, end)
    df = pd.concat([sa.rename("a"), sb.rename("b")], axis=1).dropna()
    if len(df) < 5:
        raise svc.AppError("insufficient_data", f"Only {len(df)} overlapping years.", 422)
    va, vb = df["a"].values, df["b"].values
    if detrend:
        t = df.index.values.astype(float)
        va = va - np.polyval(np.polyfit(t, va, 1), t); vb = vb - np.polyval(np.polyfit(t, vb, 1), t)
    res = S.correlation(va, vb)
    return {"result": {**res, "years": [int(i) for i in df.index], "a": df["a"].tolist(), "b": df["b"].tolist(), "detrended": detrend,
                       "labels": {"a": CATALOG[a].label, "b": CATALOG[b].label}},
            "meta": svc.meta_of(ra, aggregation=agg, other=svc.meta_of(rb)["dataset"])}


@statistics.get("/event")
def event(region: str = "banni", source: Source = "processed", variable: str = "ndvi", event_id: str = "biparjoy",
          pre_months: int = Query(3, ge=1, le=6), post_months: int = Query(3, ge=1, le=6), adjust_rain: bool = False):
    """Pre/post-event comparison against a same-season placebo distribution from other years."""
    r = svc.check(region, variable)
    ev = next((e for e in r.get("events", []) if e["id"] == event_id), None)
    if not ev:
        raise svc.AppError("unknown_event", f"No event '{event_id}' configured for {region}", 404)
    s, rec = svc.monthly(region, variable, source)
    adjusted = None
    try:
        res = S.event_study(s, pd.Timestamp(ev["date"]), pre_months, post_months)
        if adjust_rain and variable != "precip":
            rain, _ = svc.monthly(region, "precip", source)
            adjusted = S.event_study_rain_adjusted(s, rain, pd.Timestamp(ev["date"]), pre_months, post_months)
    except ValueError as e:
        raise svc.AppError("insufficient_data", str(e), 422)
    return {"result": {**res, "rain_adjusted": adjusted, "event": ev, "unit": CATALOG[variable].unit,
                       "series": {"x": [d.strftime("%Y-%m") for d in s.index], "values": TS.from_series(s)[1]}},
            "meta": svc.meta_of(rec, method="Placebo-year event study on deseasonalised monthly anomalies")}


# ------------------------------------------------------------------ water investigations status
@water.get("/investigations")
def investigations(region: str = "banni", source: Source = "processed"):
    svc.check(region)
    have = set(store.list_series(source, region))
    return {"items": [
        {"id": "surface_water", "title": "Surface-water extent", "dataset": "JRC/GSW1_4/MonthlyHistory",
         "status": "available" if "water_extent" in have else "no data processed",
         "note": "Optical water mapping; cloud and salt crust affect accuracy."},
        {"id": "salinity", "title": "Salinity", "status": "no direct dataset integrated",
         "note": "No satellite product here measures soil/water salinity. Water extent and NDVI anomalies can only hint at salinity influence; "
                 "field EC measurements or a validated salinity index/model would be required."},
        {"id": "groundwater", "title": "Groundwater levels", "dataset": "CGWB / India-WRIS (user upload)",
         "status": "available" if "groundwater" in have else "awaiting upload",
         "note": "No automatic CGWB/India-WRIS download is implemented. Upload measured well levels as CSV. Groundwater trends must come from "
                 "measured levels, never from ET or modelled soil moisture."},
        {"id": "cyclone", "title": "Cyclone Biparjoy (June 2023)", "status": "available" if "ndvi" in have else "no data processed",
         "note": "Placebo-year comparison; association only, not attribution."}]}


# ------------------------------------------------------------------ spatial
LAYER_META = {
    "ndvi": ("NDVI", "", "YlGn"), "precip": ("Precipitation", "mm", "Blues"), "lst_day": ("Land surface temp. (day)", "°C", "inferno"),
    "lst_night": ("Land surface temp. (night)", "°C", "magma"), "et": ("Evapotranspiration", "mm", "BuGn"),
    "sm_surface": ("Surface soil moisture", "kg/m²", "PuBu"), "sm_root": ("Root-zone soil moisture", "kg/m²", "PuBuGn"),
}


def _stack(source, region, variable, season):
    p = store.raster_path(source, region, variable, season)
    if not p.exists():
        raise svc.AppError("no_data", f"No raster stack for {variable}/{season} (source={source}). "
                                      "Run a 'stack' job in Settings (needs Earth Engine) or generate the sample.", 404)
    def load():
        info = PX.read_stack(p)
        rep = RQ.validate_stack(info, get_region(region)["bbox"], require_years=season != "static")
        if not rep["ok"]:
            raise svc.AppError("bad_raster", f"Raster {variable}/{season} failed quality control: " + "; ".join(rep["issues"]), 422)
        info["qc"] = rep
        return info
    return svc.cached(("stack", str(p), p.stat().st_mtime_ns), load)


def _bounds(info):
    b = info["bounds"]
    return {"south": b.bottom, "west": b.left, "north": b.top, "east": b.right}


@spatial.get("/layers")
def layers(region: str = "banni", source: Source = "processed"):
    svc.check(region)
    items = []
    for key, season in store.list_rasters(source, region):
        if season == "static":
            continue
        info = _stack(source, region, key, season)
        yrs = PX.band_years(info["descriptions"], info["data"].shape[0])
        d = info["data"][np.isfinite(info["data"])]
        label, unit, cmap = LAYER_META.get(key, (key, "", "viridis"))
        items.append({"variable": key, "season": season, "label": label, "unit": unit, "cmap": cmap,
                      "years": [int(y) for y in yrs if np.isfinite(y)], "bounds": _bounds(info),
                      "vmin": float(np.percentile(d, 2)) if d.size else None, "vmax": float(np.percentile(d, 98)) if d.size else None,
                      "crs": info["crs"].to_string() if info["crs"] else None, "shape": [info["height"], info["width"]],
                      "kind": info["tags"].get("kind", "observed")})
    return {"items": items, "total": len(items)}


@spatial.get("/layer.png")
def layer_png(region: str = "banni", source: Source = "processed", variable: str = "ndvi", season: Season = "annual",
              year: int | None = None, product: Literal["year", "mean"] = "year"):
    svc.check(region, variable)
    info = _stack(source, region, variable, season)
    yrs = PX.band_years(info["descriptions"], info["data"].shape[0])
    allv = info["data"][np.isfinite(info["data"])]
    vmin, vmax = (np.percentile(allv, 2), np.percentile(allv, 98)) if allv.size else (0, 1)
    if product == "mean":
        arr = np.nanmean(info["data"], axis=0)
    else:
        idx = np.where(yrs == year)[0]
        if year is None or len(idx) == 0:
            raise svc.AppError("bad_year", f"Year {year} not in stack ({int(np.nanmin(yrs))}-{int(np.nanmax(yrs))}).", 422)
        arr = info["data"][idx[0]]
    cmap = LAYER_META.get(variable, ("", "", "viridis"))[2]
    return Response(PX.render_scalar_png(arr, float(vmin), float(vmax), cmap), media_type="image/png",
                    headers={"Cache-Control": "no-store"})


def _pixel(region, source, variable, season, start, end, q, mask="none", thr=10.0):
    info = _stack(source, region, variable, season)
    yrs = PX.band_years(info["descriptions"], info["data"].shape[0])
    keep = np.isfinite(yrs) & (yrs >= (start or -1e9)) & (yrs <= (end or 1e9))
    if keep.sum() < PX.MIN_VALID:
        raise svc.AppError("insufficient_data", f"Pixel trends need >= {PX.MIN_VALID} years; the selection has {int(keep.sum())}.", 422)
    mt = store.raster_path(source, region, variable, season).stat().st_mtime_ns
    mmt = 0
    if mask == "rann_water":
        mp = store.raster_path(source, region, "water_occurrence", "static")
        if not mp.exists():
            raise svc.AppError("no_data", "Rann-water masking needs the static JRC occurrence raster (stack job: water_occurrence / static). It has not been processed.", 404)
        mmt = mp.stat().st_mtime_ns
    key = ("pix", region, source, variable, season, start, end, q, mask, thr, mt, mmt)

    def compute():
        data, rep = info["data"][keep], None
        if mask == "rann_water":
            occ_info = _stack(source, region, "water_occurrence", "static")
            occ = occ_info["data"][0] if RQ.grids_aligned(info, occ_info) else RQ.align_to(occ_info, info)[0]
            try:
                data, rep = RQ.apply_water_mask(data, occ, thr)
            except RQ.RasterError as e:
                raise svc.AppError("bad_raster", str(e), 422)
            rep["resampled_to_stack_grid"] = not RQ.grids_aligned(info, occ_info)
        return PX.pixel_trends(data, yrs[keep], q), info, yrs[keep], rep
    return svc.cached(key, compute)


@spatial.get("/pixel-trend")
def pixel_trend(region: str = "banni", source: Source = "processed", variable: str = "ndvi", season: Season = "annual",
                start: int | None = None, end: int | None = None, q: float = Query(0.05, gt=0, lt=0.5),
                mask: Literal["none", "rann_water"] = "none", water_thr: float = Query(10.0, ge=1, le=100)):
    svc.check(region, variable)
    res, info, yrs, maskrep = _pixel(region, source, variable, season, start, end, q, mask, water_thr)
    summ = PX.summarise(res, q)
    return {"result": {**summ, "mask": maskrep, "geometry_id": get_region(region)["geometry"]["id"], "raster_qc": info.get("qc"), "years": [int(yrs.min()), int(yrs.max())], "n_years": int(len(yrs)), "bounds": _bounds(info),
                       "shape": [info["height"], info["width"]], "crs": info["crs"].to_string() if info["crs"] else None,
                       "slope_unit": f"{LAYER_META.get(variable, ('', '', ''))[1] or 'units'} per year",
                       "method": "Per-pixel Mann-Kendall (tie-corrected) + Sen slope; Benjamini-Hochberg FDR across pixels",
                       "limitations": ["Pixels are spatially autocorrelated, so FDR control is approximate.",
                                       "Per-pixel tests ignore serial correlation (no Hamed-Rao at pixel scale).",
                                       "A significant NDVI trend is a greenness change, not evidence of a cause or species."]},
            "meta": {"region": region, "variable": variable, "season": season, "source": source, "kind": info["tags"].get("kind", "observed"),
                     "synthetic": info["tags"].get("kind") == "synthetic", "disclaimer": info["tags"].get("disclaimer")}}


@spatial.get("/pixel-trend.png")
def pixel_trend_png(region: str = "banni", source: Source = "processed", variable: str = "ndvi", season: Season = "annual",
                    start: int | None = None, end: int | None = None, q: float = Query(0.05, gt=0, lt=0.5),
                    product: Literal["class", "significant", "slope", "uncorrected"] = "class",
                    mask: Literal["none", "rann_water"] = "none", water_thr: float = Query(10.0, ge=1, le=100)):
    svc.check(region, variable)
    res, _, _, _ = _pixel(region, source, variable, season, start, end, q, mask, water_thr)
    if product in ("class", "significant"):
        png = PX.render_class_png(res["cls"], show_nonsig=product == "class")
    elif product == "uncorrected":
        png = PX.render_class_png(res["cls_uncorrected"])
    else:
        m = np.nanmax(np.abs(res["slope"])) if np.isfinite(res["slope"]).any() else 1
        png = PX.render_scalar_png(res["slope"], -m, m, "RdYlGn")
    return Response(png, media_type="image/png", headers={"Cache-Control": "no-store"})


@spatial.get("/pixel-trend.tif")
def pixel_trend_tif(region: str = "banni", source: Source = "processed", variable: str = "ndvi", season: Season = "annual",
                    start: int | None = None, end: int | None = None, q: float = Query(0.05, gt=0, lt=0.5),
                    mask: Literal["none", "rann_water"] = "none", water_thr: float = Query(10.0, ge=1, le=100)):
    svc.check(region, variable)
    import tempfile
    res, info, yrs, maskrep = _pixel(region, source, variable, season, start, end, q, mask, water_thr)
    from pathlib import Path
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "t.tif"
        PX.write_geotiff(p, {"sen_slope_per_year": res["slope"], "mk_z": res["z"], "p_value": res["p"], "fdr_q_value": res["q_value"],
                             "class_fdr": res["cls"]}, info["transform"], info["crs"],
                         {"variable": variable, "season": season, "years": f"{int(yrs.min())}-{int(yrs.max())}", "fdr_q": q,
                          "class_legend": "1=sig. increase, -1=sig. decrease, 0=not significant (BH-FDR)", "water_mask": str(maskrep), "geometry_id": get_region(region)["geometry"]["id"],
                          "kind": info["tags"].get("kind", "observed"), "method": "Mann-Kendall + Sen, BH-FDR"})
        data = p.read_bytes()
    return Response(data, media_type="image/tiff",
                    headers={"Content-Disposition": f'attachment; filename="{region}_{variable}_{season}_pixel_trend.tif"'})


@spatial.get("/inspect")
def inspect(lat: float = Query(..., ge=-90, le=90), lon: float = Query(..., ge=-180, le=180), region: str = "banni",
            source: Source = "processed", variable: str = "ndvi", season: Season = "annual"):
    svc.check(region, variable)
    info = _stack(source, region, variable, season)
    yrs = PX.band_years(info["descriptions"], info["data"].shape[0])
    vals = [PX.sample_value(info, i, lon, lat) for i in range(info["data"].shape[0])]
    inside = any(v is not None for v in vals) or _inside(info, lat, lon)
    if not inside:
        raise svc.AppError("outside_extent", "Coordinate is outside the raster extent.", 422)
    ok = [(y, v) for y, v in zip(yrs, vals) if v is not None]
    out = {"lat": lat, "lon": lon, "years": [int(y) for y in yrs], "values": vals, "unit": LAYER_META.get(variable, ("", "", ""))[1]}
    if len(ok) >= 10:
        out["trend"] = S.mann_kendall([v for _, v in ok], [y for y, _ in ok])
        out["trend_note"] = "Single-pixel test, uncorrected for multiple testing; exploratory only."
    return {"result": out, "meta": {"region": region, "variable": variable, "season": season, "source": source,
                                   "synthetic": info["tags"].get("kind") == "synthetic"}}


def _inside(info, lat, lon):
    b = info["bounds"]
    return b.left <= lon <= b.right and b.bottom <= lat <= b.top
