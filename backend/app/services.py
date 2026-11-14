"""Application services: load stored series, aggregate, run analyses, build insights.
Keeps routers thin and science modules free of web concerns."""
from __future__ import annotations
import threading
from typing import Any
import numpy as np
import pandas as pd

from .core import store
from .core.catalog import CATALOG, spec_dict
from .core.regions import get_region
from .science import stats as S
from .science import timeseries as TS


class AppError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        self.code, self.message, self.status = code, message, status


def no_data(key: str, region: str, source: str) -> AppError:
    hint = ("Run an Earth Engine processing job (Settings > Data processing) after configuring credentials, "
            "or upload data." if source == "processed" else "Generate the synthetic sample in Settings.")
    return AppError("no_data", f"No '{key}' series for region '{region}' (source={source}). {hint}", 404)


def check(region: str, key: str | None = None):
    try:
        r = get_region(region)
    except KeyError as e:
        raise AppError("unknown_region", str(e.args[0]), 404)
    if key is not None and key not in CATALOG:
        raise AppError("unknown_variable", f"Unknown variable '{key}'. Valid: {', '.join(CATALOG)}", 422)
    return r


LANDCOVER = {k for k in CATALOG if k.startswith("lc_")}
SPARSE = {"ndvi_landsat", "groundwater", "salinity_index", "grace_tws"} | LANDCOVER
ONE_PER_YEAR = {"ndvi_landsat", "salinity_index"} | LANDCOVER
_cache: dict[tuple, Any] = {}
_cache_lock = threading.Lock()


def cached(key: tuple, fn):
    with _cache_lock:
        if key in _cache:
            return _cache[key]
    val = fn()
    with _cache_lock:
        if len(_cache) > 400:
            _cache.clear()
        _cache[key] = val
    return val


def load(region: str, key: str, source: str) -> dict:
    check(region, key)
    if source not in store.SOURCES:
        raise AppError("bad_source", "source must be 'processed' or 'sample'", 422)
    rec = store.load_series(source, region, key)
    if rec is None:
        raise no_data(key, region, source)
    return rec


def meta_of(rec: dict, **extra) -> dict:
    prov = rec.get("provenance", {})
    return {"region": rec["region"], "variable": rec["key"], "kind": rec.get("kind", "observed"),
            "synthetic": rec.get("kind") == "synthetic", "disclaimer": prov.get("disclaimer"),
            "dataset": {k: prov.get(k) for k in ("ee_id", "provider", "variable", "spatial_resolution", "temporal_resolution",
                                                  "unit", "scale_factor", "quality_filter", "processing_period",
                                                  "retrieval_date", "limitations")},
            "processing_config": prov.get("processing_config"), **extra}


def monthly(region: str, key: str, source: str, start: int | None = None, end: int | None = None):
    rec = load(region, key, source)
    s = TS.clip_years(TS.to_series(rec["dates"], rec["values"]), start, end)
    if s.dropna().empty:
        raise AppError("no_data", f"'{key}' has no valid values in {start}-{end}.", 404)
    return s, rec


def annual(region: str, key: str, source: str, agg: str, start=None, end=None):
    """Year-indexed aggregate for the season `agg` using the dataset's reducer."""
    if agg not in TS.SEASONS:
        raise AppError("bad_aggregation", f"agg must be one of monthly, {', '.join(TS.SEASONS)}", 422)
    s, rec = monthly(region, key, source, start, end)
    if key in SPARSE:
        # Irregularly sampled series (one Landsat composite a year; a few well readings a year):
        # mean of whatever observations fall in the season, with a minimum count, no coverage rule.
        sd = s.dropna()
        sd = sd[sd.index.month.isin(TS.SEASONS["annual" if key in ONE_PER_YEAR else agg])]
        g = sd.groupby(sd.index.year)
        a = g.mean()[g.count() >= (1 if key in ONE_PER_YEAR or agg != "annual" else 2)]
    else:
        a = TS.seasonal_aggregate(s, agg, CATALOG[key].reducer).dropna()
    if len(a) == 0:
        raise AppError("insufficient_data", f"No complete '{agg}' aggregates for '{key}' in the requested period.", 422)
    return a, rec


