"""File-based store for processed series and raster stacks.

Layout:  data/<source>/series/<region>/<key>.json   (source = processed | sample)
         data/<source>/rasters/<region>/<key>_<season>.tif
Raw downloads live under data/raw/, caches under data/cache/. Observed data and synthetic
sample data never share a directory, so they cannot be confused.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from .config import get_settings
from .security import safe_name

SOURCES = ("processed", "sample")


def _check_source(source: str) -> str:
    if source not in SOURCES:
        raise ValueError(f"source must be one of {SOURCES}")
    return source


def series_path(source: str, region: str, key: str) -> Path:
    return get_settings().data_dir / _check_source(source) / "series" / safe_name(region, "region") / f"{safe_name(key, 'key')}.json"


def raster_path(source: str, region: str, key: str, season: str) -> Path:
    return get_settings().data_dir / _check_source(source) / "rasters" / safe_name(region, "region") / f"{safe_name(key, 'key')}_{safe_name(season, 'season')}.tif"


REQUIRED_PROVENANCE = ("ee_id", "provider", "variable", "spatial_resolution", "temporal_resolution", "unit", "scale_factor",
                       "quality_filter", "processing_period", "retrieval_date", "processing_config", "geometry")
KINDS = ("observed", "synthetic", "user-supplied")


def validate_series(key: str, months: dict, provenance: dict, kind: str) -> None:
    """Schema check applied before anything is stored. Observed data must carry full provenance, including the
    geometry used, the retrieval date and the unit; values must be finite numbers or None."""
    import math, re
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    if not months:
        raise ValueError("empty series")
    for d, v in months.items():
        if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", d):
            raise ValueError(f"bad month key '{d}' (expected YYYY-MM)")
        if v is not None and (not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v)):
            raise ValueError(f"non-finite or non-numeric value for {d}: {v!r}")
    if kind == "observed":
        miss = [k for k in REQUIRED_PROVENANCE if provenance.get(k) in (None, "", {})]
        if miss:
            raise ValueError(f"observed series '{key}' lacks provenance fields: {', '.join(miss)}")
        if not provenance["geometry"].get("id"):
            raise ValueError("provenance.geometry.id missing")


def save_series(source: str, region: str, key: str, months: dict[str, float | None], provenance: dict,
                kind: str = "observed") -> Path:
    validate_series(key, months, provenance, kind)
    p = series_path(source, region, key)
    p.parent.mkdir(parents=True, exist_ok=True)
    dates = sorted(months)
    rec = {
        "region": region, "key": key, "kind": kind,
        "dates": dates, "values": [months[d] for d in dates],
        "provenance": {**provenance, "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds")},
    }
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(rec), encoding="utf-8")
    tmp.replace(p)            # atomic: readers never see a half-written series
    return p


def load_series(source: str, region: str, key: str) -> dict | None:
    p = series_path(source, region, key)
    if not p.exists():
        return None
    rec = json.loads(p.read_text(encoding="utf-8"))
    rec["_mtime"] = p.stat().st_mtime_ns
    return rec


def list_series(source: str, region: str) -> list[str]:
    d = series_path(source, region, "x").parent
    return sorted(p.stem for p in d.glob("*.json")) if d.exists() else []


def list_rasters(source: str, region: str) -> list[tuple[str, str]]:
    d = raster_path(source, region, "x", "x").parent
    out = []
    if d.exists():
        for p in sorted(d.glob("*.tif")):
            key, _, season = p.stem.rpartition("_")
            out.append((key, season))
    return out


def clear_source(source: str) -> int:
    import shutil
    root = get_settings().data_dir / _check_source(source)
    n = sum(1 for _ in root.rglob("*") if _.is_file() and _.name != ".gitkeep")
    for child in root.iterdir():
        if child.name != ".gitkeep":
            shutil.rmtree(child) if child.is_dir() else child.unlink()
    return n


def save_raw(region: str, key: str, rows: list, provenance: dict) -> Path:
    """Raw extraction output (before aggregation), kept apart from processed series; timestamped, never overwritten."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    p = get_settings().data_dir / "raw" / safe_name(region, "region") / f"{safe_name(key, 'key')}_{stamp}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"region": region, "key": key, "provenance": provenance, "rows": rows}), encoding="utf-8")
    tmp.replace(p)
    return p


def list_raw(region: str) -> list[str]:
    d = get_settings().data_dir / "raw" / safe_name(region, "region")
    return sorted(p.name for p in d.glob("*.json")) if d.exists() else []


def clean_partial_files() -> list[str]:
    """Remove *.tmp leftovers from interrupted writes (called at start-up). Returns removed paths."""
    root = get_settings().data_dir
    gone = []
    for p in list(root.rglob("*.tmp")) + list(root.rglob("*.json.tmp")):
        try:
            p.unlink(); gone.append(str(p.relative_to(root)))
        except OSError:
            pass
    return gone


def latest_raw(region: str, key: str) -> dict | None:
    """Most recent raw artifact for `key` (files are timestamped and never overwritten)."""
    d = get_settings().data_dir / "raw" / safe_name(region, "region")
    files = sorted(d.glob(f"{safe_name(key, 'key')}_*.json")) if d.exists() else []
    return json.loads(files[-1].read_text(encoding="utf-8")) if files else None
