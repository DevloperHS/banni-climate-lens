"""Phase-1/3/4 science: raster QC, masks, agreement, indicator, validation tools, multivariate comparison,
groundwater, rain-adjusted event study, metadata verification."""
import io
import numpy as np
import pandas as pd
import pytest
from rasterio.crs import CRS
from rasterio.transform import from_bounds

from app.core import groundwater as GW
from app.science import multivar as MV
from app.science import raster_qc as RQ
from app.science import stats as S
from app.science import validation as VA
from app import verify_metadata as VM


# ------------------------------------------------------------------ raster QC
def _info(T=12, H=20, W=30, crs=4326, bounds=(68.8, 23.2, 69.95, 23.95), desc=None, data=None):
    class B: pass
    b = B(); b.left, b.bottom, b.right, b.top = bounds
    data = np.random.default_rng(1).normal(0.3, 0.05, (T, H, W)) if data is None else data
    return {"data": data, "transform": from_bounds(*bounds, W, H), "crs": CRS.from_epsg(crs), "bounds": b,
            "descriptions": desc or [f"y{2001 + i}" for i in range(T)], "height": H, "width": W, "tags": {}}


BBOX = {"west": 68.8, "east": 69.95, "south": 23.2, "north": 23.95}


def test_validate_stack_accepts_good_and_rejects_bad():
    ok = RQ.validate_stack(_info(H=60, W=92), BBOX)          # ~0.0125 deg pixels
    assert ok["ok"] and ok["n_bands"] == 12 and ok["pixel_size_m_approx"][0] > 1000
    assert not RQ.validate_stack(_info(crs=32643), BBOX)["ok"]
    assert any("cover" in i for i in RQ.validate_stack(_info(bounds=(69.2, 23.4, 69.5, 23.6)), BBOX)["issues"])
    assert any("square" in i for i in RQ.validate_stack(_info(H=10, W=100), BBOX)["issues"])
    assert any("year" in i for i in RQ.validate_stack(_info(desc=["a"] * 12), BBOX)["issues"])
    assert any("increasing" in i for i in RQ.validate_stack(_info(desc=[f"y{2020 - i}" for i in range(12)]), BBOX)["issues"])
    assert any("no valid" in i for i in RQ.validate_stack(_info(data=np.full((12, 20, 30), np.nan)), BBOX)["issues"])


def test_grid_alignment_and_resampling():
    a, b = _info(H=20, W=30), _info(H=20, W=30)
    assert RQ.grids_aligned(a, b)
    coarse = _info(T=1, H=10, W=15, data=np.arange(150, dtype=float).reshape(1, 10, 15))
    fine = _info(T=1, H=20, W=30)
    out = RQ.align_to(coarse, fine, "nearest")
    assert out.shape == (1, 20, 30) and out[0, 0, 0] == 0 and out[0, 19, 29] == 149          # nearest upsampling keeps values
    assert not RQ.grids_aligned(coarse, fine)


def test_water_mask_removes_only_water_pixels():
    stack = np.ones((5, 4, 4))
    occ = np.zeros((4, 4)); occ[0, :2] = [50, 9.9]; occ[3, 3] = 100; occ[1, 1] = np.nan
    out, rep = RQ.apply_water_mask(stack, occ, 10)
    assert np.isnan(out[:, 0, 0]).all() and np.isnan(out[:, 3, 3]).all() and np.isfinite(out[:, 0, 1]).all() and np.isfinite(out[:, 1, 1]).all()
    assert rep["pixels_masked"] == 2 and rep["fraction_of_valid_masked"] == pytest.approx(2 / 16)
    with pytest.raises(RQ.RasterError):
        RQ.apply_water_mask(stack, np.zeros((3, 3)), 10)


def test_mask_changes_trend_result_when_water_pixels_trend():
    """Water pixels with a spurious trend contaminate the regional result; masking removes them."""
    from app.science.pixel import pixel_trends
    rng = np.random.default_rng(0); T = 20; yrs = np.arange(2001, 2021)
    stack = rng.normal(0.3, 0.02, (T, 10, 10)); stack[:, :3, :] += 0.01 * (yrs - 2001)[:, None, None]       # water-edge pixels 'green up'
    occ = np.zeros((10, 10)); occ[:3, :] = 80
    raw = pixel_trends(stack, yrs); m, _ = RQ.apply_water_mask(stack, occ, 10); masked = pixel_trends(m, yrs)
    assert (raw["cls"] == 1).sum() > 20 and (masked["cls"] == 1).sum() == 0 and np.isnan(masked["cls"][:3]).all()