def series_payload(region, key, source, agg, start, end) -> dict:
    spec = CATALOG[key]
    if agg == "monthly":
        s, rec = monthly(region, key, source, start, end)
        d, v = TS.from_series(s)
        return {"result": {"x": d, "values": v, "frequency": "monthly", "unit": spec.unit, "label": spec.label},
                "meta": meta_of(rec, aggregation="monthly")}
    a, rec = annual(region, key, source, agg, start, end)
    return {"result": {"x": [int(i) for i in a.index], "values": [float(x) for x in a.values], "frequency": "annual",
                       "aggregation": agg, "reducer": spec.reducer, "unit": spec.unit, "label": spec.label},
            "meta": meta_of(rec, aggregation=agg)}


def trend_payload(region, key, source, agg, start, end, alpha) -> dict:
    a, rec = annual(region, key, source, agg, start, end)
    if len(a) < 4:
        raise AppError("insufficient_data", f"Trend tests need >= 4 years; have {len(a)}.", 422)
    rep = S.trend_report(a.values, a.index.values.astype(float), alpha)
    spec = CATALOG[key]
    return {"result": {**rep, "years": [int(i) for i in a.index], "values": [float(v) for v in a.values],
                       "unit": spec.unit, "unit_short": short_unit(key), "slope_unit": f"{short_unit(key)} per year", "aggregation": agg,
                       "line": [float(rep["mk"]["intercept"] + rep["mk"]["slope"] * y) for y in a.index],
                       "interpretation": explain_trend(spec.label, agg, rep, short_unit(key)),
                       "limitations": spec.limitations},
            "meta": meta_of(rec, aggregation=agg, method="Mann-Kendall + Hamed-Rao, Sen's slope", alpha=alpha,
                            period=f"{int(a.index.min())}-{int(a.index.max())}")}


def short_unit(key: str) -> str:
    """Unit for slopes: 'NDVI' for indices, otherwise the unit without its parenthetical note."""
    if key.startswith("ndvi"):
        return "NDVI"
    if key.startswith("evi"):
        return "EVI"
    return CATALOG[key].unit.split(" (")[0]


def explain_trend(label: str, agg: str, rep: dict, unit: str) -> str:
    t = rep[rep["recommended"]]
    ac = rep["lag1_autocorr"]
    base = (f"{label} ({agg}) shows {t['direction']} over {t['n']} years "
            f"({t['test']}: Z={t['z']:.2f}, p={t['p']:.3g}; Sen slope {t['slope']:+.4g} {unit}/yr, "
            f"95% CI {t['slope_ci_low']:+.4g} to {t['slope_ci_high']:+.4g}).")
    if t["significant"]:
        base += " The monotonic change is unlikely to be chance at the 5% level, but this does not identify its cause."
    else:
        base += " Absence of significance means the data cannot distinguish a trend from natural variability; it does not prove no change."
    if ac is not None and abs(ac) > 0.3:
        base += f" Lag-1 autocorrelation is {ac:.2f}, so the Hamed-Rao corrected test is preferred."
    return base


def anomalies_payload(region, key, source, agg, start, end) -> dict:
    if agg == "monthly":
        s, rec = monthly(region, key, source, start, end)
        z = TS.standardised_monthly_anomaly(s).dropna()
        a = TS.monthly_anomaly(s).reindex(z.index)
        return {"result": {"x": [d.strftime("%Y-%m") for d in z.index], "anomaly": a.tolist(), "z": z.tolist(),
                           "flag": (z.abs() > 2).tolist(), "frequency": "monthly", "unit": CATALOG[key].unit,
                           "note": "Anomaly = value minus the long-term mean of the same calendar month; z standardises by that month's SD. |z|>2 is flagged."},
                "meta": meta_of(rec, aggregation="monthly")}
    a, rec = annual(region, key, source, agg, start, end)
    df = TS.annual_anomaly(a)
    return {"result": {"x": [int(i) for i in df.index], "value": df["value"].tolist(), "anomaly": df["anomaly"].tolist(),
                       "z": df["z"].tolist(), "flag": df["flag"].astype(bool).tolist(), "frequency": "annual",
                       "unit": CATALOG[key].unit, "baseline": f"{int(a.index.min())}-{int(a.index.max())} mean",
                       "note": "Anomaly vs the mean of the analysed period; |z|>2 flagged (about 5% expected by chance)."},
            "meta": meta_of(rec, aggregation=agg)}


