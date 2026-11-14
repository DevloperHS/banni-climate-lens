import calendar
from datetime import date
import numpy as np
import pandas as pd
import pymannkendall as pmk
import pytest
from scipy import stats as sps

from app.science import processing as P
from app.science import stats as S
from app.science import timeseries as TS
from app.science import pixel as PX


# ---------------------------------------------------------------- processing / units
def test_ndvi_scale_and_fill():
    out = P.ndvi_from_dn([5000, -3000, 10000, -2000])
    assert out[0] == pytest.approx(0.5) and np.isnan(out[1]) and out[2] == pytest.approx(1.0)
    assert out[3] == pytest.approx(-0.2)


def test_lst_conversion_kelvin_to_celsius():
    # DN 15000 * 0.02 = 300 K = 26.85 C ; DN 0 is fill
    out = P.lst_dn_to_celsius([15000, 0])
    assert out[0] == pytest.approx(26.85) and np.isnan(out[1])


def test_et_scale_and_fill():
    out = P.et_dn_to_mm_composite([100, 32761])
    assert out[0] == pytest.approx(10.0) and np.isnan(out[1])


def test_imerg_rate_to_monthly_total():
    # 0.1 mm/hr over 31 days = 74.4 mm ; Feb leap year 29 days
    assert P.imerg_rate_to_month_mm(0.1, 2001, 7) == pytest.approx(0.1 * 24 * 31)
    assert P.imerg_rate_to_month_mm(0.1, 2024, 2) == pytest.approx(0.1 * 24 * 29)
    assert P.imerg_rate_to_month_mm(None, 2001, 7) is None


def test_landsat_scaling_and_ndvi():
    refl = P.landsat_sr_to_reflectance([20000, 10000])
    assert refl[0] == pytest.approx(0.35) and refl[1] == pytest.approx(0.075)
    assert P.ndvi_from_reflectance(0.35, 0.075) == pytest.approx((0.35 - 0.075) / (0.35 + 0.075))


def test_qa_decoding():
    assert P.lst_qc_ok(0b00000000)
    assert P.lst_qc_ok(0b01000001)            # other quality, error class 1 (<=2K)
    assert not P.lst_qc_ok(0b10000000)        # error class 2
    assert not P.lst_qc_ok(0b00000010)        # not produced
    assert P.landsat_qa_clear(0)
    assert not P.landsat_qa_clear(1 << 3)     # cloud
    assert not P.landsat_qa_clear(1 << 4)     # shadow


def test_et_composites_to_monthly_constant_rate():
    """A constant 1 mm/day ET must give exactly days_in_month mm per month, including the
    short final composite of the year."""
    ds, vals, spans = [], [], []
    for y in (2020, 2021):
        d = date(y, 1, 1)
        while d.year == y:
            sp = P.composite_span_days(d)
            ds.append(d); spans.append(sp); vals.append(1.0 * sp)
            d = date.fromordinal(d.toordinal() + 8)
    m = P.composites_to_monthly(ds, vals, "sum", spans)
    assert spans[45] == 6 and spans[91] == 5          # 2020 (leap): last composite 6 d; 2021: 5 d
    for k, v in m.items():
        y, mo = int(k[:4]), int(k[5:])
        assert v == pytest.approx(calendar.monthrange(y, mo)[1]), k


def test_mean_composites_to_monthly():
    m = P.composites_to_monthly([date(2001, 1, 1), date(2001, 1, 17), date(2001, 2, 2)], [0.2, 0.4, 0.5], "mean", [16, 16, 16])
    assert m["2001-01"] == pytest.approx(0.3) and m["2001-02"] == pytest.approx(0.5)


# ---------------------------------------------------------------- trend tests
def test_mk_matches_pymannkendall_random():
    rng = np.random.default_rng(1)
    for _ in range(10):
        x = np.cumsum(rng.normal(0.1, 1, 24))
        mine = S.mann_kendall(x, np.arange(1, 25))
        ref = pmk.original_test(x)
        assert mine["z"] == pytest.approx(ref.z, abs=1e-9)
        assert mine["p"] == pytest.approx(ref.p, abs=1e-9)
        assert mine["slope"] == pytest.approx(ref.slope, abs=1e-9)
        assert mine["s"] == ref.s


def test_hamed_rao_matches_pymannkendall():
    rng = np.random.default_rng(7)
    for _ in range(10):
        e = rng.normal(size=30)
        x = np.empty(30); x[0] = e[0]
        for i in range(1, 30):
            x[i] = 0.6 * x[i - 1] + e[i]
        mine = S.mann_kendall(x, np.arange(30), hamed_rao=True)
        ref = pmk.hamed_rao_modification_test(x)
        assert mine["z"] == pytest.approx(ref.z, abs=1e-8)
        assert mine["p"] == pytest.approx(ref.p, abs=1e-8)


def test_mk_perfect_trend_and_sen_exact():
    x = 2.0 * np.arange(1, 25) + 5
    r = S.mann_kendall(x, np.arange(2001, 2025))
    assert r["slope"] == pytest.approx(2.0) and r["direction"] == "increasing" and r["p"] < 1e-6
    assert r["tau"] == pytest.approx(1.0)
    assert r["slope_ci_low"] <= 2.0 <= r["slope_ci_high"]