def test_difference_summary_and_period_mean():
    yrs = np.arange(2001, 2011); st = np.stack([np.full((3, 3), 0.1 + 0.01 * i) for i in range(10)])
    a, b = RQ.period_mean(st, yrs, 2001, 2003), RQ.period_mean(st, yrs, 2008, 2010)
    d = RQ.difference_summary(a, b)
    assert d["mean_change"] == pytest.approx(0.07) and d["pct_increase"] == 100
    with pytest.raises(RQ.RasterError):
        RQ.period_mean(st, yrs, 1990, 1995)


def test_trend_agreement_between_resolutions():
    from app.science.pixel import pixel_trends
    rng = np.random.default_rng(2); yrs = np.arange(2001, 2025)
    truth = np.zeros((24, 24)); truth[:12] = 0.01                                      # greening in the top half
    fine = 0.3 + truth[None] * (yrs - 2001)[:, None, None] + rng.normal(0, 0.03, (24, 24, 24))
    coarse_stack = RQ.block_mean(fine, 4)                                                # 6x6 'MODIS-like'
    f = pixel_trends(fine, yrs); c = pixel_trends(coarse_stack, yrs)
    fine_on_coarse = {"slope": RQ.block_mean(f["slope"], 4), "cls": RQ.block_mean(f["cls"], 4)}
    ag = RQ.trend_agreement({"slope": c["slope"], "cls": c["cls"]}, fine_on_coarse)
    assert ag["spearman_rho"] > 0.8 and ag["sign_agreement_pct"] > 80
    with pytest.raises(RQ.RasterError):
        RQ.trend_agreement({"slope": np.full((2, 2), np.nan), "cls": np.zeros((2, 2))}, {"slope": np.zeros((2, 2)), "cls": np.zeros((2, 2))})


def test_evergreen_index_is_bounded_and_ignores_bare_ground():
    dry = np.array([0.30, 0.10, 0.02]); wet = np.array([0.40, 0.20, 0.01])
    e = RQ.evergreen_index(dry, wet)
    assert e[0] == pytest.approx(0.75) and e[1] == pytest.approx(0.5) and np.isnan(e[2])      # wet NDVI below threshold -> no ratio
    assert RQ.evergreen_index(np.array([5.0]), np.array([0.1]))[0] == 2.0                     # capped


# ------------------------------------------------------------------ ground truth / EC validation (no labels ship with the project)
def _labels_csv(n_a=30, n_b=30):
    rows = [f"{23.3 + 0.001 * i},69.1,prosopis" for i in range(n_a)] + [f"{23.5 + 0.001 * i},69.3,grass" for i in range(n_b)]
    return ("lat,lon,class\n" + "\n".join(rows)).encode()


def test_labels_parsing_validation():
    df, rep = VA.parse_labels_csv(_labels_csv())
    assert rep["rows_valid"] == 60 and rep["class_counts"] == {"prosopis": 30, "grass": 30} and rep["warnings"] == []
    bad = b"lat,lon,class\n95,69,a\n23,69,a\n23,69,a\n23.1,69,b\nx,69,b\n"
    df, rep = VA.parse_labels_csv(bad)
    assert rep["rejected"] == 2 and rep["duplicates_removed"] == 1
    with pytest.raises(VA.ValidationError):
        VA.parse_labels_csv(b"lat,lon\n1,2\n")
    with pytest.raises(VA.ValidationError):
        VA.parse_labels_csv(b"lat,lon,class\n23,69,a\n23.1,69,a\n")                                # one class only


def test_separability_refuses_small_samples_and_detects_real_separation():
    rng = np.random.default_rng(3)
    v = np.r_[rng.normal(0.8, 0.1, 40), rng.normal(0.4, 0.1, 40)]; c = np.array(["p"] * 40 + ["g"] * 40)
    r = VA.indicator_separability(v, c)
    pr = r["pairs"][0]
    assert pr["auc"] > 0.95 and pr["higher_class"] == "p" and pr["auc_ci_low"] > 0.85 and pr["mannwhitney_p"] < 1e-6 and r["caveats"]
    small = VA.indicator_separability(v[:5].tolist() + v[40:45].tolist() and np.r_[v[:5], v[40:45]], np.array(["p"] * 5 + ["g"] * 5))
    assert small["pairs"][0]["auc"] is None and "fewer than" in small["pairs"][0]["reason"]
    noise = VA.indicator_separability(rng.normal(size=80), c)
    assert 0.3 < noise["pairs"][0]["auc"] < 0.7