def monthly_pattern_payload(region, key, source, start, end) -> dict:
    s, rec = monthly(region, key, source, start, end)
    g = s.groupby(s.index.month)
    return {"result": {"month": list(range(1, 13)), "mean": [_f(g.mean().get(m)) for m in range(1, 13)],
                       "sd": [_f(g.std().get(m)) for m in range(1, 13)], "min": [_f(g.min().get(m)) for m in range(1, 13)],
                       "max": [_f(g.max().get(m)) for m in range(1, 13)], "unit": CATALOG[key].unit},
            "meta": meta_of(rec)}


def seasonal_comparison_payload(region, key, source, start, end, alpha) -> dict:
    out = {}
    rec = None
    for season in ("annual", "summer", "monsoon", "postmonsoon", "winter"):
        try:
            a, rec = annual(region, key, source, season, start, end)
        except AppError:
            continue
        row = {"years": [int(i) for i in a.index], "values": [float(v) for v in a.values], "mean": float(a.mean())}
        if len(a) >= 4:
            tr = S.trend_report(a.values, a.index.values.astype(float), alpha)
            t = tr[tr["recommended"]]
            row["trend"] = {"direction": t["direction"], "p": t["p"], "slope": t["slope"], "test": t["test"]}
        out[season] = row
    if not out:
        raise no_data(key, region, source)
    return {"result": {"seasons": out, "unit": CATALOG[key].unit}, "meta": meta_of(rec)}


def _f(x):
    return None if x is None or not np.isfinite(x) else float(x)


# ----------------------------------------------------------------------- rainfall-adjusted
def _response_rain_pairs(region, response, source, season, start, end, rain_season="monsoon"):
    resp, rec_r = annual(region, response, source, season, start, end)
    if rain_season == "prev_monsoon":      # dry-season greenness is plausibly set by the PREVIOUS monsoon's water
        rain, rec_p = annual(region, "precip", source, "monsoon", start, end)
        rain = rain.copy(); rain.index = rain.index + 1
    else:
        rain, rec_p = annual(region, "precip", source, rain_season, start, end)
    # previous-year same-season rain (lagged water availability)
    prev = rain.copy(); prev.index = prev.index + 1
    df = pd.concat([resp.rename("y"), rain.rename("rain"), prev.rename("rain_prev")], axis=1)
    df = df.dropna(subset=["y", "rain"])
    return df, rec_r, rec_p


def rainfall_adjusted_payload(region, source, response="ndvi", season="monsoon", start=None, end=None, alpha=0.05,
                              rain_season="monsoon") -> dict:
    """Response (aggregated over `season`) ~ rainfall total over `rain_season`. The handover controls annual ET and soil
    moisture with MONSOON rainfall, so rain_season defaults to monsoon."""
    if response == "precip":
        raise AppError("bad_request", "The response variable cannot be precipitation.", 422)
    df, rec_r, rec_p = _response_rain_pairs(region, response, source, season, start, end, rain_season)
    try:
        res = S.rainfall_adjusted(df.index.values, df["y"].values, df["rain"].values, df["rain_prev"].values, alpha)
    except ValueError as e:
        raise AppError("insufficient_data", str(e), 422)
    # S5: monthly deseasonalised check (removes the seasonal cycle explicitly)
    try:
        res["sensitivity"].append(_monthly_check(region, response, source, start, end, alpha))
    except AppError:
        pass
    spec = CATALOG[response]
    return {"result": {**res, "response": response, "response_label": spec.label, "season": season, "rain_season": rain_season,
                       "unit": spec.unit, "rain_unit": CATALOG["precip"].unit},
            "meta": meta_of(rec_r, aggregation=season, rainfall_dataset=meta_of(rec_p)["dataset"],
                            method="OLS response~rainfall; residual Mann-Kendall/Hamed-Rao/Sen; sensitivity S1-S5")}


