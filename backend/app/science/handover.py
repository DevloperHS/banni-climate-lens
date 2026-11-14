"""Reproduction of the Banni handover analysis (pp.5-12) and comparison with its reported values.

The calculations deliberately mirror the handover's Colab scripts, using pymannkendall directly
(hamed_rao_modification_test + sens_slope) so that agreement with the handover does not depend on this
platform's own statistics engine. The platform engine is then cross-checked against the same numbers.
Nothing here forces a match: each comparison is reported as reproduced / consistent / not reproduced.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pymannkendall as mk
import statsmodels.api as sm

from . import stats as S

REF = Path(__file__).resolve().parents[1] / "config" / "handover_reference.json"
MONSOON = (6, 7, 8, 9)

# How the handover's protocol differs from the platform's default engine, and how each difference is handled.
PROTOCOL_DIFFERENCES = [
    {"item": "NDVI quality filtering", "handover": "None (all composites, Earth Engine fill mask only)",
     "platform_default": "Series `ndvi` follows the handover; `ndvi_qa` (SummaryQA==0) is kept as a sensitivity", "status": "aligned + sensitivity"},
    {"item": "NDVI monthly aggregation", "handover": "Mean image of composites dated within the month, then regional mean",
     "platform_default": "Same (series `ndvi`)", "status": "aligned"},
    {"item": "Monsoon aggregation", "handover": "NDVI: mean of the available Jun-Sep monthly values; rainfall: sum of the available Jun-Sep monthly totals (no coverage rule)",
     "platform_default": "Trend/adjusted endpoints require >=3/4 months (mean) or 4/4 (sum); this reproduction module uses the handover rule", "status": "aligned in reproduction; stricter elsewhere"},
    {"item": "Rainfall conversion", "handover": "rate(mm/hr) x (time_end - time_start in days) x 24",
     "platform_default": "Same, with a recorded check against calendar days; unit mm/hr verified in the Earth Engine catalogue", "status": "aligned"},
    {"item": "Trend test", "handover": "Hamed-Rao modified MK always + Sen slope (no CI)",
     "platform_default": "Reports MK and Hamed-Rao, Sen slope with CI; Hamed-Rao used here as headline", "status": "aligned (superset)"},
    {"item": "Regression", "handover": "OLS NDVI ~ monsoon rainfall; residual = observed - predicted; residual trend by Hamed-Rao",
     "platform_default": "Same primary model; sensitivities S1-S5 added", "status": "aligned + sensitivities"},
    {"item": "ET annual", "handover": "Sum of all 8-day composites in the calendar year x 0.1",
     "platform_default": "Monthly rate-based totals summed to the year (equal for constant rates; small redistribution otherwise)", "status": "small known difference"},
    {"item": "ET / soil-moisture rainfall control", "handover": "Monsoon (Jun-Sep) rainfall for annual ET and soil moisture",
     "platform_default": "Adjusted-analysis endpoint now has rain_season (default monsoon)", "status": "aligned"},
    {"item": "Root-zone soil moisture band", "handover": "GLDAS RootMoist_inst", "platform_default": "Changed from a 0-100 cm layer sum to RootMoist_inst", "status": "aligned (was different)"},
    {"item": "Soil moisture aggregation", "handover": "Mean of all 3-hourly images in the year / in Mar-May",
     "platform_default": "Mean of monthly means (equal weight per month)", "status": "small known difference"},
    {"item": "Geometry", "handover": "Rectangle 23.20-23.95N, 68.80-69.95E (~9,751 km2, not the 2,618 km2 grassland)",
     "platform_default": "Same rectangle by default; grassland polygon supported separately once an authoritative file is supplied", "status": "aligned; polygon pending"},
]


def load_reference() -> dict:
    return json.loads(REF.read_text(encoding="utf-8"))


def handover_annual(ndvi_m: pd.Series, rain_m: pd.Series) -> pd.DataFrame:
    """Handover p.6-7: inner-join monthly NDVI and rain, then per year NDVI = mean and rain = SUM over the
    available Jun-Sep months. Years without any monsoon month are dropped."""
    j = pd.concat([ndvi_m.rename("ndvi"), rain_m.rename("rain")], axis=1).dropna()
    j = j[j.index.month.isin(MONSOON)]
    g = j.groupby(j.index.year)
    df = pd.DataFrame({"ndvi_monsoon": g["ndvi"].mean(), "rain_monsoon": g["rain"].sum(), "n_months": g["ndvi"].count()})
    df.index.name = "year"
    return df.sort_index()


def _trend(y: np.ndarray) -> dict:
    t = mk.hamed_rao_modification_test(y)          # exactly as the handover Colab cell
    s = mk.sens_slope(y)
    return {"direction": t.trend if t.trend != "no trend" else "no significant trend", "p": float(t.p), "z": float(t.z),
            "slope": float(s.slope), "n": int(len(y))}


def colab_protocol(df: pd.DataFrame) -> dict:
    """Handover step 15 verbatim: raw NDVI, raw rain, OLS, residual trend."""
    d = df.dropna().sort_index()
    out = {"n_years": int(len(d)), "years": [int(i) for i in d.index]}
    out["ndvi"] = _trend(d["ndvi_monsoon"].values)
    out["rain"] = _trend(d["rain_monsoon"].values)
    X = sm.add_constant(d["rain_monsoon"])
    model = sm.OLS(d["ndvi_monsoon"], X).fit()
    resid = d["ndvi_monsoon"] - model.predict(X)
    out["regression"] = {"r2": float(model.rsquared), "rain_coef": float(model.params["rain_monsoon"]),
                         "rain_p": float(model.pvalues["rain_monsoon"]), "intercept": float(model.params["const"])}
    out["residual"] = _trend(resid.values)
    r = out["residual"]
    out["verdict_rule"] = ("CONFIRMED" if r["p"] < 0.05 and r["slope"] > 0 else "MARGINAL" if r["p"] < 0.10 and r["slope"] > 0 else "NOT CONFIRMED")
    out["verdict_note"] = ("Handover decision rule (p<0.05 and slope>0). A positive residual trend means greener than rainfall alone predicts; "
                           "it does not identify the cause (the handover itself calls the Prosopis link a match, not proof).")
    return out


def water_protocol(w: pd.DataFrame, rain_monsoon: pd.Series) -> dict:
    """Handover step 17: raw trend and rain-adjusted residual trend for ET and root-zone soil moisture."""
    df = w.join(rain_monsoon.rename("rain_monsoon"), how="inner").dropna()
    out = {"n_years": int(len(df))}
    for col in [c for c in ("et_annual_mm", "sm_root_annual") if c in df]:
        X = sm.add_constant(df["rain_monsoon"])
        m = sm.OLS(df[col], X).fit()
        out[col] = {"raw": _trend(df[col].values), "r2_rain": float(m.rsquared), "residual": _trend((df[col] - m.predict(X)).values)}
    return out


def _compare(ref: dict, got: dict | float | None) -> dict:
    """Transparent comparison. Status: reproduced | consistent | not reproduced | not available."""
    if got is None:
        return {"status": "not available", "checks": {}}
    if ref["kind"] == "value":
        rel = abs(got - ref["value"]) / abs(ref["value"])
        st = "reproduced" if rel <= 0.02 else "consistent" if rel <= 0.10 else "not reproduced"
        return {"status": st, "checks": {"relative_difference": rel}}
    chk = {"direction_match": got["direction"] == ref["direction"],
           "significance_match": (got["p"] < 0.05) == (ref["p"] < 0.05)}
    chk["p_close"] = abs(got["p"] - ref["p"]) <= max(0.002, 0.2 * ref["p"]) if ref["p"] > 0.0005 else got["p"] <= 0.001
    if ref.get("slope") not in (None, 0):
        chk["slope_rel_diff"] = abs(got["slope"] - ref["slope"]) / abs(ref["slope"])
        chk["slope_close"] = chk["slope_rel_diff"] <= 0.10
    if ref.get("z") is not None:
        chk["z_diff"] = abs(got["z"] - ref["z"])
    basic = chk["direction_match"] and chk["significance_match"]
    close = chk["p_close"] and chk.get("slope_close", True)
    st = "reproduced" if basic and close else "consistent" if basic else "not reproduced"
    return {"status": st, "checks": chk}


def compare_all(colab: dict | None, water: dict | None, annual_ndvi_2001_2023: dict | None = None) -> list[dict]:
    ref = load_reference()
    got = {}
    if annual_ndvi_2001_2023:
        got["ndvi_annual_2001"] = annual_ndvi_2001_2023.get(2001); got["ndvi_annual_2023"] = annual_ndvi_2001_2023.get(2023)
    if colab:
        got.update(ndvi_monsoon_trend=colab["ndvi"], rain_monsoon_trend=colab["rain"], ndvi_rain_residual_trend=colab["residual"])
    if water:
        if "et_annual_mm" in water:
            got.update(et_annual_trend=water["et_annual_mm"]["raw"], et_rain_residual_trend=water["et_annual_mm"]["residual"])
        if "sm_root_annual" in water:
            got.update(smroot_annual_trend=water["sm_root_annual"]["raw"], smroot_rain_residual_trend=water["sm_root_annual"]["residual"])
    rows = []
    for r in ref["reported"]:
        g = got.get(r["id"])
        rows.append({"id": r["id"], "label": r["label"], "page": r["page"], "unit": r["unit"], "note": r.get("note"),
                     "reported": {k: r.get(k) for k in ("value", "direction", "p", "slope", "z") if r.get(k) is not None},
                     "computed": g, **_compare(r, g)})
    return rows


def engine_cross_check(df: pd.DataFrame) -> dict:
    """The platform's own engine must agree with the pymannkendall-based protocol on the same inputs."""
    d = df.dropna().sort_index()
    mine = S.mann_kendall(d["ndvi_monsoon"].values, d.index.values.astype(float), hamed_rao=True)
    ref = _trend(d["ndvi_monsoon"].values)
    return {"p_engine": mine["p"], "p_pymannkendall": ref["p"], "slope_engine": mine["slope"], "slope_pymannkendall": ref["slope"],
            "agree": bool(abs(mine["p"] - ref["p"]) < 1e-8 and abs(mine["slope"] - ref["slope"]) < 1e-10)}

