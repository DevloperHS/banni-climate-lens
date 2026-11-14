"""Handover reproduction, geometry handling, real-data schema validation, reproducibility, data quality."""
import json
import math

import numpy as np
import pandas as pd
import pymannkendall as mk
import pytest
import statsmodels.api as sm

from app.core import store
from app.core import regions as R
from app.core.catalog import CATALOG
from app.gee import client as eeclient, extract
from app.science import handover as H
from app.science import processing as P


# ------------------------------------------------------------------ handover protocol
def _monthly(fn):
    idx = pd.date_range("2001-01-01", "2024-12-01", freq="MS")
    return pd.Series([fn(d) for d in idx], index=idx, dtype=float)


def test_handover_annual_uses_mean_for_ndvi_and_sum_for_rain():
    nd = _monthly(lambda d: 0.1 + 0.01 * (d.month in (6, 7, 8, 9)) * d.month)
    rn = _monthly(lambda d: 100.0 if d.month in (6, 7, 8, 9) else 5.0)
    df = H.handover_annual(nd, rn)
    assert len(df) == 24 and df["rain_monsoon"].iloc[0] == 400.0
    assert df["ndvi_monsoon"].iloc[0] == pytest.approx(np.mean([0.1 + 0.01 * m for m in (6, 7, 8, 9)]))


def test_handover_annual_inner_join_and_partial_months():
    nd = _monthly(lambda d: 0.2); rn = _monthly(lambda d: 10.0)
    rn[pd.Timestamp("2005-07-01")] = np.nan
    df = H.handover_annual(nd, rn)
    assert df.loc[2005, "n_months"] == 3 and df.loc[2005, "rain_monsoon"] == 30.0       # handover sums what is available


def _planted(seed=3):
    rng = np.random.default_rng(seed)
    yrs = np.arange(2001, 2025)
    rain = rng.gamma(2, 150, 24)
    nd = 0.1 + 0.0004 * rain + 0.004 * (yrs - 2001) + rng.normal(0, 0.01, 24)
    return pd.DataFrame({"ndvi_monsoon": nd, "rain_monsoon": rain}, index=pd.Index(yrs, name="year"))


def test_colab_protocol_equals_handover_script_verbatim():
    """Re-run the handover's step-15 code literally and require identical numbers."""
    df = _planted().reset_index()
    raw_mk = mk.hamed_rao_modification_test(df["ndvi_monsoon"].values); raw_sen = mk.sens_slope(df["ndvi_monsoon"].values)
    rain_mk = mk.hamed_rao_modification_test(df["rain_monsoon"].values)
    X = sm.add_constant(df["rain_monsoon"]); model = sm.OLS(df["ndvi_monsoon"], X).fit()
    resid = df["ndvi_monsoon"] - model.predict(X)
    res_mk = mk.hamed_rao_modification_test(resid.values); res_sen = mk.sens_slope(resid.values)
    out = H.colab_protocol(_planted())
    assert out["ndvi"]["p"] == pytest.approx(raw_mk.p) and out["ndvi"]["slope"] == pytest.approx(raw_sen.slope)
    assert out["rain"]["p"] == pytest.approx(rain_mk.p)
    assert out["regression"]["r2"] == pytest.approx(model.rsquared)
    assert out["residual"]["p"] == pytest.approx(res_mk.p) and out["residual"]["z"] == pytest.approx(res_mk.z)
    assert out["residual"]["slope"] == pytest.approx(res_sen.slope)


def test_platform_engine_agrees_with_pymannkendall_protocol():
    assert H.engine_cross_check(_planted())["agree"]


def _row(rows, rid): return next(r for r in rows if r["id"] == rid)


def test_comparison_statuses_are_honest():
    ref = {r["id"]: r for r in H.load_reference()["reported"]}
    r = ref["ndvi_rain_residual_trend"]
    same = {"direction": "increasing", "p": 0.0059, "z": 2.753, "slope": 0.0017}
    assert H._compare(r, same)["status"] == "reproduced"
    near = {"direction": "increasing", "p": 0.02, "z": 2.3, "slope": 0.0011}
    assert H._compare(r, near)["status"] == "consistent"
    flipped = {"direction": "no significant trend", "p": 0.2, "z": 1.0, "slope": 0.0004}
    assert H._compare(r, flipped)["status"] == "not reproduced"
    assert H._compare(r, None)["status"] == "not available"
    v = ref["ndvi_annual_2001"]
    assert H._compare(v, 0.1667)["status"] == "reproduced" and H._compare(v, 0.25)["status"] == "not reproduced"