def _monthly_check(region, response, source, start, end, alpha) -> dict:
    y, _ = monthly(region, response, source, start, end)
    p, _ = monthly(region, "precip", source, start, end)
    ya = TS.monthly_anomaly(y)
    pa = TS.monthly_anomaly(TS.cumulative_lag(p, 3).dropna())
    d = TS.align(ya, pa)
    if len(d) < 36:
        raise AppError("insufficient_data", "Too few months for monthly check", 422)
    f = S.ols(d["a"].values, {"rain_3mo_anomaly": d["b"].values}, alpha)
    t = (d.index.year + (d.index.month - 1) / 12).values
    tr = S.trend_report(np.array(f["residuals"]), t, alpha)
    pick = tr[tr["recommended"]]
    return {"name": "S5: monthly deseasonalised anomaly ~ 3-month cumulative rain anomaly", "n": f["n"],
            "direction": pick["direction"], "mk_p": tr["mk"]["p"], "hr_p": tr["hr"]["p"], "sen_slope": tr["mk"]["slope"],
            "r2": f["r2"], "slope_unit": "per year"}


# ----------------------------------------------------------------------- sensor / index robustness checks
# Research brief s.7 'Checks that would strengthen the result': repeat the NDVI series with the Aqua satellite's product
# (MYD13Q1) and with EVI. Each series is run through exactly the same tests as the headline NDVI.
VI_CHECKS = [("ndvi", "Terra NDVI (MOD13Q1)", "headline series"),
             ("ndvi_aqua", "Aqua NDVI (MYD13Q1)", "second satellite"),
             ("evi", "Terra EVI (MOD13Q1)", "second vegetation index")]
CHECK_SEASONS = [("monsoon", "monsoon", "Monsoon (Jun-Sep)", "same monsoon's rainfall"),
                 ("summer", "prev_monsoon", "Dry season (Mar-May)", "previous monsoon's rainfall")]


def _year_term(res: dict) -> dict | None:
    return next(({"coef": s["year_coef_per_year"], "p": s["ols_p"], "hac_p": s["hac_p"]} for s in res["sensitivity"]
                 if s["name"].startswith("S3")), None)


def _check_row(region, source, key, season, rain_season, y0, y1, alpha) -> dict:
    raw = trend_payload(region, key, source, season, y0, y1, alpha)
    adj = rainfall_adjusted_payload(region, source, key, season, y0, y1, alpha, rain_season)["result"]
    t, rt = raw["result"]["hr"], adj["residual_trend"]["hr"]
    return {"available": True, "synthetic": raw["meta"]["synthetic"], "period": raw["meta"]["period"], "n": t["n"],
            "raw_trend": {"direction": t["direction"], "slope": t["slope"], "p": t["p"], "significant": t["significant"],
                          "ci": [t["slope_ci_low"], t["slope_ci_high"]]},
            "r2_rain": adj["regression"]["r2"],
            "residual_trend": {"direction": rt["direction"], "slope": rt["slope"], "p": rt["p"], "significant": rt["significant"],
                               "ci": [rt["slope_ci_low"], rt["slope_ci_high"]], "n": rt["n"]},
            "year_term": _year_term(adj), "slope_unit": f"{short_unit(key)} per year"}


def _agreement(rows: list[dict], alpha: float) -> dict:
    """Does each check give the same answer as the headline series on the decisive test (trend left after removing rain)?
    'Same answer' = same direction and the same significance call at alpha. Nothing is averaged or forced."""
    head = next((r for r in rows if r["key"] == "ndvi" and r["available"]), None)
    others = [r for r in rows if r["key"] != "ndvi"]
    if head is None:
        return {"status": "unavailable", "text": "The headline NDVI series is not available, so nothing can be compared."}
    h = head["residual_trend"]
    missing = [r["label"] for r in others if not r["available"]]
    tested = [r for r in others if r["available"]]
    agree = [r for r in tested if r["residual_trend"]["direction"] == h["direction"] and r["residual_trend"]["significant"] == h["significant"]]
    differ = [r for r in tested if r not in agree]
    verdict = "significant " + h["direction"] if h["significant"] else "no significant trend"
    parts = []
    if agree:
        parts.append(f"{' and '.join(r['label'] for r in agree)} {'agrees' if len(agree) == 1 else 'agree'} with Terra NDVI after rainfall is removed ({verdict}, alpha = {alpha:g}).")
    for r in differ:
        x = r["residual_trend"]
        parts.append(f"{r['label']} differs: {'significant ' + x['direction'] if x['significant'] else 'no significant trend'} (p = {x['p']:.3g}).")
    if missing:
        parts.append(f"Not yet available: {', '.join(missing)}.")
    status = "unavailable" if not tested else ("agree" if not differ and not missing else ("partial" if not differ else "disagree"))
    return {"status": status, "headline": verdict, "agree": [r["key"] for r in agree], "differ": [r["key"] for r in differ],
            "missing": [r["key"] for r in others if not r["available"]], "text": " ".join(parts)}