def test_mk_no_trend_noise():
    rng = np.random.default_rng(3)
    r = S.mann_kendall(rng.normal(size=24), np.arange(24))
    assert r["direction"] == "no significant trend"


def test_sen_uses_actual_time_with_gaps():
    t = np.array([2001, 2002, 2005, 2010, 2011, 2015.0])
    r = S.sen_slope(3 * t + 1, t)
    assert r["slope"] == pytest.approx(3.0)


def test_mk_handles_nan_and_min_n():
    x = np.array([1, 2, np.nan, 4, 5, 6.0]); r = S.mann_kendall(x, np.arange(6))
    assert r["n"] == 5
    with pytest.raises(ValueError):
        S.mann_kendall([1, 2, 3])


def test_mk_tie_correction():
    x = np.array([1, 1, 2, 2, 3, 3, 4, 4.0]); r = S.mann_kendall(x)
    assert r["var_s"] == pytest.approx(pmk.original_test(x).var_s)


# ---------------------------------------------------------------- regression
def test_ols_matches_closed_form_and_scipy():
    rng = np.random.default_rng(5)
    x = rng.normal(size=40); y = 1.5 + 2.0 * x + rng.normal(scale=0.5, size=40)
    f = S.ols(y, {"x": x})
    lr = sps.linregress(x, y)
    b = {c["name"]: c for c in f["coefficients"]}
    assert b["x"]["coef"] == pytest.approx(lr.slope) and b["intercept"]["coef"] == pytest.approx(lr.intercept)
    assert f["r2"] == pytest.approx(lr.rvalue ** 2) and b["x"]["p"] == pytest.approx(lr.pvalue)
    assert b["x"]["ci_low"] < lr.slope < b["x"]["ci_high"]
    assert np.sum(f["residuals"]) == pytest.approx(0, abs=1e-9)


def test_ols_too_few_obs():
    with pytest.raises(ValueError):
        S.ols([1, 2, 3], {"x": [1, 2, 4]})


def test_correlation():
    a = np.arange(20.0); r = S.correlation(a, a * 2 + 1)
    assert r["pearson_r"] == pytest.approx(1.0) and "causation" in r["note"]


# ---------------------------------------------------------------- rainfall-adjusted
def _synth(trend: float, seed=11, n=24):
    rng = np.random.default_rng(seed)
    yrs = np.arange(2001, 2001 + n)
    rain = rng.gamma(2.0, 150, n)
    ndvi = 0.10 + 0.0004 * rain + trend * (yrs - 2001) + rng.normal(0, 0.01, n)
    return yrs, ndvi, rain


def test_rainfall_adjusted_detects_residual_trend():
    yrs, ndvi, rain = _synth(trend=0.004)
    r = S.rainfall_adjusted(yrs, ndvi, rain)
    assert r["residual_trend"]["mk"]["direction"] == "increasing"
    yc = next(s for s in r["sensitivity"] if s["name"].startswith("S3"))
    assert yc["year_coef_per_year"] == pytest.approx(0.004, abs=0.0015)
    assert r["verdict"]["sensitivity_total"] >= 2
    assert any("Prosopis" in c for c in r["caveats"])           # confounder caveat always present


def test_rainfall_adjusted_rain_explains_everything():
    """NDVI driven only by rain -> raw NDVI may trend (rain trends) but residuals must not."""
    rng = np.random.default_rng(2)
    yrs = np.arange(2001, 2025)
    rain = 200 + 8 * (yrs - 2001) + rng.normal(0, 40, 24)
    ndvi = 0.1 + 0.0005 * rain + rng.normal(0, 0.004, 24)
    r = S.rainfall_adjusted(yrs, ndvi, rain)
    assert r["ndvi_trend"]["mk"]["direction"] == "increasing"
    assert r["residual_trend"]["mk"]["direction"] == "no significant trend"
    assert any("Rainfall itself has a significant trend" in c for c in r["caveats"])


def test_rainfall_adjusted_needs_data():
    with pytest.raises(ValueError):
        S.rainfall_adjusted([1, 2, 3], [1, 2, 3], [1, 2, 3])


# ---------------------------------------------------------------- FDR
def test_bh_matches_known_example():
    p = np.array([0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.074, 0.205, 0.212, 0.216])
    rej, adj = S.benjamini_hochberg(p, 0.05)
    # reference adjusted values via manual BH
    m = len(p); ref = np.minimum.accumulate((p * m / np.arange(1, m + 1))[::-1])[::-1]
    assert np.allclose(adj, np.minimum(ref, 1))
    assert rej.tolist() == [True, True] + [False] * 8


def test_bh_ignores_nan():
    rej, adj = S.benjamini_hochberg(np.array([0.001, np.nan, 0.5]), 0.05)
    assert rej.tolist() == [True, False, False] and np.isnan(adj[1])


def test_bh_controls_fdr_under_null():
    rng = np.random.default_rng(0)
    false_rej = [S.benjamini_hochberg(rng.uniform(size=2000), 0.05)[0].sum() for _ in range(20)]
    assert np.mean(np.array(false_rej) > 0) < 0.3     # FWER-ish sanity under global null


