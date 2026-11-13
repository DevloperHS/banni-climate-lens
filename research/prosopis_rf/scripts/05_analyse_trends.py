"""Step 5: trend tests on banni_ndvi_by_prosopis_chirps.csv (the table exported by the Code Editor run).

Answers the question in the task brief:
  - Is the monsoon-NDVI trend different in high-Prosopis vs low-Prosopis MODIS pixels?
  - Does it survive removing the rainfall effect, with CHIRPS as an independent rainfall source (not IMERG)?
Protocol = the project's handover protocol: Hamed-Rao modified Mann-Kendall + Sen slope (pymannkendall), rainfall removed
by OLS residuals (statsmodels), second method "NDVI ~ rain + year". Also compares CHIRPS with the platform's IMERG monsoon
totals over the same years.

Run from the repository root:
  .venv\\Scripts\\python research\\prosopis_rf\\scripts\\05_analyse_trends.py [path\\to\\banni_ndvi_by_prosopis_chirps.csv]
Default input: research/prosopis_rf/results/banni_ndvi_by_prosopis_chirps.csv
Writes research/prosopis_rf/results/trend_tests.json and prints a readable table.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pymannkendall as mk
import statsmodels.api as sm

ROOT = Path(__file__).resolve().parents[3]
RES = ROOT / "research" / "prosopis_rf" / "results"
ALPHA = 0.05


def trend(y, years):
    hr = mk.hamed_rao_modification_test(np.asarray(y, float))
    sen = mk.sens_slope(np.asarray(y, float))
    return {"direction": hr.trend if hr.p < ALPHA else "no significant trend", "p": float(hr.p), "z": float(hr.z),
            "sen_slope_per_year": float(sen.slope), "n": int(len(y)), "period": f"{int(min(years))}-{int(max(years))}"}


def rain_removed(y, rain, years):
    X = sm.add_constant(np.asarray(rain, float))
    fit = sm.OLS(np.asarray(y, float), X).fit()
    joint = sm.OLS(np.asarray(y, float), sm.add_constant(np.column_stack([rain, years]).astype(float))).fit()
    return {"r2_rain": float(fit.rsquared), "residual_trend": trend(fit.resid, years),
            "year_term": {"coef_per_year": float(joint.params[2]), "p": float(joint.pvalues[2])}}


def imerg_monsoon():
    """Platform IMERG monsoon (Jun-Sep) totals over the platform rectangle (68.80-69.95 E, 23.20-23.95 N)."""
    rec = json.loads((ROOT / "data" / "processed" / "series" / "banni" / "precip.json").read_text())
    s = pd.Series(rec["values"], index=pd.to_datetime(rec["dates"]))
    m = s[s.index.month.isin([6, 7, 8, 9])]
    g = m.groupby(m.index.year)
    return g.sum()[g.count() == 4]


def main(path):
    df = pd.read_csv(path)
    df = df[[c for c in df.columns if c in ("year", "ndvi_hi_pros", "ndvi_lo_pros", "chirps_monsoon_mm")]].sort_values("year")
    df = df.dropna()
    yrs = df["year"].to_numpy(float)
    gap = df["ndvi_hi_pros"] - df["ndvi_lo_pros"]
    out = {"input": str(Path(path).relative_to(ROOT)) if Path(path).is_relative_to(ROOT) else str(path), "years": [int(y) for y in yrs]}
    out["trend"] = {k: trend(df[k], yrs) for k in ("ndvi_hi_pros", "ndvi_lo_pros", "chirps_monsoon_mm")}
    out["trend"]["gap_hi_minus_lo"] = trend(gap, yrs)
    out["rain_removed_chirps"] = {k: rain_removed(df[k], df["chirps_monsoon_mm"], yrs) for k in ("ndvi_hi_pros", "ndvi_lo_pros")}
    im = imerg_monsoon().reindex(df["year"].astype(int))
    both = pd.DataFrame({"chirps": df["chirps_monsoon_mm"].to_numpy(), "imerg": im.to_numpy()}, index=df["year"].astype(int)).dropna()
    out["chirps_vs_imerg"] = {"n": int(len(both)), "pearson_r": float(both.corr().iloc[0, 1]),
                              "mean_chirps_mm": float(both["chirps"].mean()), "mean_imerg_mm": float(both["imerg"].mean()),
                              "year_2020": {"chirps_mm": float(both.loc[2020, "chirps"]), "imerg_mm": float(both.loc[2020, "imerg"])} if 2020 in both.index else None,
                              "note": "CHIRPS over the script ROI (69.0-69.9 E, 23.4-23.9 N); IMERG over the platform rectangle (68.80-69.95 E, 23.20-23.95 N)."}
    out["rain_removed_imerg"] = {k: rain_removed(df.set_index("year").loc[both.index, k], both["imerg"], both.index.to_numpy(float))
                                 for k in ("ndvi_hi_pros", "ndvi_lo_pros")}
    RES.mkdir(parents=True, exist_ok=True)
    (RES / "trend_tests.json").write_text(json.dumps(out, indent=2))

    f = lambda t: f"{t['direction']:<22} slope {t['sen_slope_per_year']:+.5f}/yr  p={t['p']:.4f}"
    print(f"Input: {out['input']}  ({len(df)} years)")
    for k, t in out["trend"].items():
        print(f"  trend  {k:<20} {f(t)}")
    for src in ("chirps", "imerg"):
        for k, r in out[f"rain_removed_{src}"].items():
            print(f"  rain-removed ({src:6}) {k:<13} R2={r['r2_rain']:.2f}  residual {f(r['residual_trend'])}  "
                  f"year term {r['year_term']['coef_per_year']:+.5f} p={r['year_term']['p']:.4f}")
    c = out["chirps_vs_imerg"]
    print(f"  CHIRPS vs IMERG monsoon totals: r={c['pearson_r']:.3f}, means {c['mean_chirps_mm']:.0f} vs {c['mean_imerg_mm']:.0f} mm, 2020: {c['year_2020']}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else RES / "banni_ndvi_by_prosopis_chirps.csv")