def sensor_index_checks_payload(region, source, start=None, end=None, alpha=0.05) -> dict:
    """Terra NDVI vs Aqua NDVI vs Terra EVI, monsoon and dry season, raw trend and rain-removed trend.
    All available series are tested over their COMMON years (Aqua starts mid-2002), so differences come from the
    satellite or the index and not from a different period. Terra-only results over 2001-2024 stay on the main cards."""
    check(region)
    spans, missing = {}, {}
    for key, _, _ in VI_CHECKS:
        try:
            a, _ = annual(region, key, source, "monsoon", start, end)
            spans[key] = (int(a.index.min()), int(a.index.max()))
        except AppError as e:
            missing[key] = e.message
    if "ndvi" not in spans:
        raise no_data("ndvi", region, source)
    y0 = max(s[0] for s in spans.values()); y1 = min(s[1] for s in spans.values())
    seasons = []
    for season, rain_season, slabel, rlabel in CHECK_SEASONS:
        rows = []
        for key, label, role in VI_CHECKS:
            base = {"key": key, "label": label, "role": role, "dataset": CATALOG[key].ee_id}
            if key in missing:
                rows.append({**base, "available": False, "reason": missing[key]}); continue
            try:
                rows.append({**base, **_check_row(region, source, key, season, rain_season, y0, y1, alpha)})
            except AppError as e:
                rows.append({**base, "available": False, "reason": e.message})
        seasons.append({"season": season, "label": slabel, "rain_control": rlabel, "rows": rows, "agreement": _agreement(rows, alpha)})
    # Terra vs Aqua year-to-year agreement on the monsoon means (same years)
    sensor_corr = None
    if "ndvi_aqua" in spans:
        t, _ = annual(region, "ndvi", source, "monsoon", y0, y1)
        q, _ = annual(region, "ndvi_aqua", source, "monsoon", y0, y1)
        d = pd.concat([t.rename("t"), q.rename("q")], axis=1).dropna()
        if len(d) >= 4:
            sensor_corr = {"n": int(len(d)), "pearson_r": _f(np.corrcoef(d["t"], d["q"])[0, 1]),
                           "mean_difference_aqua_minus_terra": _f((d["q"] - d["t"]).mean())}
    synthetic = any(r.get("synthetic") for s in seasons for r in s["rows"])
    return {"result": {"period": f"{y0}-{y1}", "seasons": seasons, "terra_aqua_monsoon": sensor_corr,
                       "method": "Hamed-Rao modified Mann-Kendall + Sen slope on each series; rainfall removed by OLS residuals "
                                 "(dry season: previous monsoon's rainfall); second method: response ~ rainfall + year",
                       "note": "Aqua's record starts 4 Jul 2002, so every series is tested over the years all of them cover."},
            "meta": {"region": region, "source": source, "synthetic": synthetic, "kind": "synthetic" if synthetic else "observed",
                     "period": f"{y0}-{y1}", "alpha": alpha}}