def test_ec_validation_requires_enough_points():
    assert VA.ec_validation(np.arange(5.0), np.arange(5.0))["status"] == "insufficient"
    rng = np.random.default_rng(4); idx = rng.normal(size=40)
    good = VA.ec_validation(idx, 2 * idx + rng.normal(0, 0.3, 40))
    assert good["status"] == "computed" and good["spearman_rho"] > 0.8 and good["ci_low"] > 0.6
    none = VA.ec_validation(idx, rng.normal(size=40))
    assert "No convincing" in none["message"]


# ------------------------------------------------------------------ multivariate comparison
def _frame(seed=1, n=24):
    rng = np.random.default_rng(seed); yrs = np.arange(2001, 2001 + n)
    rain = rng.gamma(2, 150, n); temp = 40 + 0.05 * (yrs - 2001) + rng.normal(0, 0.5, n)
    ndvi = 0.1 + 0.0004 * rain + rng.normal(0, 0.01, n)
    et = 100 + 0.2 * rain + rng.normal(0, 8, n)
    return pd.DataFrame({"ndvi": ndvi, "rain": rain, "temp": temp, "et": et}, index=yrs)


def test_compare_matrix_and_fdr():
    r = MV.compare(_frame(), response="ndvi")
    P = np.array(r["pearson"])
    assert P.shape == (4, 4) and np.allclose(np.diag(P), 1) and np.allclose(P, P.T)
    pr = {(x["a"], x["b"]): x for x in r["pairs"]}
    assert pr[("ndvi", "rain")]["pearson_r"] > 0.8 and pr[("ndvi", "rain")]["significant_bh"]
    assert not pr[("ndvi", "temp")]["significant_bh"]
    assert "does not show" in r["association_note"] and "cannot establish causation" in r["causation_note"]


def test_compare_prediction_vs_association_and_vif():
    r = MV.compare(_frame(), response="ndvi")
    assert r["prediction"]["r2_loo_cv"] <= r["prediction"]["r2_in_sample"] + 1e-9
    assert r["regression"]["vif"]["rain"] > 1 and "temp" in r["regression"]["vif"]
    # ET is a near-copy of rain -> collinearity must be flagged when both are predictors
    f = _frame(); f["et"] = f["rain"] * 0.2 + np.random.default_rng(9).normal(0, 1, 24)
    assert MV.compare(f, response="ndvi")["regression"]["collinearity_warning"] is True


def test_loo_r2_matches_brute_force():
    rng = np.random.default_rng(5); X = rng.normal(size=(20, 2)); y = X @ [1, 2] + rng.normal(size=20)
    press = 0.0
    for i in range(20):
        m = np.ones(20, bool); m[i] = False
        A = np.column_stack([np.ones(19), X[m]]); b, *_ = np.linalg.lstsq(A, y[m], rcond=None)
        press += (y[i] - np.r_[1, X[i]] @ b) ** 2
    assert MV.loo_r2(y, X)["press"] == pytest.approx(press)


def test_partial_correlation_removes_confounder():
    rng = np.random.default_rng(6); z = rng.normal(size=60); a = z + rng.normal(0, 0.3, 60); b = z + rng.normal(0, 0.3, 60)
    df = pd.DataFrame({"a": a, "b": b, "z": z})
    assert MV.partial_correlation(df, "a", "b", [])["r"] > 0.8
    assert abs(MV.partial_correlation(df, "a", "b", ["z"])["r"]) < 0.4


def test_compare_anomalies_and_guards():
    f = _frame(); f.loc[2010, "rain"] += 2000; f.loc[2010, "et"] += 400
    r = MV.compare(f)
    assert any(x["year"] == 2010 and x["coincident"] for x in r["anomaly_years"])
    with pytest.raises(ValueError):
        MV.compare(_frame(n=5));
    with pytest.raises(ValueError):
        MV.compare(_frame()[["ndvi"]])


def test_detrend_removes_shared_trend_correlation():
    yrs = np.arange(2001, 2025); rng = np.random.default_rng(7)
    f = pd.DataFrame({"a": 0.01 * (yrs - 2001) + rng.normal(0, .01, 24), "b": 2 * (yrs - 2001) + rng.normal(0, 1, 24)}, index=yrs)
    assert MV.compare(f)["pairs"][0]["pearson_r"] > 0.9 and abs(MV.compare(f, detrend=True)["pairs"][0]["pearson_r"]) < 0.5