def test_reference_contains_every_handover_number():
    ids = {r["id"] for r in H.load_reference()["reported"]}
    assert {"ndvi_annual_2001", "ndvi_annual_2023", "ndvi_monsoon_trend", "rain_monsoon_trend", "ndvi_rain_residual_trend",
            "et_annual_trend", "et_rain_residual_trend", "smroot_annual_trend", "smroot_rain_residual_trend"} <= ids
    r = {x["id"]: x for x in H.load_reference()["reported"]}
    assert r["ndvi_rain_residual_trend"]["p"] == 0.0059 and r["rain_monsoon_trend"]["p"] == 0.0561 and r["et_annual_trend"]["p"] == 0.0122


def test_handover_endpoint_on_synthetic_data_never_claims_more_than_it_computes(client, sample):
    r = client.get("/api/statistics/handover-reproduction?source=sample")
    assert r.status_code == 200
    res = r.json()["result"]
    assert r.json()["meta"]["synthetic"] is True
    assert res["engine_cross_check"]["agree"] and len(res["protocol_differences"]) >= 10
    assert sum(res["counts"].values()) == len(res["rows"])
    assert "never adjusted" in " ".join(res["notes"]).lower() or "never adjusted" in " ".join(res["notes"])
    # synthetic data should NOT reproduce the real handover's numbers; if it claimed to, the comparison would be meaningless
    assert res["counts"]["reproduced"] < len(res["rows"])
    assert client.get("/api/statistics/handover-reproduction?source=processed&region=banni").status_code in (200, 404, 422)


def test_adjusted_supports_rain_season(client, sample):
    a = client.get("/api/statistics/rainfall-adjusted?source=sample&response=et&season=annual&rain_season=monsoon").json()["result"]
    b = client.get("/api/statistics/rainfall-adjusted?source=sample&response=et&season=annual&rain_season=annual").json()["result"]
    assert a["rain_season"] == "monsoon" and b["rain_season"] == "annual" and a["rainfall"] != b["rainfall"]


# ------------------------------------------------------------------ dataset catalogue facts verified against the official catalogue
def test_catalog_matches_verified_metadata():
    assert CATALOG["precip"].unit.startswith("mm/month") and "mm/hr" in CATALOG["precip"].unit
    assert CATALOG["precip"].ee_id == "NASA/GPM_L3/IMERG_MONTHLY_V07" and CATALOG["precip"].scale_m == 11132
    assert CATALOG["sm_root"].variable == "RootMoist_inst" and CATALOG["sm_surface"].variable == "SoilMoi0_10cm_inst"
    assert CATALOG["ndvi"].scale_factor == "0.0001" and CATALOG["lst_day"].scale_factor.startswith("0.02")
    assert CATALOG["et"].scale_factor.startswith("0.1") and "ndvi_qa" in CATALOG
    assert "2022" in CATALOG["water_extent"].limitations         # JRC monthly history ends 2022-01-01
    assert set(extract.EXPECTED_BANDS["NASA/GLDAS/V021/NOAH/G025/T3H"]) == {"RootMoist_inst", "SoilMoi0_10cm_inst"}


def test_imerg_conversion_gives_plausible_kutch_rainfall():
    """0.025 mm/hr (~18 mm/month) monsoon-ish rates must land in a plausible annual range; a unit mistake would not."""
    months = [P.imerg_rate_to_month_mm(0.0108, 2010, m) for m in range(1, 13)]
    assert 50 < sum(months) < 2000
    assert sum(P.imerg_rate_to_month_mm(0.0108 * 24, 2010, m) for m in range(1, 13)) > 2000      # forgetting hr->day would be flagged


# ------------------------------------------------------------------ geometry
def test_bbox_area_and_reference_not_conflated():
    r = R.get_region("banni")
    assert r["computed_bbox_area_km2"] == pytest.approx(9751.3, abs=1.0)
    assert r["geometry"]["id"] == "handover_bbox" and r["reference_area_km2"] == 2618
    assert "grassland" in r["reference_area_note"] and r["pending_geometry"]["file"].endswith("banni_grassland.geojson")


def test_polygon_area_matches_rectangle_formula():
    b = {"west": 69.0, "east": 69.5, "south": 23.4, "north": 23.6}
    ring = [[69.0, 23.4], [69.5, 23.4], [69.5, 23.6], [69.0, 23.6], [69.0, 23.4]]
    assert R.ring_area_km2(ring) == pytest.approx(R.bbox_area_km2(b), rel=2e-3)