# ----------------------------------------------------------------------- insights
def build_insights(region_id: str, source: str, start=None, end=None) -> dict:
    region = check(region_id)
    findings, notes, used = [], [], []
    syn = False

    def tr(key, agg):
        nonlocal syn
        try:
            r = trend_payload(region_id, key, source, agg, start, end, 0.05)
        except AppError:
            return None
        used.append((key, agg)); syn = syn or r["meta"]["synthetic"]
        return r["result"]

    ndvi_a, ndvi_m = tr("ndvi", "annual"), tr("ndvi", "monsoon")
    rain_a, rain_m = tr("precip", "annual"), tr("precip", "monsoon")
    lst = tr("lst_day", "annual")
    et = tr("et", "annual")
    adj = None
    try:
        adj = rainfall_adjusted_payload(region_id, source, "ndvi", "monsoon", start, end)
        syn = syn or adj["meta"]["synthetic"]
    except AppError as e:
        notes.append(f"Rainfall-adjusted analysis unavailable: {e.message}")

    def pick(t): return t[t["recommended"]]

    if ndvi_a:
        p = pick(ndvi_a)
        findings.append(_finding("ndvi_trend", "Vegetation greenness trend", ndvi_a["interpretation"], p, {
            "researcher": f"Annual-mean NDVI: {p['test']} Z={p['z']:.2f}, p={p['p']:.3g}, Sen slope {p['slope']:+.4g}/yr (n={p['n']}).",
            "authority": f"Satellite greenness has been {_dir(p)} over the study period. This shows a change in greenness, not what is causing it.",
            "student": f"NDVI measures how green the land looks from space. Here it is {_dir(p)} from year to year on average.",
            "community": f"Satellite images suggest the land has been getting {'greener' if p['direction']=='increasing' else 'less green' if p['direction']=='decreasing' else 'about the same'} over the years; scientists still need field checks to know why."}))
    if rain_m or rain_a:
        t = rain_m or rain_a; p = pick(t)
        findings.append(_finding("rain_trend", "Rainfall trend", t["interpretation"], p, {
            "researcher": f"{t['aggregation']} rainfall: {p['direction']} ({p['test']}, p={p['p']:.3g}, slope {p['slope']:+.3g} mm/yr).",
            "authority": f"Satellite-estimated {t['aggregation']} rainfall shows {p['direction']}.",
            "student": "Rainfall changes from year to year; a trend test tells us whether there is a steady rise or fall beyond that natural variation.",
            "community": f"Rain over the years: {p['direction']} according to satellite estimates."}))
    if adj:
        v = adj["result"]["verdict"]
        r2 = adj["result"]["regression"]["r2"]
        text = (f"Monsoon NDVI explained by monsoon rainfall with R²={r2:.2f}. {v['text']}")
        findings.append({"id": "adjusted", "title": "Rainfall-adjusted vegetation trend", "statement": text,
                         "evidence": {"residual_direction": v["residual_direction"], "p": v["residual_p"], "r2": r2,
                                      "sensitivity": f"{v['sensitivity_agreeing']}/{v['sensitivity_total']} agree"},
                         "audiences": {
                             "researcher": text + " Caveats: " + " ".join(adj["result"]["caveats"][:3]),
                             "authority": ("After accounting for rainfall, greenness still shows a trend." if v["residual_direction"] != "no significant trend"
                                           else "After accounting for rainfall, no remaining greenness trend is detectable.")
                             + " The cause (e.g. grazing, invasive species, water management) is not identified by this analysis.",
                             "student": "We first remove the part of greenness that rainfall explains, then test whether anything is left over time. What is left is a clue, not a cause.",
                             "community": "Rain explains part of the changes in greenness. Whether something else is also at work needs ground surveys."},
                         "limitations": adj["result"]["caveats"]})
    if lst:
        p = pick(lst)
        findings.append(_finding("lst_trend", "Daytime land surface temperature", lst["interpretation"] + " This is skin temperature, not air temperature.", p, {
            "researcher": f"LST day annual mean: {p['direction']} (p={p['p']:.3g}, {p['slope']:+.3g} °C/yr).",
            "authority": f"Satellite surface temperature shows {p['direction']}; it is not the same as air temperature.",
            "student": "Land surface temperature is how hot the ground itself is, which differs from the air temperature weather stations report.",
            "community": "Ground surface heat measured from space has " + ("not changed clearly." if not p["significant"] else f"been {p['direction']}.")}))
    if et:
        p = pick(et)
        findings.append(_finding("et_trend", "Evapotranspiration", et["interpretation"] + " MOD16 is a model product; do not infer groundwater change from it.", p, {
            "researcher": f"Annual ET: {p['direction']} (p={p['p']:.3g}, {p['slope']:+.3g} mm/yr).",
            "authority": f"Modelled evapotranspiration shows {p['direction']}. This alone does not indicate groundwater decline.",
            "student": "Evapotranspiration is water leaving the land through evaporation and plants. Here it comes from a model fed with satellite data.",
            "community": "Modelled water loss to the air and plants: " + p["direction"] + "."}))
    if not findings:
        return {"findings": [], "notes": notes + ["No processed series available for this region/source."], "synthetic": False,
                "region": region["name"], "datasets_used": [], "question": _question(region)}
    return {"question": _question(region), "region": region["name"], "synthetic": syn,
            "synthetic_warning": ("These findings were computed from SYNTHETIC sample data and have no scientific meaning." if syn else None),
            "findings": findings, "notes": notes, "datasets_used": [f"{k} ({a})" for k, a in used],
            "methodology": "Annual/seasonal aggregation of monthly series; Mann-Kendall and Hamed-Rao tests, Sen slope; "
                           "OLS rainfall adjustment with residual trend tests and sensitivity analyses (see Methodology)."}


