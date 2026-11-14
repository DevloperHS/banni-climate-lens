"""Statistical engine: trend tests, regression, diagnostics, FDR, event studies.

All functions are pure (NumPy/SciPy/statsmodels) and independent of the web layer and of
Earth Engine, so they can be validated against known data.
"""
from __future__ import annotations
import numpy as np
from scipy import stats as sps
import statsmodels.api as sm
from statsmodels.stats.diagnostic import acorr_ljungbox, het_breuschpagan
from statsmodels.stats.stattools import durbin_watson


def _clean(x, t=None):
    x = np.asarray(x, float)
    t = np.arange(len(x), dtype=float) if t is None else np.asarray(t, float)
    m = np.isfinite(x) & np.isfinite(t)
    return x[m], t[m]


def _acf(x: np.ndarray, nlags: int) -> np.ndarray:
    x = x - x.mean()
    d = np.sum(x * x)
    if d == 0:
        return np.zeros(nlags + 1)
    return np.array([np.sum(x[: len(x) - k] * x[k:]) / d for k in range(nlags + 1)])


def sen_slope(x, t=None, alpha: float = 0.05, var_s: float | None = None) -> dict:
    """Theil-Sen slope using actual time values `t` (handles gaps), median intercept, and a
    Gilbert (1987) / Sen (1968) confidence interval for the slope."""
    x, t = _clean(x, t)
    n = len(x)
    i, j = np.triu_indices(n, 1)
    dt = t[j] - t[i]
    ok = dt != 0
    slopes = np.sort((x[j] - x[i])[ok] / dt[ok])
    N = len(slopes)
    slope = float(np.median(slopes))
    intercept = float(np.median(x - slope * t))
    if var_s is None:
        var_s = _mk_var(x)
    c = sps.norm.ppf(1 - alpha / 2) * np.sqrt(var_s)
    lo_i = int(np.floor((N - c) / 2)) - 1      # M1-th ordered slope, 0-based
    hi_i = int(np.ceil((N + c) / 2))           # (M2+1)-th ordered slope, 0-based == index M2
    lo = float(slopes[max(lo_i, 0)]) if N else np.nan
    hi = float(slopes[min(hi_i, N - 1)]) if N else np.nan
    return {"slope": slope, "intercept": intercept, "ci_low": lo, "ci_high": hi}


def _mk_var(x: np.ndarray) -> float:
    n = len(x)
    _, counts = np.unique(x, return_counts=True)
    ties = np.sum(counts * (counts - 1) * (2 * counts + 5))
    return (n * (n - 1) * (2 * n + 5) - ties) / 18.0


def mann_kendall(x, t=None, alpha: float = 0.05, hamed_rao: bool = False) -> dict:
    """Mann-Kendall trend test (tie-corrected), optionally with the Hamed & Rao (1998)
    variance correction for serial correlation.

    The correction follows Hamed & Rao: detrend with Sen's slope, rank the residuals, take the
    autocorrelation of the ranks at lags 1..n-1, and keep only lags outside +/- z(1-a/2)/sqrt(n).
    Sen's slope is computed against actual time `t`; the S statistic uses ordering only.
    """
    x, t = _clean(x, t)
    n = len(x)
    if n < 4:
        raise ValueError("Mann-Kendall needs at least 4 valid observations")
    order = np.argsort(t, kind="stable")
    x, t = x[order], t[order]
    s = float(np.sign(x[None, :] - x[:, None])[np.triu_indices(n, 1)].sum())
    var_s = _mk_var(x)
    sen = sen_slope(x, t, alpha, var_s=var_s)
    correction = 1.0
    if hamed_rao:
        # Sen slope is per unit of t; convert to per-index for (near) equally spaced data
        step = np.median(np.diff(t)) if n > 1 else 1.0
        detr = x - sen["slope"] * step * np.arange(1, n + 1)
        r = sps.rankdata(detr)
        rho = _acf(r, n - 1)
        bound = sps.norm.ppf(1 - alpha / 2) / np.sqrt(n)
        sni = sum((n - k) * (n - k - 1) * (n - k - 2) * rho[k] for k in range(1, n) if abs(rho[k]) > bound)
        correction = 1 + 2.0 / (n * (n - 1) * (n - 2)) * sni
        if not np.isfinite(correction) or correction <= 0:
            correction = 1.0
    var_c = var_s * correction
    z = 0.0 if s == 0 else (s - np.sign(s)) / np.sqrt(var_c)
    p = float(2 * (1 - sps.norm.cdf(abs(z))))
    sig = p < alpha
    direction = "no significant trend" if not sig else ("increasing" if z > 0 else "decreasing")
    return {
        "test": "Hamed-Rao modified Mann-Kendall" if hamed_rao else "Mann-Kendall",
        "n": n, "s": s, "var_s": float(var_c), "variance_correction": float(correction),
        "tau": float(s / (n * (n - 1) / 2)), "z": float(z), "p": p, "alpha": alpha,
        "significant": bool(sig), "direction": direction,
        "slope": sen["slope"], "slope_ci_low": sen["ci_low"], "slope_ci_high": sen["ci_high"],
        "intercept": sen["intercept"],
        "slope_unit": "per unit of t (years for annual series)",
    }