# ------------------------------------------------------------------ rain-adjusted event study
def _monthly(fn):
    idx = pd.date_range("2001-01-01", "2024-12-01", freq="MS")
    return pd.Series([fn(d) for d in idx], index=idx, dtype=float)


def test_event_adjustment_explains_rain_driven_change_but_not_independent_shock():
    rng = np.random.default_rng(8)
    rain = _monthly(lambda d: (150 if d.month in (6, 7, 8, 9) else 5) * rng.gamma(4, .25))
    rain[(rain.index >= "2023-06-01") & (rain.index < "2023-09-01")] *= 4                               # very wet 2023 monsoon
    ndvi_rain = 0.1 + 0.0004 * rain.rolling(3, min_periods=1).sum() + _monthly(lambda d: rng.normal(0, .01))
    ev = pd.Timestamp("2023-06-15")
    r = S.event_study_rain_adjusted(ndvi_rain, rain, ev)
    assert r["raw"]["z_vs_reference"] > 5 and abs(r["rain_adjusted"]["z_vs_reference"]) < r["raw"]["z_vs_reference"] / 3 and "attributes" in r["interpretation"]
    shock = ndvi_rain.copy(); shock[(shock.index >= "2023-06-01") & (shock.index < "2023-09-01")] += 0.25
    r2 = S.event_study_rain_adjusted(shock, rain, ev)
    assert r2["rain_adjusted"]["z_vs_reference"] > 5 and r2["adjustment"]["r2_non_event_years"] > 0.3


# ------------------------------------------------------------------ groundwater
def _gw_csv(wells=3, years=range(2005, 2024), trend=0.3, extra=""):
    rows = ["date,value,well_id"]
    rng = np.random.default_rng(11)
    for w in range(wells):
        for y in years:
            for m in (1, 5, 8, 11):
                rows.append(f"{y}-{m:02d}-15,{8 + 3 * w + trend * (y - 2005) + rng.normal(0, .3):.2f},W{w}")
    return ("\n".join(rows) + extra).encode()


def test_groundwater_parse_validation_report():
    df, rep = GW.parse(_gw_csv(extra="\n2010-01-01,-3,W0\nbad,5,W0\n2012-01-01,abc,W1\n2030-01-01,5,W1\n2010-01-15,10,W0"))
    assert rep["n_wells"] == 3 and rep["rows_valid"] == 3 * 19 * 4
    r = rep["rejected_by_reason"]
    assert r["unparseable date"] == 1 and r["non-numeric value"] == 1 and r["date in the future"] == 1 and any("outside" in k for k in r)
    assert rep["duplicates_removed"] >= 1 and "below ground" in rep["unit_assumption"]
    with pytest.raises(GW.GroundwaterError):
        GW.parse(b"date,value\n2020-01-01,5\n")
    with pytest.raises(GW.GroundwaterError):
        GW.parse(b"a,b\n1,2\n")


def test_groundwater_well_id_sanitised():
    df, _ = GW.parse(b"date,value,well_id\n" + b"\n".join(f"2010-{m:02d}-01,{5 + m},../../etc/passwd".encode() for m in range(1, 9)))
    assert "/" not in df["well_id"].iloc[0] and ".." not in df["well_id"].iloc[0].replace("_", "") or df["well_id"].iloc[0].count("/") == 0


def test_groundwater_aggregation_uses_anomalies_across_wells():
    df, _ = GW.parse(_gw_csv(wells=3))
    m = GW.aggregate_monthly(df)
    s = pd.Series(m); s.index = pd.PeriodIndex(s.index, freq="M").to_timestamp()
    ann = s.groupby(s.index.year).mean()
    t = S.mann_kendall(ann.values, ann.index.values.astype(float))
    assert t["direction"] == "increasing" and t["slope"] == pytest.approx(0.3, abs=0.05)
    # a well that stops reporting early (different baseline) must not create a spurious step in the aggregate
    csv = _gw_csv(wells=3, trend=0.0).decode().splitlines()
    csv = [l for l in csv if not (l.endswith("W2") and int(l[:4]) > 2014)]
    df2, _ = GW.parse("\n".join(csv).encode()); m2 = GW.aggregate_monthly(df2)
    s2 = pd.Series(m2); s2.index = pd.PeriodIndex(s2.index, freq="M").to_timestamp(); a2 = s2.groupby(s2.index.year).mean()
    assert S.mann_kendall(a2.values, a2.index.values.astype(float))["direction"] == "no significant trend"