def _question(region) -> str:
    return (f"Has vegetation greenness in {region['name']} changed during {region['study_period']['start']}-"
            f"{region['study_period']['end']}, and is any change explained by rainfall?")


def _dir(p):
    return "without a statistically significant trend" if p["direction"] == "no significant trend" else p["direction"]


def _finding(fid, title, statement, p, aud):
    return {"id": fid, "title": title, "statement": statement,
            "evidence": {"test": p["test"], "z": p["z"], "p": p["p"], "slope": p["slope"], "n": p["n"], "direction": p["direction"]},
            "audiences": aud, "limitations": []}



# ----------------------------------------------------------------------- handover reproduction & data quality
def handover_payload(region: str, source: str, start=None, end=None) -> dict:
    """Run the handover's exact protocol on stored data and compare with its reported numbers."""
    from .science import handover as H
    check(region)
    ndvi_m, rec_n = monthly(region, "ndvi", source, start, end)
    rain_m, rec_p = monthly(region, "precip", source, start, end)
    df = H.handover_annual(ndvi_m, rain_m)
    try:
        colab = H.colab_protocol(df)
    except Exception as e:      # too few years etc.: report, do not fake
        raise AppError("insufficient_data", f"Cannot run the handover protocol: {type(e).__name__}: {e}", 422)
    water, notes, water_alt = None, [], None
    rain_mon = df["rain_monsoon"]
    wt = store.latest_raw(region, "handover_water_table") if source == "processed" else None
    try:
        et_a, _ = annual(region, "et", source, "annual", start, end)
        sm_a, _ = annual(region, "sm_root", source, "annual", start, end)
        water_alt = H.water_protocol(pd.DataFrame({"et_annual_mm": et_a, "sm_root_annual": sm_a}), rain_mon)     # from the stored monthly series
    except AppError as e:
        notes.append(f"Series-derived water analysis unavailable: {e.message}")
    if wt:
        t = pd.DataFrame(wt["rows"]).set_index("year")
        water = H.water_protocol(t[["et_annual_mm", "sm_root_annual"]], rain_mon)
        notes.append("ET and soil-moisture rows use the handover's own annual definitions (pixel-wise sum of ET composites; mean of all GLDAS images), retrieved directly "
                     f"from Earth Engine on {wt['provenance'].get('retrieval_date')}. The same analysis on the platform's monthly-derived series is shown as a sensitivity.")
    else:
        water = water_alt
        if water:
            notes.append("ET/soil-moisture rows are derived from the monthly series; run the handover_water_table artifact for the handover's exact definitions.")
    raw = store.latest_raw(region, "ndvi_annual_image_mean") if source == "processed" else None
    if raw:
        yr_means = {int(r["year"]): float(r["value"]) for r in raw["rows"] if r.get("value") is not None}
        notes.append("Annual mean NDVI rows use the exact handover quantity (pixel-wise mean of all images per year) retrieved directly from Earth Engine on "
                     f"{raw['provenance'].get('retrieval_date')}.")
    else:
        yr_means = {}
        mm = ndvi_m.dropna()
        for y, g in mm.groupby(mm.index.year):
            if len(g) >= 11:
                yr_means[int(y)] = float(g.mean())
        notes.append("Annual mean NDVI rows are APPROXIMATED by the mean of monthly means, which weights pixels differently from the handover's pixel-wise image mean; "
                     "run `python -m app.cli extract` to retrieve the exact quantity.")
    rows = H.compare_all(colab, water, yr_means)
    counts = {k: sum(1 for r in rows if r["status"] == k) for k in ("reproduced", "consistent", "not reproduced", "not available")}
    ref = H.load_reference()
    return {"result": {"rows": rows, "counts": counts, "colab": colab, "water": water, "water_series_derived": water_alt if wt else None,
                       "annual": {"years": [int(i) for i in df.index], "ndvi_monsoon": df["ndvi_monsoon"].tolist(),
                                  "rain_monsoon": df["rain_monsoon"].tolist(), "n_months": df["n_months"].tolist()},
                       "engine_cross_check": H.engine_cross_check(df), "protocol_differences": H.PROTOCOL_DIFFERENCES,
                       "reference_source": ref["source"], "reference_geometry": ref["geometry"], "notes": notes + [
                           "Status rules: reproduced = same direction, same significance at 0.05, p and slope close (slope within 10%); "
                           "consistent = same direction and significance but p or slope differ; not reproduced otherwise. Results are never adjusted to match.",
                           "Differences can arise from geometry, QA filtering, month assignment, missing months, product reprocessing since the handover date, or rounding of the reported figures."]},
            "meta": meta_of(rec_n, aggregation="handover monsoon (Jun-Sep)", rainfall_dataset=meta_of(rec_p)["dataset"],
                            method="Hamed-Rao (pymannkendall) + Sen slope + OLS residuals, as in the handover Colab scripts")}