def trend_report(x, t=None, alpha: float = 0.05) -> dict:
    """Both tests side by side + lag-1 autocorrelation.

    `recommended` is deliberately CONSERVATIVE. Hamed-Rao rescales Var(S) by a factor estimated from the rank
    autocorrelation of ~n points. A factor > 1 (positive autocorrelation) widens uncertainty and is the case the
    correction exists for. A factor < 1 (driven by negative autocorrelation at some lags, easily produced by noise when
    n ~ 24) would make the test MORE liberal than plain Mann-Kendall, so it is not used as the headline and a warning is
    attached. (Observed on real Banni ET: factor 0.26, MK p=0.027 vs Hamed-Rao p=1e-5.)"""
    xs, ts = _clean(x, t)
    out = {"mk": mann_kendall(xs, ts, alpha), "hr": mann_kendall(xs, ts, alpha, hamed_rao=True)}
    out["lag1_autocorr"] = float(_acf(xs, 1)[1]) if len(xs) > 3 else None
    f = out["hr"]["variance_correction"]
    ac = out["lag1_autocorr"]
    out["recommended"] = "hr" if (f > 1.0 or (ac is not None and abs(ac) > 0.3 and f >= 1.0)) else "mk"
    out["warnings"] = []
    if f < 0.8:
        out["warnings"].append(f"Hamed-Rao variance correction is {f:.2f} (< 1): it would make the result more significant than plain Mann-Kendall "
                               f"(p {out['hr']['p']:.2g} vs {out['mk']['p']:.2g}). With only {len(xs)} points this factor is unstable, so the Mann-Kendall result is "
                               "reported as primary. Treat the corrected p-value with caution.")
    if out["hr"]["significant"] != out["mk"]["significant"]:
        out["warnings"].append("Mann-Kendall and Hamed-Rao disagree about significance at the chosen alpha; the conclusion is fragile.")
    return out