def test_per_well_trends_with_fdr(tmp_path):
    df, rep = GW.parse(_gw_csv(wells=4))
    wells = {"wells": {w: {"dates": [d.strftime("%Y-%m-%d") for d in g["date"]], "values": g["value"].tolist()} for w, g in df.groupby("well_id")}}
    rows = GW.per_well_trends(wells)
    assert len(rows) == 4 and all(r["direction"] == "increasing" and r["significant_fdr"] for r in rows) and "deepening" in rows[0]["meaning"]


# ------------------------------------------------------------------ metadata verification
def _stac(units="mm/hr", scale=None, gsd=11132, end="2025-09-01T00:00:00Z"):
    return {"id": "x", "summaries": {"gsd": [gsd], "eo:bands": [{"name": "precipitation", "gee:units": units, **({"gee:scale": scale} if scale else {})}]},
            "extent": {"temporal": {"interval": [["1998-01-01T00:00:00Z", end]]}}}


def test_metadata_check_detects_unit_scale_gsd_and_coverage_problems():
    ok = VM.check_record("c", _stac(), {"precipitation": {"units": "mm/hr"}}, 11132, "2024-12-31")
    assert ok["ok"]
    assert not VM.check_record("c", _stac(units="mm/day"), {"precipitation": {"units": "mm/hr"}}, 11132, None)["ok"]
    assert not VM.check_record("c", _stac(scale=0.1), {"precipitation": {"scale": 0.01}}, None, None)["ok"]
    assert not VM.check_record("c", _stac(gsd=5000), {}, 11132, None)["ok"]
    r = VM.check_record("c", _stac(end="2022-01-01T00:00:00Z"), {}, None, "2024-12-31")
    assert not r["ok"] and "coverage ends" in r["issues"][0]
    assert not VM.check_record("c", _stac(), {"nope": {}}, None, None)["ok"]


def test_verify_all_uses_injected_fetcher_and_reports_fetch_failures():
    def f(prov, slug):
        if "IMERG" in slug:
            raise OSError("offline")
        return {"id": slug, "summaries": {"eo:bands": [], "gsd": [0]}, "extent": {"temporal": {"interval": [[None, None]]}}}
    r = VM.verify_all(f)
    assert not r["all_ok"] and any("fetch failed" in i for x in r["results"] for i in x["issues"])


# ------------------------------------------------------------------ conservative test selection (found on real Banni ET data)
def _alternating(seed=0):
    rng = np.random.default_rng(seed); t = np.arange(24)
    return 0.25 * t + 3.0 * np.where(t % 2 == 0, 1, -1) * rng.uniform(0.5, 1.5, 24), t + 2001.0


def test_hamed_rao_variance_deflation_is_not_the_headline():
    """Negative rank autocorrelation can shrink Var(S) (factor<1) and make HR far MORE significant than plain MK."""
    x, t = _alternating()
    r = S.trend_report(x, t)
    assert r["hr"]["variance_correction"] < 0.5 and r["hr"]["p"] < r["mk"]["p"] / 100        # the pathology is present
    assert r["recommended"] == "mk"                                                          # ... and is NOT used as the headline
    assert any("more significant than plain Mann-Kendall" in w for w in r["warnings"])
    assert r["mk"]["p"] == pytest.approx(0.0309, abs=1e-3)


def test_hamed_rao_still_recommended_when_it_widens_uncertainty():
    rng = np.random.default_rng(0); e = rng.normal(size=30); x = np.empty(30); x[0] = e[0]
    for i in range(1, 30):
        x[i] = 0.8 * x[i - 1] + e[i]                                                         # strongly positive autocorrelation
    r = S.trend_report(x, np.arange(30) + 1990.0)
    assert r["hr"]["variance_correction"] > 1.0 and r["recommended"] == "hr" and r["hr"]["p"] > r["mk"]["p"]


def test_handover_protocol_is_unchanged_by_the_conservative_rule():
    """The reproduction must keep using plain Hamed-Rao exactly as the handover specifies."""
    from app.science import handover as H
    import pymannkendall as pmk
    x, t = _alternating()
    assert H._trend(x)["p"] == pytest.approx(pmk.hamed_rao_modification_test(x).p)