PLAUSIBLE = {  # (min, max) for monthly values; used only to flag possible unit/conversion errors
    "ndvi": (-0.2, 1.0), "ndvi_qa": (-0.2, 1.0), "ndvi_landsat": (-0.2, 1.0), "precip": (0, 1500), "lst_day": (-20, 80), "lst_night": (-30, 50),
    "et": (0, 300), "sm_surface": (0, 150), "sm_root": (0, 1000), "water_extent": (0, 1e6), "groundwater": (0, 500),
    "ndvi_nowater": (-0.2, 1.0), "water_extent_mndwi": (0, 1e6), "salinity_index": (0, 1.0),
    "grace_tws": (-100, 100), **{k: (0, 100) for k in LANDCOVER}}


def quality_report(region: str, key: str, source: str) -> dict:
    rec = load(region, key, source)
    s = TS.to_series(rec["dates"], rec["values"])
    prov = rec["provenance"]
    per = prov.get("processing_period", "")
    try:
        y0, y1 = (int(x) for x in per.split("-")[:2])
    except ValueError:
        y0, y1 = int(s.index.year.min()), int(s.index.year.max())
    expected = pd.date_range(f"{y0}-01-01", f"{y1}-12-01", freq="MS")
    valid = s.dropna()
    missing = [d.strftime("%Y-%m") for d in expected if d not in valid.index]
    by_year = {int(y): int(c) for y, c in valid.groupby(valid.index.year).count().items()}
    lo, hi = PLAUSIBLE.get(key, (-np.inf, np.inf))
    out_of_range = valid[(valid < lo) | (valid > hi)]
    flags = []
    if len(out_of_range):
        flags.append(f"{len(out_of_range)} value(s) outside the plausible monthly range [{lo}, {hi}]: check units/scale factors.")
    if key == "precip":
        try:
            ann = TS.seasonal_aggregate(s, "annual", "sum").dropna()
            if len(ann) and not (50 <= ann.mean() <= 2000):
                flags.append(f"Mean annual rainfall {ann.mean():.0f} mm is outside 50-2000 mm: possible unit/conversion error (expect mm/hr x 24 x days).")
        except Exception:
            pass
    return {"result": {"key": key, "expected_months": len(expected), "valid_months": int(len(valid)), "missing_months": len(missing),
                       "missing_list": missing[:200], "completeness_pct": round(100 * len(valid) / max(len(expected), 1), 1),
                       "valid_by_year": by_year, "stats": {"min": _f(valid.min()), "max": _f(valid.max()), "mean": _f(valid.mean()), "sd": _f(valid.std())},
                       "plausible_range": [lo, hi], "out_of_range": int(len(out_of_range)), "flags": flags,
                       "raw_files": store.list_raw(region), "geometry": prov.get("geometry"),
                       "retrieval_date": prov.get("retrieval_date"), "ee_id": prov.get("ee_id"), "unit": prov.get("unit")},
            "meta": meta_of(rec)}
