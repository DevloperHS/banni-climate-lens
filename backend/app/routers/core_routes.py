"""health, regions, datasets (catalogue, jobs, sample, upload)."""
from __future__ import annotations
import io
from datetime import date
from typing import Literal
import pandas as pd
from fastapi import APIRouter, Depends, UploadFile, File, Form, Query
from pydantic import BaseModel, Field, model_validator

from .. import jobs, services as svc
from ..core import store, sample, groundwater as GW
from ..core.config import get_settings
from ..core.security import require_write, safe_text
from ..core.catalog import CATALOG, spec_dict
from ..core.regions import list_regions, boundary_geojson, geometry_problems
from ..gee import client

health = APIRouter(prefix="/api/health", tags=["health"])
regions = APIRouter(prefix="/api/regions", tags=["regions"])
datasets = APIRouter(prefix="/api/datasets", tags=["datasets"])


@health.api_route("", methods=["GET", "HEAD"])
def health_check():
    """Liveness plus the facts an operator needs: version, writable data dir, free disk, active jobs, Earth Engine configuration."""
    import shutil
    d = get_settings().data_dir
    writable = True
    try:
        probe = d / "cache" / ".health"
        probe.parent.mkdir(parents=True, exist_ok=True)
        probe.write_text("ok"); probe.unlink()
    except OSError:
        writable = False
    try:
        free_gb = round(shutil.disk_usage(d).free / 1e9, 2)
    except OSError:
        free_gb = None
    from ..main import VERSION
    active = sum(1 for j in jobs.list_jobs() if j["status"] in ("queued", "running"))
    status = "ok" if writable else "degraded"
    return {"status": status, "version": VERSION, "time": date.today().isoformat(), "data_dir_writable": writable, "disk_free_gb": free_gb,
            "active_jobs": active, "auth_required_for_writes": bool(get_settings().api_token), "earth_engine_configured": bool(get_settings().ee_project)}


@health.get("/earthengine")
def ee_health(probe: bool = False):
    """Configuration status by default; probe=true attempts a real Earth Engine call."""
    return client.status(probe=probe)


@regions.get("")
def get_regions():
    return {"items": [{**r, "boundary": boundary_geojson(r)} for r in list_regions()], "total": len(list_regions()),
            "invalid_geometries": geometry_problems()}


@regions.get("/{region_id}")
def get_one(region_id: str):
    r = svc.check(region_id)
    return {**r, "boundary": boundary_geojson(r)}


@regions.get("/{region_id}/boundary")
def get_boundary(region_id: str):
    return boundary_geojson(svc.check(region_id))


@datasets.get("")
def catalogue(region: str = "banni", source: Literal["processed", "sample"] = "processed",
              page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100)):
    svc.check(region)
    have = set(store.list_series(source, region))
    rasters = store.list_rasters(source, region)
    items = []
    for k in CATALOG:
        rec = store.load_series(source, region, k) if k in have else None
        d = spec_dict(k)
        d.update(available=rec is not None, kind=rec.get("kind") if rec else None,
                 retrieval_date=(rec or {}).get("provenance", {}).get("retrieval_date"),
                 processing_period=(rec or {}).get("provenance", {}).get("processing_period"),
                 n_months=(sum(v is not None for v in rec["values"]) if rec else 0),
                 rasters=[s for kk, s in rasters if kk == k])
        items.append(d)
    start = (page - 1) * page_size
    return {"items": items[start:start + page_size], "total": len(items), "page": page, "page_size": page_size,
            "earth_engine": client.status()}


@datasets.get("/quality")
def data_quality(region: str = "banni", variable: str = "ndvi", source: Literal["processed", "sample"] = "processed"):
    """Completeness, missing months, value ranges and unit-plausibility flags for one stored series."""
    svc.check(region, variable)
    return svc.quality_report(region, variable, source)


class JobTask(BaseModel):
    type: Literal["series", "stack"]
    key: str
    season: Literal["annual", "monsoon", "summer", "postmonsoon", "winter", "peak", "static"] | None = None

    @model_validator(mode="after")
    def _chk(self):
        if self.key not in CATALOG or CATALOG[self.key].ee_id is None:
            raise ValueError(f"'{self.key}' cannot be extracted from Earth Engine")
        if self.type == "series" and self.key == "water_occurrence":
            raise ValueError("water_occurrence is a static raster; use a stack task with season 'static'")
        if self.type == "stack":
            if self.key in ("water_extent", "water_extent_mndwi", "ndvi_qa", "ndvi_nowater", "grace_tws", "ndvi_aqua", "evi") or self.key.startswith("lc_") or self.season is None:
                raise ValueError("stack tasks need a season and a gridded variable")
            if (self.key == "water_occurrence") != (self.season == "static"):
                raise ValueError("season 'static' is only for water_occurrence (and required for it)")
        return self