def _write_poly(tmp_path, props, coords=None):
    coords = coords or [[[69.0, 23.4], [69.5, 23.4], [69.5, 23.6], [69.0, 23.6], [69.0, 23.4]]]
    f = tmp_path / "banni_grassland.geojson"
    f.write_text(json.dumps({"type": "Feature", "properties": props, "geometry": {"type": "Polygon", "coordinates": coords}}))
    return f


def test_polygon_validation(tmp_path):
    parent = R.get_region("banni")
    good = {"source": "Test Forest Dept survey", "retrieved": "2026-11-07", "license": "test"}
    info, err = R.load_polygon(_write_poly(tmp_path, good), parent)
    assert err is None and info["props"]["source"] == "Test Forest Dept survey"
    _, err = R.load_polygon(_write_poly(tmp_path, {"source": "x"}), parent)
    assert "missing" in err
    _, err = R.load_polygon(_write_poly(tmp_path, good, [[[10, 10], [11, 10], [11, 11], [10, 10]]]), parent)
    assert "outside" in err


def test_polygon_registers_separate_region(tmp_path, monkeypatch):
    _write_poly(tmp_path, {"source": "Test survey", "retrieved": "2026-11-07", "license": "test"})
    monkeypatch.setattr(R, "GEOMS", tmp_path)
    R._load.cache_clear()
    try:
        regs = {r["id"]: r for r in R.list_regions()}
        assert "banni" in regs and "banni_grassland" in regs
        g = regs["banni_grassland"]
        assert g["geometry"]["kind"] == "polygon" and g["geometry"]["source"] == "Test survey"
        assert g["computed_bbox_area_km2"] < 0.2 * regs["banni"]["computed_bbox_area_km2"]
        assert R.boundary_geojson(g)["properties"]["kind"] == "polygon"
        assert regs["banni"]["geometry"]["id"] == "handover_bbox"          # rectangle untouched
    finally:
        monkeypatch.undo(); R._load.cache_clear()


# ------------------------------------------------------------------ real-data schema validation & reproducibility
def _prov():
    return extract.build_provenance("precip", "banni", 2001, 2002)


def test_provenance_records_geometry_units_and_dates():
    p = _prov()
    for k in store.REQUIRED_PROVENANCE:
        assert p.get(k) not in (None, "", {}), k
    assert p["geometry"]["id"] == "handover_bbox" and p["geometry"]["area_km2"] > 9000
    assert p["unit"].startswith("mm/month") and p["ee_id"] == "NASA/GPM_L3/IMERG_MONTHLY_V07"


def test_series_schema_validation_rejects_bad_records():
    ok = {f"2001-{m:02d}": 1.0 for m in range(1, 13)}
    store.validate_series("precip", ok, _prov(), "observed")
    with pytest.raises(ValueError, match="bad month key"):
        store.validate_series("precip", {"2001-13": 1.0}, _prov(), "observed")
    with pytest.raises(ValueError, match="non-finite"):
        store.validate_series("precip", {"2001-01": float("nan")}, _prov(), "observed")
    with pytest.raises(ValueError, match="lacks provenance"):
        store.validate_series("precip", ok, {"ee_id": "x"}, "observed")
    bad = _prov(); bad["geometry"] = {}
    with pytest.raises(ValueError):
        store.validate_series("precip", ok, bad, "observed")
    with pytest.raises(ValueError):
        store.validate_series("precip", {}, _prov(), "observed")
    store.validate_series("precip", ok, {}, "synthetic")                  # synthetic exempt but still value-checked


def test_extraction_is_reproducible_and_raw_is_kept_separately(client, monkeypatch, tmp_path):
    monkeypatch.setattr(extract, "get_ee", lambda: object())
    raw = [{"month": f"2001-{m:02d}", "rate_mm_hr": 0.01 * m} for m in range(1, 13)]
    months = {r["month"]: r["rate_mm_hr"] * 24 * P.days_in_month(2001, m + 1) for m, r in enumerate(raw)}
    monkeypatch.setitem(extract.EXTRACTORS, "precip", lambda ee, region, y0, y1: (dict(months), list(raw)))
    extract.run_series_job("precip", "banni", 2001, 2001)
    a = json.loads(store.series_path("processed", "banni", "precip").read_text())
    extract.run_series_job("precip", "banni", 2001, 2001)
    b = json.loads(store.series_path("processed", "banni", "precip").read_text())
    assert a["dates"] == b["dates"] and a["values"] == b["values"]
    assert {k: v for k, v in a["provenance"].items() if k != "saved_at"} == {k: v for k, v in b["provenance"].items() if k != "saved_at"}
    files = store.list_raw("banni")
    assert any(f.startswith("precip_") for f in files)
    rawrec = json.loads((store.get_settings().data_dir / "raw" / "banni" / files[-1]).read_text())
    assert rawrec["rows"][0]["month"] == "2001-01" and rawrec["provenance"]["geometry"]["id"] == "handover_bbox"
    assert "raw" not in str(store.series_path("processed", "banni", "precip"))      # separate trees


