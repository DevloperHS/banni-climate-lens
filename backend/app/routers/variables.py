"""Variable-group routers (vegetation, rainfall, temperature, water, landcover) sharing one implementation."""
from __future__ import annotations
from typing import Literal
import numpy as np
from fastapi import APIRouter, Query
from .. import services as svc
from ..core import store
from ..core.catalog import CATALOG
from ..science import stats as S
from ..science import timeseries as TS

Source = Literal["processed", "sample"]
Agg = Literal["monthly", "annual", "summer", "monsoon", "postmonsoon", "winter", "peak"]
TrendAgg = Literal["annual", "summer", "monsoon", "postmonsoon", "winter", "peak"]


def make_router(prefix: str, group: str, default: str) -> APIRouter:
    keys = [k for k, s in CATALOG.items() if s.group == group]
    r = APIRouter(prefix=f"/api/{prefix}", tags=[prefix])

    def var(variable: str | None) -> str:
        v = variable or default
        if v not in keys:
            raise svc.AppError("unknown_variable", f"'{v}' is not a {prefix} variable. Valid: {', '.join(keys)}", 422)
        return v

    @r.get("/variables")
    def variables(region: str = "banni", source: Source = "processed"):
        svc.check(region)
        have = set(store.list_series(source, region))
        return {"items": [{"key": k, "label": CATALOG[k].label, "unit": CATALOG[k].unit, "available": k in have} for k in keys],
                "default": default}

    @r.get("/timeseries")
    def timeseries(region: str = "banni", variable: str | None = None, source: Source = "processed", agg: Agg = "monthly",
                   start: int | None = Query(None, ge=1980), end: int | None = Query(None, le=2100)):
        v = var(variable); svc.check(region)
        return svc.series_payload(region, v, source, agg, start, end)

    @r.get("/trend")
    def trend(region: str = "banni", variable: str | None = None, source: Source = "processed", agg: TrendAgg = "annual",
              start: int | None = Query(None, ge=1980), end: int | None = Query(None, le=2100),
              alpha: float = Query(0.05, gt=0, lt=0.5)):
        v = var(variable); svc.check(region)
        return svc.cached(("trend", region, v, source, agg, start, end, alpha, _mt(source, region, v)),
                          lambda: svc.trend_payload(region, v, source, agg, start, end, alpha))

    @r.get("/anomalies")
    def anomalies(region: str = "banni", variable: str | None = None, source: Source = "processed", agg: Agg = "annual",
                  start: int | None = None, end: int | None = None):
        v = var(variable); svc.check(region)
        return svc.anomalies_payload(region, v, source, agg, start, end)

    @r.get("/monthly-pattern")
    def monthly_pattern(region: str = "banni", variable: str | None = None, source: Source = "processed",
                        start: int | None = None, end: int | None = None):
        v = var(variable); svc.check(region)
        return svc.monthly_pattern_payload(region, v, source, start, end)

    @r.get("/seasonal-comparison")
    def seasonal(region: str = "banni", variable: str | None = None, source: Source = "processed",
                 start: int | None = None, end: int | None = None, alpha: float = Query(0.05, gt=0, lt=0.5)):
        v = var(variable); svc.check(region)
        return svc.seasonal_comparison_payload(region, v, source, start, end, alpha)

    return r


def _mt(source, region, key):
    p = store.series_path(source, region, key)
    return p.stat().st_mtime_ns if p.exists() else 0


vegetation = make_router("vegetation", "vegetation", "ndvi")
rainfall = make_router("rainfall", "rainfall", "precip")
temperature = make_router("temperature", "temperature", "lst_day")
water = make_router("water", "water", "et")
landcover = make_router("landcover", "landcover", "lc_grassland")


@vegetation.get("/landsat-comparison")
def landsat_comparison(region: str = "banni", source: Source = "processed", start: int | None = None, end: int | None = None):
    """MODIS Sep-Oct mean NDVI vs Landsat Sep-Oct composite NDVI, per year."""
    svc.check(region)
    mod, rec_m = svc.annual(region, "ndvi", source, "peak", start, end)
    lan, rec_l = svc.annual(region, "ndvi_landsat", source, "annual", start, end)
    import pandas as pd
    df = pd.concat([mod.rename("modis"), lan.rename("landsat")], axis=1).dropna()
    if len(df) < 6:
        raise svc.AppError("insufficient_data", f"Only {len(df)} overlapping years between MODIS and Landsat.", 422)
    out = {"years": [int(i) for i in df.index], "modis": df["modis"].tolist(), "landsat": df["landsat"].tolist(),
           "correlation": S.correlation(df["modis"], df["landsat"]),
           "trend_modis": S.trend_report(df["modis"].values, df.index.values.astype(float)),
           "trend_landsat": S.trend_report(df["landsat"].values, df.index.values.astype(float)),
           "species_discrimination": {
               "status": "not attempted",
               "reason": ("Species-level separation (e.g. Prosopis juliflora vs native grasses) cannot be inferred from NDVI. "
                          "It would require labelled field points, multi-temporal/multi-band spectral features, a validated "
                          "classifier with an independent accuracy assessment. None of these inputs exist in this repository.")},
           "note": "Landsat is a Sep-Oct median composite assigned to October; years with no clear scenes are absent. Sensor differences (TM/ETM+/OLI) are not harmonised."}
    return {"result": out, "meta": svc.meta_of(rec_l, compared_with=svc.meta_of(rec_m)["dataset"])}