class JobRequest(BaseModel):
    region: str = "banni"
    start: int = Field(2001, ge=1980, le=2100)
    end: int = Field(2024, ge=1980, le=2100)
    tasks: list[JobTask] = Field(min_length=1, max_length=40)

    @model_validator(mode="after")
    def _chk(self):
        if self.end < self.start:
            raise ValueError("end must be >= start")
        return self


@datasets.post("/jobs", status_code=202, dependencies=[Depends(require_write)])
def create_job(req: JobRequest):
    svc.check(req.region)
    try:
        client.get_ee()
    except client.EarthEngineUnavailable as e:
        raise svc.AppError("earth_engine_unavailable", str(e), 503)
    return jobs.submit({"region": req.region, "start": req.start, "end": req.end,
                        "tasks": [t.model_dump() for t in req.tasks]})


@datasets.get("/jobs")
def job_list():
    items = jobs.list_jobs()
    return {"items": items, "total": len(items)}


@datasets.get("/jobs/{job_id}")
def job_get(job_id: str):
    j = jobs.get(job_id)
    if not j:
        raise svc.AppError("not_found", f"No job '{job_id}'", 404)
    return j


@datasets.get("/jobs/{job_id}/log")
def job_log(job_id: str):
    """Detailed log (with tracebacks for failed tasks; credentials are redacted)."""
    t = jobs.log_tail(job_id)
    if t is None:
        raise svc.AppError("not_found", f"No log for job '{job_id}'", 404)
    return {"id": job_id, "log": t}


@datasets.post("/jobs/{job_id}/cancel", dependencies=[Depends(require_write)])
def job_cancel(job_id: str):
    j = jobs.cancel(job_id)
    if not j:
        raise svc.AppError("not_found", f"No job '{job_id}'", 404)
    return j


@datasets.post("/jobs/{job_id}/retry", status_code=202, dependencies=[Depends(require_write)])
def job_retry(job_id: str):
    j0 = jobs.get(job_id)
    if not j0:
        raise svc.AppError("not_found", f"No job '{job_id}'", 404)
    if j0["status"] not in jobs.TERMINAL or j0["status"] == "completed":
        raise svc.AppError("bad_state", f"Job is '{j0['status']}'; only failed, cancelled or interrupted jobs can be retried.", 409)
    try:
        client.get_ee()
    except client.EarthEngineUnavailable as e:
        raise svc.AppError("earth_engine_unavailable", str(e), 503)
    return jobs.retry(job_id)


@datasets.post("/sample", dependencies=[Depends(require_write)])
def make_sample(region: str = "banni"):
    svc.check(region)
    return sample.generate(region)


@datasets.delete("/sample", dependencies=[Depends(require_write)])
def delete_sample():
    return {"removed_files": store.clear_source("sample")}


async def read_limited(file: UploadFile) -> bytes:
    """Read an upload in chunks and stop at the size limit (no unbounded memory use)."""
    limit = get_settings().max_upload_mb * 1_000_000
    buf = bytearray()
    while chunk := await file.read(65536):
        buf += chunk
        if len(buf) > limit:
            raise svc.AppError("too_large", f"Upload exceeds {get_settings().max_upload_mb} MB.", 413)
    if b"\x00" in buf[:4096]:
        raise svc.AppError("bad_csv", "File looks binary, not CSV text.", 422)
    return bytes(buf)


@datasets.post("/upload", dependencies=[Depends(require_write)])
async def upload_series(region: str = Form(...), key: str = Form("groundwater"),
                        source: Literal["processed", "sample"] = Form("processed"),
                        source_note: str = Form(""), file: UploadFile = File(...)):
    """Upload measured groundwater levels (CGWB / India-WRIS) as CSV: date,value[,well_id]. Rows are validated; the
    response contains the full validation report. Only groundwater can be uploaded."""
    svc.check(region, key)
    if key != "groundwater":
        raise svc.AppError("bad_request", "Only 'groundwater' can be uploaded; other variables come from Earth Engine.", 422)
    raw = await read_limited(file)
    try:
        df, rep = GW.parse(raw)
    except GW.GroundwaterError as e:
        raise svc.AppError("bad_csv", str(e), 422)
    months = GW.aggregate_monthly(df)
    note = safe_text(source_note or file.filename or "upload")
    prov = {**spec_dict(key), "region": region, "kind": "user-supplied", "retrieval_date": date.today().isoformat(),
            "processing_period": f"{min(months)[:4]}-{max(months)[:4]}", "user_source_note": note,
            "geometry": {"id": "user-supplied wells", "kind": "points", "source": note},
            "processing_config": {"aggregation": "monthly mean per well; multi-well aggregate = mean of per-well anomalies + grand mean",
                                  "rows": rep["rows_valid"], "n_wells": rep["n_wells"], "filename": safe_text(file.filename or "", 80)}}
    GW.save_wells(source, region, df, rep, file.filename or "upload.csv", note)
    store.save_series(source, region, key, months, prov, kind="user-supplied")
    return {"key": key, "months": len(months), "rows": rep["rows_valid"], "validation": rep}
