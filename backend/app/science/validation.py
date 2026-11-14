"""Validation of indicators against user-supplied FIELD data (ground-truth class labels; measured soil/water EC).

No labels or field measurements ship with this project. Without them every function here refuses to produce an
accuracy claim. With them, they provide honest, small-sample-aware statistics.
"""
from __future__ import annotations
import io
import math
import numpy as np
import pandas as pd
from scipy import stats as sps

MIN_PER_CLASS = 10
MAX_POINTS = 20000


class ValidationError(ValueError):
    pass


def parse_labels_csv(raw: bytes, classes_hint: tuple[str, ...] | None = None) -> tuple[pd.DataFrame, dict]:
    """CSV columns: lat, lon, class [, date, source]. Returns clean frame and a validation report."""
    try:
        df = pd.read_csv(io.BytesIO(raw))
    except Exception as e:
        raise ValidationError(f"unreadable CSV: {e}")
    df.columns = [c.strip().lower() for c in df.columns]
    for c in ("lat", "lon", "class"):
        if c not in df.columns:
            raise ValidationError("CSV needs columns lat, lon, class")
    if len(df) > MAX_POINTS:
        raise ValidationError(f"too many rows (max {MAX_POINTS})")
    n0 = len(df)
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce"); df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
    df["class"] = df["class"].astype(str).str.strip().str.lower()
    bad = df[~(df["lat"].between(-90, 90) & df["lon"].between(-180, 180)) | df["class"].isin(["", "nan"])]
    df = df.drop(bad.index)
    dups = int(df.duplicated(["lat", "lon"]).sum())
    df = df.drop_duplicates(["lat", "lon"])
    counts = df["class"].value_counts().to_dict()
    rep = {"rows_in": int(n0), "rows_valid": int(len(df)), "rejected": int(len(bad)), "duplicates_removed": dups, "class_counts": counts,
           "warnings": [f"class '{k}' has only {v} points (< {MIN_PER_CLASS}); no accuracy statistics will be reported for it" for k, v in counts.items() if v < MIN_PER_CLASS]}
    if len(counts) < 2:
        raise ValidationError("need at least two classes")
    return df.reset_index(drop=True), rep


def indicator_separability(values: np.ndarray, classes: np.ndarray) -> dict:
    """Per-class distribution of an indicator at labelled points and pairwise ROC-AUC (Mann-Whitney). Reports nothing
    for classes with fewer than MIN_PER_CLASS valid points."""
    ok = np.isfinite(values)
    v, c = values[ok], classes[ok]
    out = {"n_valid": int(ok.sum()), "classes": {}, "pairs": [], "caveats": []}
    cls = sorted(set(c))
    for k in cls:
        x = v[c == k]
        out["classes"][k] = {"n": int(len(x)), "mean": float(x.mean()), "sd": float(x.std(ddof=1)) if len(x) > 1 else None,
                             "median": float(np.median(x)), "enough": bool(len(x) >= MIN_PER_CLASS)}
    for i, a in enumerate(cls):
        for b in cls[i + 1:]:
            xa, xb = v[c == a], v[c == b]
            if len(xa) < MIN_PER_CLASS or len(xb) < MIN_PER_CLASS:
                out["pairs"].append({"a": a, "b": b, "auc": None, "reason": f"fewer than {MIN_PER_CLASS} valid points in a class"})
                continue
            u = sps.mannwhitneyu(xa, xb, alternative="two-sided")
            auc_a = float(u.statistic / (len(xa) * len(xb)))          # P(value in a > value in b)
            flip = auc_a < 0.5
            auc = 1 - auc_a if flip else auc_a
            rng = np.random.default_rng(0)
            boots = []
            for _ in range(500):
                ra, rb = rng.choice(xa, len(xa)), rng.choice(xb, len(xb))
                b_ = float(sps.mannwhitneyu(ra, rb).statistic / (len(ra) * len(rb)))
                boots.append(1 - b_ if flip else b_)
            out["pairs"].append({"a": a, "b": b, "auc": auc, "higher_class": b if flip else a, "auc_ci_low": float(np.percentile(boots, 2.5)),
                                 "auc_ci_high": float(np.percentile(boots, 97.5)), "mannwhitney_p": float(u.pvalue), "n_a": int(len(xa)), "n_b": int(len(xb))})
    out["caveats"] = ["AUC measures how well the indicator ranks one class above another at these points only.",
                      "Points must be an independent random/stratified sample; clustered or convenience samples inflate performance.",
                      "Spatial autocorrelation between nearby points makes the intervals optimistic.",
                      "An indicator that separates classes here is evidence for further work, not a validated species map."]
    return out


def ec_validation(index_values: np.ndarray, ec: np.ndarray) -> dict:
    """Spearman correlation between a spectral salinity proxy and measured EC (dS/m)."""
    ok = np.isfinite(index_values) & np.isfinite(ec)
    n = int(ok.sum())
    if n < MIN_PER_CLASS:
        return {"n": n, "status": "insufficient", "message": f"{n} paired points; at least {MIN_PER_CLASS} needed. The index remains UNVALIDATED."}
    rho, p = sps.spearmanr(index_values[ok], ec[ok])
    z = np.arctanh(np.clip(rho, -0.999999, 0.999999)); se = 1.06 / math.sqrt(max(n - 3, 1))      # Fieller et al. approx for Spearman
    return {"n": n, "status": "computed", "spearman_rho": float(rho), "p": float(p), "ci_low": float(np.tanh(z - 1.96 * se)), "ci_high": float(np.tanh(z + 1.96 * se)),
            "message": ("Index tracks measured EC at these points" if p < 0.05 and rho > 0.3 else "No convincing relationship at these points") +
                       "; local validity applies only to similar soils, dates and depths."}