# ------------------------------------------------------------------ regression
def ols(y, X: dict[str, np.ndarray], alpha: float = 0.05, hac_lags: int | None = None) -> dict:
    """OLS with intercept. Returns coefficients (CI, p), fit stats, residuals, diagnostics and
    Newey-West (HAC) standard errors as a robustness check against autocorrelation."""
    y = np.asarray(y, float)
    names = list(X)
    M = np.column_stack([np.asarray(X[k], float) for k in names])
    ok = np.isfinite(y) & np.all(np.isfinite(M), axis=1)
    y, M = y[ok], M[ok]
    n, k = len(y), M.shape[1]
    if n < k + 3:
        raise ValueError(f"Too few observations ({n}) for {k} predictor(s)")
    Xc = sm.add_constant(M, has_constant="add")
    fit = sm.OLS(y, Xc).fit()
    ci = fit.conf_int(alpha)
    L = hac_lags if hac_lags is not None else max(1, int(np.floor(4 * (n / 100) ** (2 / 9))))
    hac = sm.OLS(y, Xc).fit(cov_type="HAC", cov_kwds={"maxlags": L})
    hci = hac.conf_int(alpha)
    labels = ["intercept"] + names
    coefs = [{"name": labels[i], "coef": float(fit.params[i]), "se": float(fit.bse[i]),
              "t": float(fit.tvalues[i]), "p": float(fit.pvalues[i]),
              "ci_low": float(ci[i][0]), "ci_high": float(ci[i][1]),
              "hac_se": float(hac.bse[i]), "hac_p": float(hac.pvalues[i]),
              "hac_ci_low": float(hci[i][0]), "hac_ci_high": float(hci[i][1])} for i in range(len(labels))]
    resid = fit.resid
    diag = {"durbin_watson": float(durbin_watson(resid))}
    try:
        lb = acorr_ljungbox(resid, lags=[min(10, max(1, n // 5))], return_df=True)
        diag["ljung_box_p"] = float(lb["lb_pvalue"].iloc[0])
    except Exception:
        diag["ljung_box_p"] = None
    diag["shapiro_p"] = float(sps.shapiro(resid).pvalue) if 3 <= n <= 5000 else None
    try:
        diag["breusch_pagan_p"] = float(het_breuschpagan(resid, Xc)[1])
    except Exception:
        diag["breusch_pagan_p"] = None
    infl = fit.get_influence()
    cooks = infl.cooks_distance[0]
    diag["cooks_threshold"] = float(4 / n)
    diag["outlier_indices"] = [int(i) for i in np.where(cooks > 4 / n)[0]]
    return {
        "n": int(n), "r2": float(fit.rsquared), "adj_r2": float(fit.rsquared_adj),
        "f_p": float(fit.f_pvalue), "coefficients": coefs, "diagnostics": diag,
        "fitted": fit.fittedvalues.tolist(), "residuals": resid.tolist(), "valid_mask": ok.tolist(),
    }


def correlation(a, b) -> dict:
    a, b = np.asarray(a, float), np.asarray(b, float)
    m = np.isfinite(a) & np.isfinite(b)
    a, b = a[m], b[m]
    if len(a) < 4:
        raise ValueError("Need at least 4 paired observations")
    pr, pp = sps.pearsonr(a, b)
    sr, sp = sps.spearmanr(a, b)
    # Fisher-z 95% CI for Pearson r
    z = np.arctanh(pr); se = 1 / np.sqrt(len(a) - 3)
    return {"n": int(len(a)), "pearson_r": float(pr), "pearson_p": float(pp),
            "pearson_ci_low": float(np.tanh(z - 1.96 * se)), "pearson_ci_high": float(np.tanh(z + 1.96 * se)),
            "spearman_rho": float(sr), "spearman_p": float(sp),
            "note": "Correlation does not establish causation."}


# ------------------------------------------------------------------ multiple testing
def benjamini_hochberg(p: np.ndarray, q: float = 0.05) -> tuple[np.ndarray, np.ndarray]:
    """BH step-up. Returns (reject mask, adjusted p-values/q-values). NaNs are ignored and
    returned as NaN/False."""
    p = np.asarray(p, float)
    valid = np.isfinite(p)
    pv = p[valid]
    m = len(pv)
    adj = np.full(p.shape, np.nan)
    rej = np.zeros(p.shape, bool)
    if m == 0:
        return rej, adj
    order = np.argsort(pv)
    ranked = pv[order] * m / (np.arange(m) + 1)
    ranked = np.minimum.accumulate(ranked[::-1])[::-1]
    a = np.empty(m)
    a[order] = np.minimum(ranked, 1.0)
    adj[valid] = a
    rej[valid] = a <= q
    return rej, adj


# ------------------------------------------------------------------ rainfall-adjusted analysis
def _resid_trend(resid: np.ndarray, years: np.ndarray) -> dict:
    return trend_report(resid, years)


def rainfall_adjusted(years, ndvi, rain, rain_prev=None, alpha: float = 0.05) -> dict:
    """NDVI ~ Rainfall, then test the residuals for a trend; with sensitivity analyses.

    Primary model:   NDVI_y = b0 + b1 * Rain_y + e_y         (same-period totals, annual resolution)
    Residual trend:  Mann-Kendall / Hamed-Rao + Sen slope on e_y.
    Sensitivities:
      S1 add previous-year rainfall (lagged water availability)
      S2 Theil-Sen robust line instead of OLS
      S3 joint model NDVI ~ Rain + Year with Newey-West (HAC) errors
      S4 drop influential points (Cook's D > 4/n) and refit
    A positive residual trend means "greener than rainfall alone predicts" - it is NOT evidence
    of a specific cause or species. Verdict text is deliberately conservative.
    """
    years = np.asarray(years, float); ndvi = np.asarray(ndvi, float); rain = np.asarray(rain, float)
    m = np.isfinite(years) & np.isfinite(ndvi) & np.isfinite(rain)
    yr, nd, rn = years[m], ndvi[m], rain[m]
    n = len(yr)
    if n < 8:
        raise ValueError(f"Need >= 8 paired years for a rainfall-adjusted analysis (have {n})")

    main = ols(nd, {"rainfall": rn}, alpha)
    resid = np.asarray(main["residuals"])
    res = {
        "model": "NDVI ~ Rainfall (OLS)", "n": n, "years": yr.astype(int).tolist(),
        "ndvi": nd.tolist(), "rainfall": rn.tolist(),
        "ndvi_trend": trend_report(nd, yr, alpha), "rainfall_trend": trend_report(rn, yr, alpha),
        "regression": main, "predicted": main["fitted"], "residuals": resid.tolist(),
        "residual_trend": _resid_trend(resid, yr),
    }
    sens = []

    def add(name, resid_s, yrs, extra=None):
        t = _resid_trend(np.asarray(resid_s), yrs)
        sens.append({"name": name, "n": int(len(resid_s)), "direction": t["hr"]["direction"] if t["recommended"] == "hr" else t["mk"]["direction"],
                     "mk_p": t["mk"]["p"], "hr_p": t["hr"]["p"], "sen_slope": t["mk"]["slope"], **(extra or {})})

    # S1 lagged rainfall
    if rain_prev is not None:
        rp = np.asarray(rain_prev, float)[m]
        ok = np.isfinite(rp)
        if ok.sum() >= 8:
            f = ols(nd[ok], {"rainfall": rn[ok], "rainfall_prev_year": rp[ok]}, alpha)
            add("S1: + previous-year rainfall (OLS)", f["residuals"], yr[ok], {"r2": f["r2"]})
    # S2 Theil-Sen robust
    ts = sps.theilslopes(nd, rn)
    add("S2: Theil-Sen robust NDVI~Rain", nd - (ts[1] + ts[0] * rn), yr, {"robust_slope": float(ts[0])})
    # S3 joint model with year
    joint = ols(nd, {"rainfall": rn, "year": yr}, alpha)
    yc = next(c for c in joint["coefficients"] if c["name"] == "year")
    sens.append({"name": "S3: NDVI ~ Rainfall + Year (HAC errors)", "n": joint["n"],
                 "year_coef_per_year": yc["coef"], "ols_p": yc["p"], "hac_p": yc["hac_p"],
                 "hac_ci_low": yc["hac_ci_low"], "hac_ci_high": yc["hac_ci_high"],
                 "direction": ("no significant trend" if yc["hac_p"] >= alpha else ("increasing" if yc["coef"] > 0 else "decreasing"))})
    # S4 drop influential
    out_idx = main["diagnostics"]["outlier_indices"]
    if out_idx and n - len(out_idx) >= 8:
        keep = np.setdiff1d(np.arange(n), out_idx)
        f = ols(nd[keep], {"rainfall": rn[keep]}, alpha)
        add(f"S4: influential years removed ({', '.join(str(int(yr[i])) for i in out_idx)})", f["residuals"], yr[keep])
    res["sensitivity"] = sens

    # --- caveats derived from diagnostics (not boilerplate)
    d = main["diagnostics"]; caveats = []
    if d["durbin_watson"] < 1.5 or d["durbin_watson"] > 2.5:
        caveats.append(f"Residual autocorrelation is suggested (Durbin-Watson={d['durbin_watson']:.2f}); "
                       "OLS p-values may be optimistic - prefer the Hamed-Rao and HAC results.")
    if d.get("ljung_box_p") is not None and d["ljung_box_p"] < alpha:
        caveats.append(f"Ljung-Box rejects white-noise residuals (p={d['ljung_box_p']:.3f}).")
    if d.get("shapiro_p") is not None and d["shapiro_p"] < alpha:
        caveats.append(f"Residuals depart from normality (Shapiro p={d['shapiro_p']:.3f}); rely on the rank-based tests.")
    if d.get("breusch_pagan_p") is not None and d["breusch_pagan_p"] < alpha:
        caveats.append(f"Heteroscedasticity detected (Breusch-Pagan p={d['breusch_pagan_p']:.3f}).")
    if out_idx:
        caveats.append(f"{len(out_idx)} influential year(s) (Cook's D > 4/n): " + ", ".join(str(int(yr[i])) for i in out_idx) + ".")
    if main["r2"] < 0.2:
        caveats.append(f"Rainfall explains little of NDVI variance (R2={main['r2']:.2f}); 'rainfall-adjusted' residuals are close to raw NDVI.")
    if res["rainfall_trend"]["mk"]["significant"]:
        caveats.append("Rainfall itself has a significant trend, so NDVI and rainfall trends are not separable by this model alone.")
    caveats.append("Unmodelled drivers (grazing, land management, Prosopis juliflora spread, flooding/salinity, "
                   "temperature, land-cover change) remain confounders; a residual trend cannot identify which.")
    if n < 20:
        caveats.append(f"Only {n} annual observations: tests have limited power.")
    res["caveats"] = caveats

    rt = res["residual_trend"]; pick = rt[rt["recommended"]]
    agree = sum(1 for s in sens if s["direction"] == pick["direction"])
    res["verdict"] = {
        "residual_direction": pick["direction"], "residual_p": pick["p"], "test_used": pick["test"],
        "sensitivity_agreeing": agree, "sensitivity_total": len(sens),
        "text": (f"After removing the rainfall-explained part, the NDVI residuals show: {pick['direction']} "
                 f"({pick['test']}, p={pick['p']:.3g}, Sen slope {pick['slope']:+.4g} NDVI/yr). "
                 f"{agree} of {len(sens)} sensitivity analyses give the same direction. "
                 "This indicates the trend is (or is not) explained by rainfall alone within this simple model; "
                 "it does not identify the cause or the vegetation type."),
    }
    return res


# ------------------------------------------------------------------ event study
def event_study(monthly: "pd.Series", event_ts: "pd.Timestamp", pre_months: int = 3, post_months: int = 3) -> dict:  # noqa: F821
    """Compare the change in deseasonalised anomaly across an event date with the same
    calendar-window change in every other year (a placebo distribution).

    delta_y = mean(anomaly in [event, event+post)) - mean(anomaly in [event-pre, event))
    The event year's delta is ranked against the other years' deltas. This does NOT prove
    causation: other events (e.g. a wet monsoon) in the same year also move the delta.
    """
    import pandas as pd
    anom = monthly - monthly.index.month.map(
        monthly[monthly.index.year != event_ts.year].groupby(monthly[monthly.index.year != event_ts.year].index.month).mean()).values
    anchor_m = event_ts.month

    def delta(year: int):
        t0 = pd.Timestamp(year=year, month=anchor_m, day=1)
        pre = anom[(anom.index >= t0 - pd.DateOffset(months=pre_months)) & (anom.index < t0)]
        post = anom[(anom.index >= t0) & (anom.index < t0 + pd.DateOffset(months=post_months))]
        if len(pre) < max(2, pre_months - 1) or len(post) < max(2, post_months - 1):
            return None
        return float(post.mean() - pre.mean()), float(pre.mean()), float(post.mean())

    ev = delta(event_ts.year)
    if ev is None:
        raise ValueError("Insufficient data around the event date")
    others = {y: delta(y) for y in sorted(set(monthly.index.year)) if y != event_ts.year}
    ref = np.array([v[0] for v in others.values() if v is not None])
    if len(ref) < 5:
        raise ValueError("Too few comparison years for a placebo distribution")
    pct = float(np.mean(ref < ev[0]) * 100)
    z = float((ev[0] - ref.mean()) / ref.std(ddof=1)) if ref.std(ddof=1) > 0 else None
    return {
        "event_year": int(event_ts.year), "pre_months": pre_months, "post_months": post_months,
        "pre_mean_anomaly": ev[1], "post_mean_anomaly": ev[2], "delta": ev[0],
        "reference_years": len(ref), "reference_mean_delta": float(ref.mean()), "reference_sd_delta": float(ref.std(ddof=1)),
        "percentile_in_reference": pct, "z_vs_reference": z,
        "reference": {str(y): (None if v is None else v[0]) for y, v in others.items()},
        "extreme": bool(pct >= 95 or pct <= 5),
        "interpretation": ("The change across the event date is "
                           + ("outside" if (pct >= 95 or pct <= 5) else "within")
                           + f" the range of same-season changes in other years (percentile {pct:.0f}). "
                             "Association only; attribution to the cyclone would additionally need controls for rainfall, "
                             "season timing and land-cover state."),
    }


def event_study_rain_adjusted(y: "pd.Series", rain: "pd.Series", event_ts: "pd.Timestamp", pre_months: int = 3, post_months: int = 3,  # noqa: F821
                              rain_window: int = 3) -> dict:
    """Event study on the part of the response NOT explained by recent rainfall.

    1. Deseasonalise y and the trailing `rain_window`-month rainfall total (climatology excludes the event year).
    2. Fit y_anom ~ rain_anom on NON-event years only (so the event cannot influence the fit).
    3. Run the placebo-year event study on the residual series.
    Compare `raw` and `rain_adjusted`: if the unusual change vanishes after adjustment, rainfall timing (not the
    event itself) is the more parsimonious explanation. Still association, not attribution."""
    import pandas as pd
    ey = event_ts.year
    def anom(s):
        base = s[s.index.year != ey]
        return s - s.index.month.map(base.groupby(base.index.month).mean()).values
    ya = anom(y)
    rr = anom(rain.rolling(rain_window, min_periods=rain_window).sum())
    d = pd.concat([ya.rename("y"), rr.rename("r")], axis=1).dropna()
    fit_d = d[d.index.year != ey]
    if len(fit_d) < 36:
        raise ValueError("too few non-event months to fit the rainfall adjustment")
    X = np.column_stack([np.ones(len(fit_d)), fit_d["r"].values])
    beta, *_ = np.linalg.lstsq(X, fit_d["y"].values, rcond=None)
    pred = beta[0] + beta[1] * d["r"]
    resid = (d["y"] - pred)
    r2 = 1 - np.sum((fit_d["y"].values - X @ beta) ** 2) / np.sum((fit_d["y"].values - fit_d["y"].mean()) ** 2)
    adj = event_study(resid + 1.0, event_ts, pre_months, post_months)
    raw = event_study(y, event_ts, pre_months, post_months)
    return {"raw": raw, "rain_adjusted": adj, "adjustment": {"rain_window_months": rain_window, "slope": float(beta[1]), "intercept": float(beta[0]),
                                                           "r2_non_event_years": float(r2), "n_fit_months": int(len(fit_d))},
            "interpretation": ("Raw change is " + ("unusual" if raw["extreme"] else "not unusual") + f" (percentile {raw['percentile_in_reference']:.0f}); after removing the "
                               f"rainfall-explained part it is " + ("unusual" if adj["extreme"] else "not unusual") + f" (percentile {adj['percentile_in_reference']:.0f}). "
                               "Neither result attributes the change to the cyclone: land-cover state, flooding, grazing and measurement artefacts are not controlled.")}