# ------------------------------------------------------------------ data quality
def test_quality_report_finds_missing_months_and_unit_problems(client):
    # 2001-2003 with 2002-05 missing and values in mm/hr (a conversion error the report must flag)
    months = {f"{y}-{m:02d}": 0.02 for y in (2001, 2002, 2003) for m in range(1, 13) if not (y == 2002 and m == 5)}
    store.save_series("processed", "banni", "precip", months, extract.build_provenance("precip", "banni", 2001, 2003))
    q = client.get("/api/datasets/quality?variable=precip").json()["result"]
    assert q["expected_months"] == 36 and q["missing_months"] == 1 and q["missing_list"] == ["2002-05"]
    assert any("unit/conversion" in f for f in q["flags"])
    assert q["geometry"]["id"] == "handover_bbox" and q["retrieval_date"]
    # a correctly converted series is not flagged
    good = {k: P.imerg_rate_to_month_mm(0.0108, int(k[:4]), int(k[5:])) for k in months}
    store.save_series("processed", "banni", "precip", good, extract.build_provenance("precip", "banni", 2001, 2003))
    assert client.get("/api/datasets/quality?variable=precip").json()["result"]["flags"] == []
    assert client.get("/api/datasets/quality?variable=water_extent_mndwi").status_code == 404


def test_live_check_cli_stops_without_credentials(capsys):
    from app import cli
    class A: region = "banni"; start = 2001; end = 2024
    assert cli.live_check(A()) == 2
    assert "STOP" in capsys.readouterr().err



def test_bbox_area_matches_independent_ellipsoid_integration():
    """Independent check of the area code: integrate the WGS84 area element M*N*cos(phi) numerically."""
    a, f = 6378137.0, 1 / 298.257223563
    e2 = f * (2 - f)
    s, n, N = math.radians(23.20), math.radians(23.95), 20000
    h = (n - s) / N
    dA = lambda p: a * a * (1 - e2) * math.cos(p) / (1 - e2 * math.sin(p) ** 2) ** 2
    ref = sum(dA(s + (i + .5) * h) for i in range(N)) * h * math.radians(1.15) / 1e6
    assert R.get_region("banni")["computed_bbox_area_km2"] == pytest.approx(ref, abs=0.2)
    assert ref == pytest.approx(9751.3, abs=0.5)



def test_band_verifier_treats_static_assets_as_images(monkeypatch):
    """Regression: GlobalSurfaceWater is an ee.Image; asking for it as a collection failed in the live check."""
    calls = []

    class Obj:
        def __init__(self, bands): self.b = bands
        def bandNames(self): return self
        def getInfo(self): return self.b
        def first(self): return self

    class FakeEE:
        def Image(self, cid): calls.append(("Image", cid)); return Obj(["occurrence"])
        def ImageCollection(self, cid): calls.append(("Collection", cid)); return Obj(extract.EXPECTED_BANDS[cid])

    monkeypatch.setattr(extract, "get_ee", lambda: FakeEE())
    rep = extract.verify_dataset_bands()
    assert all(v["ok"] for v in rep.values())
    assert ("Image", "JRC/GSW1_4/GlobalSurfaceWater") in calls and ("Collection", "JRC/GSW1_4/GlobalSurfaceWater") not in calls


def test_earth_engine_map_callbacks_take_exactly_one_argument():
    """Regression for the first live run: ee List/ImageCollection.map() rejects callbacks with a second (even defaulted) parameter."""
    import ast, inspect
    tree = ast.parse(inspect.getsource(extract))
    callbacks = {"per_month", "prep", "f"}
    bad = [(n.name, n.lineno) for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name in callbacks
           and (len(n.args.args) != 1 or n.args.defaults or n.args.kwonlyargs or n.args.vararg)]
    assert not bad, f"map callbacks must take exactly one argument: {bad}"
