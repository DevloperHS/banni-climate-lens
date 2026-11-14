"""Integrated multi-variable comparison.

Distinguishes three different questions, reported separately:
  * ASSOCIATION  - correlation matrices (Pearson/Spearman, BH-adjusted p), partial correlations
  * PREDICTION   - leave-one-out cross-validated R2 (does the model predict held-out years?)
  * CAUSATION    - never inferred; every output states what the analysis cannot show.
"""
from __future__ import annotations
import itertools
import numpy as np
import pandas as pd
from scipy import stats as sps
from statsmodels.stats.outliers_influence import variance_inflation_factor
import statsmodels.api as sm

from . import stats as S

MIN_YEARS = 8


def _detrend(x: np.ndarray, t: np.ndarray) -> np.ndarray:
    return x - np.polyval(np.polyfit(t, x, 1), t)


def loo_r2(y: np.ndarray, X: np.ndarray) -> dict:
    """Leave-one-out cross-validated R2 via the PRESS statistic (exact for OLS)."""
    Xc = sm.add_constant(X, has_constant="add")
    hat = Xc @ np.linalg.pinv(Xc.T @ Xc) @ Xc.T
    fit = sm.OLS(y, Xc).fit()
    e = fit.resid / (1 - np.diag(hat))
    press = float(np.sum(e ** 2)); sst = float(np.sum((y - y.mean()) ** 2))
    return {"r2_in_sample": float(fit.rsquared), "r2_loo_cv": float(1 - press / sst), "press": press}


def partial_correlation(df: pd.DataFrame, a: str, b: str, controls: list[str]) -> dict:
    """Correlation of a and b after regressing both on `controls`."""
    if not controls:
        r, p = sps.pearsonr(df[a], df[b])
        return {"r": float(r), "p": float(p), "n": int(len(df)), "controls": []}
    Z = sm.add_constant(df[controls].values)
    ra = sm.OLS(df[a].values, Z).fit().resid
    rb = sm.OLS(df[b].values, Z).fit().resid
    r, _ = sps.pearsonr(ra, rb)
    n, k = len(df), len(controls)
    dof = n - 2 - k
    t = r * np.sqrt(dof / max(1e-12, 1 - r * r)) if dof > 0 else np.nan
    p = float(2 * sps.t.sf(abs(t), dof)) if dof > 0 else None
    return {"r": float(r), "p": p, "n": int(n), "controls": controls}


def compare(df: pd.DataFrame, response: str | None = None, detrend: bool = False, alpha: float = 0.05) -> dict:
    """df: year-indexed annual aggregates, one column per variable (rows with any NaN are dropped)."""
    d = df.dropna()
    n, vars_ = len(d), list(d.columns)
    if len(vars_) < 2:
        raise ValueError("need at least two variables")
    if n < MIN_YEARS:
        raise ValueError(f"only {n} years have all variables (need >= {MIN_YEARS})")
    t = d.index.values.astype(float)
    work = d.copy()
    if detrend:
        for c in vars_:
            work[c] = _detrend(work[c].values, t)
    pairs = list(itertools.combinations(vars_, 2))
    P = pd.DataFrame(np.eye(len(vars_)), index=vars_, columns=vars_)
    Pp = pd.DataFrame(np.zeros((len(vars_),) * 2), index=vars_, columns=vars_)
    Sm = P.copy(); Sp = Pp.copy()
    rows = []
    for a, b in pairs:
        r, p = sps.pearsonr(work[a], work[b]); rho, sp = sps.spearmanr(work[a], work[b])
        P.loc[a, b] = P.loc[b, a] = r; Pp.loc[a, b] = Pp.loc[b, a] = p
        Sm.loc[a, b] = Sm.loc[b, a] = rho; Sp.loc[a, b] = Sp.loc[b, a] = sp
        rows.append({"a": a, "b": b, "pearson_r": float(r), "pearson_p": float(p), "spearman_rho": float(rho), "spearman_p": float(sp)})
    rej, adj = S.benjamini_hochberg(np.array([r["pearson_p"] for r in rows]), alpha)
    for r, rj, ad in zip(rows, rej, adj):
        r["pearson_p_bh"] = float(ad); r["significant_bh"] = bool(rj)
    z = (d - d.mean()) / d.std(ddof=1)
    flags = []
    for yr, row in z.iterrows():
        hot = [c for c in vars_ if abs(row[c]) > 2]
        if len(hot) >= 1:
            flags.append({"year": int(yr), "variables": hot, "z": {c: float(row[c]) for c in hot}, "coincident": len(hot) >= 2})
    out = {"n": int(n), "years": [int(i) for i in d.index], "variables": vars_, "detrended": detrend,
           "pearson": P.round(6).values.tolist(), "pearson_p": Pp.round(8).values.tolist(), "spearman": Sm.round(6).values.tolist(),
           "pairs": rows, "zscores": {c: z[c].tolist() for c in vars_}, "anomaly_years": flags,
           "association_note": "Correlation describes co-variation over these years. It does not show that one variable drives another; shared trends, lags and omitted variables produce correlations. p-values are BH-adjusted across all pairs."}
    if response:
        if response not in vars_:
            raise ValueError("response must be one of the variables")
        preds = [c for c in vars_ if c != response]
        k = len(preds)
        if k > max(1, n // 5):
            preds = preds[: max(1, n // 5)]
            out["predictors_truncated_to"] = preds
        X = work[preds].values; y = work[response].values
        fit = S.ols(y, {p: work[p].values for p in preds}, alpha)
        out["regression"] = {"response": response, "predictors": preds, **{k2: fit[k2] for k2 in ("n", "r2", "adj_r2", "f_p", "coefficients", "diagnostics", "residuals")}}
        if len(preds) >= 2:
            Xc = sm.add_constant(X)
            out["regression"]["vif"] = {p: float(variance_inflation_factor(Xc, i + 1)) for i, p in enumerate(preds)}
            out["regression"]["collinearity_warning"] = any(v > 5 for v in out["regression"]["vif"].values())
        out["prediction"] = loo_r2(y, X)
        out["prediction"]["note"] = ("Leave-one-out R2 measures prediction of held-out years. A large gap versus in-sample R2 signals overfitting; "
                                     "good prediction is still not evidence of causation.")
        out["partial_correlations"] = [{"variable": p, **partial_correlation(work, response, p, [c for c in preds if c != p])} for p in preds]
        lag = []
        yv = work[response].values
        for p in preds:
            for L in (-2, -1, 0, 1, 2):
                a_, b_ = (yv[max(L, 0):n + min(L, 0)], work[p].values[max(-L, 0):n - max(L, 0)]) if L else (yv, work[p].values)
                if len(a_) >= 6:
                    r, pv = sps.pearsonr(a_, b_)
                    lag.append({"variable": p, "lag_years": L, "r": float(r), "p": float(pv), "n": int(len(a_))})
        out["lagged"] = lag
        out["lag_note"] = "lag L>0: predictor leads the response by L years. Many lags are examined, so single significant lags should not be over-interpreted."
        out["causation_note"] = "This analysis cannot establish causation. Direction of effect, confounding and common drivers are not tested."
    return out
