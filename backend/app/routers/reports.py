"""reports router: insights, CSV / GeoJSON / PDF exports. Every export embeds provenance."""
from __future__ import annotations
import io
import json
from datetime import datetime, timezone
from typing import Literal
from fastapi import APIRouter, Query, Response

from .. import services as svc
from ..core import store
from ..core.catalog import CATALOG
from ..core.regions import boundary_geojson
from ..science import timeseries as TS

Source = Literal["processed", "sample"]
Agg = Literal["monthly", "annual", "summer", "monsoon", "postmonsoon", "winter", "peak"]
reports = APIRouter(prefix="/api/reports", tags=["reports"])


@reports.get("/insights")
def insights(region: str = "banni", source: Source = "processed", start: int | None = None, end: int | None = None):
    svc.check(region)
    return svc.build_insights(region, source, start, end)


@reports.get("/export/csv")
def export_csv(region: str = "banni", variable: str = "ndvi", source: Source = "processed", agg: Agg = "monthly",
               start: int | None = None, end: int | None = None):
    svc.check(region, variable)
    p = svc.series_payload(region, variable, source, agg, start, end)
    m, r = p["meta"], p["result"]
    lines = ["# GlobalClimateLens export",
             f"# generated_utc: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
             f"# region: {region}", f"# variable: {variable} ({r['label']})", f"# unit: {r['unit']}", f"# aggregation: {agg}",
             f"# data_kind: {m['kind']}"]
    if m["synthetic"]:
        lines.append(f"# WARNING: {m['disclaimer']}")
    from ..core.security import safe_text
    for k, v in m["dataset"].items():
        lines.append(f"# {k}: {safe_text(v if v is not None else '', 400)}")
    lines.append("period,value")
    lines += [f"{x},{'' if v is None else repr(v)}" for x, v in zip(r["x"], r["values"])]
    return Response("\n".join(lines) + "\n", media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{region}_{variable}_{agg}.csv"'})


@reports.get("/export/geojson")
def export_geojson(region: str = "banni", source: Source = "processed"):
    """Region boundary Feature with the latest computed trend statistics as properties."""
    r = svc.check(region)
    f = boundary_geojson(r)
    props = f["properties"]
    props.update(computed_area_km2=r["computed_bbox_area_km2"], reference_area_km2=r["reference_area_km2"],
                 generated_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"), data_source=source)
    trends = {}
    for key in CATALOG:
        for agg in ("annual", "monsoon"):
            try:
                t = svc.trend_payload(region, key, source, agg, None, None, 0.05)
            except svc.AppError:
                continue
            rr = t["result"]; pick = rr[rr["recommended"]]
            trends[f"{key}_{agg}"] = {"direction": pick["direction"], "p": pick["p"], "sen_slope": pick["slope"], "unit": f"{CATALOG[key].unit}/yr",
                                      "test": pick["test"], "period": t["meta"]["period"], "kind": t["meta"]["kind"]}
    props["trends"] = trends
    if any(v["kind"] == "synthetic" for v in trends.values()):
        props["WARNING"] = "Contains statistics from SYNTHETIC sample data."
    return Response(json.dumps(f, indent=1), media_type="application/geo+json",
                    headers={"Content-Disposition": f'attachment; filename="{region}.geojson"'})


def _png(fig) -> bytes:
    b = io.BytesIO(); fig.savefig(b, format="png", dpi=150, bbox_inches="tight"); return b.getvalue()


@reports.get("/manifest")
def report_manifest(region: str = "banni", source: Source = "processed", start: int | None = None, end: int | None = None):
    """Which report sections are available for this region/source (and why others are not)."""
    svc.check(region)
    from .. import reporting
    return reporting.manifest(region, source, start, end)


@reports.get("/pdf")
def pdf_report(region: str = "banni", source: Source = "processed", start: int | None = None, end: int | None = None, maps: bool = True):
    """Full research report generated from the stored data at request time."""
    svc.check(region)
    from .. import reporting
    data = reporting.build_pdf(region, source, start, end, include_maps=maps)
    return Response(data, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{region}_report.pdf"'})
