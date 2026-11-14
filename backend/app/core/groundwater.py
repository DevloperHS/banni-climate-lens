"""Measured groundwater import, validation and per-well analysis (CGWB / India-WRIS style data supplied as CSV).

Required columns: date, value  (depth to water level, metres below ground level; larger = deeper)
Optional columns: well_id, lat, lon.
No groundwater data ships with the project and none is inferred from ET or modelled soil moisture.
"""
from __future__ import annotations
import io
import json
import re
from datetime import date, datetime, timezone
import numpy as np
import pandas as pd

from . import store
from .config import get_settings
from ..science import stats as S

MAX_ROWS = 200_000
DEPTH_MIN, DEPTH_MAX = 0.0, 300.0     # m b.g.l.; outside -> rejected as implausible
SAFE_ID = re.compile(r"[^A-Za-z0-9_.-]")


class GroundwaterError(ValueError):
    pass


def parse(raw: bytes) -> tuple[pd.DataFrame, dict]:
    try:
        df = pd.read_csv(io.BytesIO(raw))
    except Exception as e:
        raise GroundwaterError(f"unreadable CSV: {e}")
    df.columns = [c.strip().lower() for c in df.columns]
    if not {"date", "value"} <= set(df.columns):
        raise GroundwaterError("CSV needs columns 'date' and 'value' (optional: well_id, lat, lon)")
    if len(df) > MAX_ROWS:
        raise GroundwaterError(f"too many rows (max {MAX_ROWS})")
    n0 = len(df)
    reasons: dict[str, int] = {}

    def drop(mask, why):
        nonlocal df
        if mask.any():
            reasons[why] = reasons.get(why, 0) + int(mask.sum())
            df = df[~mask]

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    drop(df["date"].isna(), "unparseable date")
    drop(df["value"].isna(), "non-numeric value")
    drop(df["date"] > pd.Timestamp(datetime.now(timezone.utc).date()), "date in the future")
    drop(df["date"] < pd.Timestamp("1950-01-01"), "date before 1950")
    drop(~df["value"].between(DEPTH_MIN, DEPTH_MAX), f"depth outside {DEPTH_MIN}-{DEPTH_MAX} m")
    df["well_id"] = df["well_id"].astype(str).map(lambda s: SAFE_ID.sub("_", s.strip())[:40]) if "well_id" in df.columns else "well_1"
    dups = int(df.duplicated(["well_id", "date"]).sum())
    df = df.drop_duplicates(["well_id", "date"], keep="last")
    wells = df.groupby("well_id")["value"].agg(["count", "min", "max"])
    jumps = []
    for w, g in df.sort_values("date").groupby("well_id"):
        d = g["value"].diff().abs()
        if len(g) >= 8 and (d > 5 * max(d.median(), 0.05)).any():
            jumps.append({"well_id": w, "n_large_jumps": int((d > 5 * max(d.median(), 0.05)).sum())})
    rep = {"rows_in": int(n0), "rows_valid": int(len(df)), "rejected_by_reason": reasons, "duplicates_removed": dups,
           "n_wells": int(df["well_id"].nunique()), "date_range": [str(df["date"].min().date()), str(df["date"].max().date())] if len(df) else None,
           "readings_per_well": {k: int(v) for k, v in wells["count"].items()}, "wells_with_large_jumps": jumps,
           "unit_assumption": "metres below ground level (depth to water); larger = deeper = lower water table",
           "warnings": []}
    if len(df) < 4:
        raise GroundwaterError("fewer than 4 valid rows after validation: " + (json.dumps(reasons) if reasons else "no data"))
    if (wells["count"] < 8).all():
        rep["warnings"].append("no well has >= 8 readings; per-well trend tests are not possible")
    if rep["n_wells"] > 1:
        rep["warnings"].append("Wells are aggregated as the mean of per-well anomalies so that different well depths do not bias the trend.")
    if jumps:
        rep["warnings"].append("Large step changes detected in some wells (pumping, well deepening, datum change?). Inspect before interpreting trends.")
    return df.reset_index(drop=True), rep


def aggregate_monthly(df: pd.DataFrame) -> dict[str, float]:
    df = df.copy()
    df["m"] = df["date"].dt.to_period("M")
    pm = df.groupby(["well_id", "m"])["value"].mean().reset_index()
    if pm["well_id"].nunique() == 1:
        s = pm.groupby("m")["value"].mean()
    else:
        pm["anom"] = pm["value"] - pm.groupby("well_id")["value"].transform("mean")
        grand = pm.groupby("well_id")["value"].mean().mean()
        s = pm.groupby("m")["anom"].mean() + grand
    return {str(k): float(v) for k, v in s.items()}


def well_dir(region: str, source: str):
    return get_settings().data_dir / source / "groundwater" / region


def save_wells(source: str, region: str, df: pd.DataFrame, rep: dict, filename: str, note: str):
    d = well_dir(region, source)
    d.mkdir(parents=True, exist_ok=True)
    def _coord(g, col):         # optional per-well location (first valid value), used to place wells on the dashboard map
        if col not in g:
            return None
        v = pd.to_numeric(g[col], errors="coerce").dropna()
        return float(v.iloc[0]) if len(v) else None
    wells = {w: {"dates": [x.strftime("%Y-%m-%d") for x in g.sort_values("date")["date"]], "values": [float(v) for v in g.sort_values("date")["value"]],
                 "lat": _coord(g, "lat"), "lon": _coord(g, "lon")}
             for w, g in df.groupby("well_id")}
    payload = {"region": region, "wells": wells, "validation": rep, "source_note": note[:200].replace("\n", " "), "filename": SAFE_ID.sub("_", filename)[:80],
               "uploaded": date.today().isoformat(), "unit": "m below ground level"}
    tmp = d / "wells.json.tmp"
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    tmp.replace(d / "wells.json")


def load_wells(source: str, region: str) -> dict | None:
    p = well_dir(region, source) / "wells.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def per_well_trends(wells: dict, alpha: float = 0.05, min_obs: int = 8) -> list[dict]:
    """Mann-Kendall + Sen per well on annual means (years with >=1 reading) with BH-FDR across wells."""
    rows = []
    for w, rec in wells["wells"].items():
        s = pd.Series(rec["values"], index=pd.to_datetime(rec["dates"]))
        a = s.groupby(s.index.year).mean()
        if len(a) < max(min_obs // 2, 4):
            rows.append({"well_id": w, "n_years": int(len(a)), "status": "too few years"})
            continue
        t = S.mann_kendall(a.values, a.index.values.astype(float), alpha)
        rows.append({"well_id": w, "n_years": int(len(a)), "status": "tested", "direction": t["direction"], "p": t["p"], "slope_m_per_yr": t["slope"],
                     "ci_low": t["slope_ci_low"], "ci_high": t["slope_ci_high"],
                     "meaning": ("water table deepening" if t["direction"] == "increasing" else "water table shallowing" if t["direction"] == "decreasing" else "no significant change")})
    tested = [r for r in rows if r["status"] == "tested"]
    if tested:
        _, adj = S.benjamini_hochberg(np.array([r["p"] for r in tested]), alpha)
        for r, q in zip(tested, adj):
            r["p_fdr"] = float(q); r["significant_fdr"] = bool(q <= alpha)
    return rows