# ---------------------------------------------------------------- pixel trends
def test_pixel_trends_match_scalar_implementation():
    rng = np.random.default_rng(4)
    T, H, W = 20, 6, 7
    yrs = np.arange(2001, 2001 + T)
    stack = rng.normal(size=(T, H, W)) * 0.1
    stack[:, :3, :] += 0.02 * (yrs - 2001)[:, None, None]       # increasing top half
    stack[3, 4, 4] = np.nan
    res = PX.pixel_trends(stack, yrs, row_chunk=4)
    for (i, j) in [(0, 0), (2, 5), (4, 4), (5, 6)]:
        ref = S.mann_kendall(stack[:, i, j], yrs)
        assert res["z"][i, j] == pytest.approx(ref["z"], abs=1e-9)
        assert res["p"][i, j] == pytest.approx(ref["p"], abs=1e-9)
        assert res["slope"][i, j] == pytest.approx(ref["slope"], abs=1e-9)
    assert np.nanmean(res["cls"][:3] == 1) > 0.9
    assert np.all(res["cls"][3:] != 1) or np.nanmean(res["cls"][3:] == 1) < 0.1


def test_pixel_min_valid_and_fdr_reduces_false_positives():
    rng = np.random.default_rng(8)
    stack = rng.normal(size=(24, 40, 40))
    stack[:, 0, 0] = np.nan; stack[:15, 1, 1] = np.nan
    res = PX.pixel_trends(stack, np.arange(24))
    assert np.isnan(res["cls"][0, 0]) and np.isnan(res["cls"][1, 1])
    s = PX.summarise(res)
    assert s["significant_increase_uncorrected"] + s["significant_decrease_uncorrected"] > 20   # ~5% of 1600
    assert s["significant_increase_fdr"] + s["significant_decrease_fdr"] <= 2


def test_pixel_ties_handled():
    stack = np.tile(np.array([1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6.0])[:, None, None], (1, 2, 2))
    res = PX.pixel_trends(stack, np.arange(12), min_valid=10)
    ref = S.mann_kendall(stack[:, 0, 0], np.arange(12))
    assert res["z"][0, 0] == pytest.approx(ref["z"])


def test_geotiff_roundtrip(tmp_path):
    from rasterio.transform import from_bounds
    from rasterio.crs import CRS
    arr = np.arange(12, dtype=float).reshape(3, 4); arr[0, 0] = np.nan
    t = from_bounds(68.8, 23.2, 69.95, 23.95, 4, 3)
    p = PX.write_geotiff(tmp_path / "a.tif", {"slope": arr}, t, CRS.from_epsg(4326), {"k": "v"})
    info = PX.read_stack(p)
    assert info["data"].shape == (1, 3, 4) and np.isnan(info["data"][0, 0, 0]) and info["crs"].to_epsg() == 4326
    assert info["descriptions"][0] == "slope"


# ---------------------------------------------------------------- timeseries
def _monthly(years, fn):
    idx = pd.date_range(f"{years[0]}-01-01", f"{years[-1]}-12-01", freq="MS")
    return pd.Series([fn(d) for d in idx], index=idx, dtype=float)


def test_seasonal_aggregate_sum_requires_full_season():
    s = _monthly([2001, 2002], lambda d: 10.0)
    s[pd.Timestamp("2002-07-01")] = np.nan
    mon = TS.seasonal_aggregate(s, "monsoon", "sum")
    assert mon.loc[2001] == 40.0 and 2002 not in mon.index
    ann = TS.seasonal_aggregate(s, "annual", "sum")
    assert ann.loc[2001] == 120.0 and 2002 not in ann.index
    assert TS.seasonal_aggregate(s, "monsoon", "mean").loc[2002] == 10.0     # 3/4 months OK for a mean


def test_anomaly_zero_mean_per_month():
    s = _monthly(range(2001, 2011), lambda d: d.month + (d.year - 2001) * 0.1)
    a = TS.monthly_anomaly(s)
    assert a.groupby(a.index.month).mean().abs().max() < 1e-12


def test_annual_anomaly_flags():
    a = pd.Series([1.0] * 19 + [10.0], index=range(2001, 2021))
    df = TS.annual_anomaly(a)
    assert bool(df.loc[2020, "flag"]) and not bool(df.loc[2005, "flag"])


# ---------------------------------------------------------------- event study
def test_event_study_detects_shock_and_ignores_normal():
    rng = np.random.default_rng(6)
    s = _monthly(range(2001, 2025), lambda d: 0.3 + 0.1 * np.sin(2 * np.pi * d.month / 12) + rng.normal(0, 0.01))
    ev = pd.Timestamp("2023-06-15")
    base = S.event_study(s, ev)
    assert not base["extreme"]
    s2 = s.copy(); s2[(s2.index >= "2023-06-01") & (s2.index < "2023-09-01")] += 0.2
    shocked = S.event_study(s2, ev)
    assert shocked["extreme"] and shocked["delta"] > 0.15 and "Association only" in shocked["interpretation"]
