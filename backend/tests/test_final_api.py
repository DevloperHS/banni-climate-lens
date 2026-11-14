"""Final-phase API tests: security, pipeline control, groundwater, salinity, ground truth, masks, maps, comparison, reports."""
import io
import json
import time

import numpy as np
import pytest
import rasterio

from app import jobs
from app.core import security, store
from app.core.config import get_settings
from app.core.regions import get_region
from app.gee import cancel as cancelmod, client as eeclient, extract


# ------------------------------------------------------------------ security
@pytest.fixture()
def token():
    s = get_settings(); s.api_token = "s3cret-token"
    yield "s3cret-token"
    s.api_token = None


def test_write_endpoints_require_token_when_configured(client, token):
    assert client.post("/api/datasets/sample?region=banni").status_code == 401
    r = client.post("/api/datasets/sample?region=banni", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized" and r.headers["www-authenticate"] == "Bearer"
    assert client.post("/api/datasets/sample?region=banni", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    for method, url in [("post", "/api/datasets/jobs"), ("delete", "/api/datasets/sample"), ("post", "/api/datasets/jobs/x/cancel"),
                        ("post", "/api/datasets/jobs/x/retry"), ("post", "/api/datasets/upload"), ("post", "/api/spatial/ground-truth"), ("post", "/api/salinity/field-ec")]:
        assert getattr(client, method)(url).status_code == 401, url
    assert client.get("/api/health").status_code == 200 and client.get("/api/regions").status_code == 200          # reads stay open
    assert client.get("/api/health").json()["auth_required_for_writes"] is True


def test_no_token_configured_means_open_api(client):
    assert get_settings().api_token is None
    assert client.post("/api/datasets/sample?region=banni").status_code == 200


def test_path_traversal_and_bad_identifiers_rejected(client, sample):
    for bad in ["../../etc/passwd", "..%2f..%2fx", "banni/../x", "BANNI", "a b", ""]:
        r = client.get("/api/vegetation/timeseries", params={"region": bad, "source": "sample"})
        assert r.status_code in (404, 422), bad
    assert client.get("/api/spatial/layer.png", params={"variable": "../x", "source": "sample", "year": 2010}).status_code == 422
    assert client.get("/api/spatial/layer.png", params={"variable": "ndvi", "season": "../../x", "source": "sample"}).status_code == 422
    assert client.get("/api/vegetation/timeseries?source=../../processed").status_code == 422
    with pytest.raises(ValueError):
        store.series_path("sample", "../x", "ndvi")
    with pytest.raises(ValueError):
        store.raster_path("sample", "banni", "ndvi", "../../x")
    with pytest.raises(ValueError):
        security.safe_name("a/b")


def test_security_headers_and_cors(client):
    r = client.get("/api/health", headers={"Origin": "https://evil.example"})
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY" and r.headers["referrer-policy"] == "no-referrer"
    assert "access-control-allow-origin" not in r.headers                     # foreign origins not allowed
    ok = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    pre = client.options("/api/datasets/jobs", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "authorization"})
    assert pre.status_code == 200 and "authorization" in pre.headers["access-control-allow-headers"].lower()
    assert "PUT" not in pre.headers["access-control-allow-methods"]


def test_internal_errors_do_not_leak_details(client, monkeypatch):
    from app import services
    monkeypatch.setattr(services, "monthly", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("secret path C:/keys/ee.json")))
    r = client.get("/api/vegetation/monthly-pattern?source=sample")
    assert r.status_code == 500 and "secret" not in r.text and "C:/keys" not in r.text


def test_redaction_and_csv_sanitisation():
    assert "abc123" not in security.redact("Authorization: Bearer abc123 token=zzz&x=1")
    assert "BEGIN" not in security.redact("-----BEGIN PRIVATE KEY-----\nMIIEv\n-----END PRIVATE KEY-----")
    assert "SECRET" not in security.redact('"private_key": "SECRET"')
    assert "\n" not in security.safe_text("a\nb\r\n# injected")
    assert security.csv_cell("=HYPERLINK(\"x\")").startswith("'") and security.csv_cell("-5.2") == "-5.2" and security.csv_cell("@cmd").startswith("'")


def _gw_csv(n_wells=3):
    rows = ["date,value,well_id"]
    rng = np.random.default_rng(3)
    for w in range(n_wells):
        for y in range(2006, 2024):
            for m in (1, 5, 8, 11):
                rows.append(f"{y}-{m:02d}-10,{9 + 2 * w + 0.25 * (y - 2006) + rng.normal(0, .3):.2f},W{w}")
    return "\n".join(rows).encode()


def test_upload_limits_binary_and_note_injection(client):
    s = get_settings(); old = s.max_upload_mb; s.max_upload_mb = 1
    try:
        big = b"date,value\n" + b"2010-01-01,5\n" * 120000
        assert client.post("/api/datasets/upload", data={"region": "banni", "key": "groundwater", "source": "sample"}, files={"file": ("a.csv", big, "text/csv")}).status_code == 413
    finally:
        s.max_upload_mb = old
    assert client.post("/api/datasets/upload", data={"region": "banni", "key": "groundwater", "source": "sample"}, files={"file": ("a.csv", b"\x00\x01\x02binary", "text/csv")}).status_code == 422
    r = client.post("/api/datasets/upload", data={"region": "banni", "key": "groundwater", "source": "sample", "source_note": "CGWB\n# injected: yes\n=cmd"},
                    files={"file": ("../../evil.csv", _gw_csv(), "text/csv")})
    assert r.status_code == 200
    csv = client.get("/api/reports/export/csv?source=sample&variable=groundwater&agg=annual").text
    assert not any(l.startswith("# injected") for l in csv.splitlines())
    assert "evil" not in str(list(get_settings().data_dir.rglob("*evil*")))            # client filename never used as a path


# ------------------------------------------------------------------ health
def test_health_reports_operational_facts(client):
    h = client.get("/api/health").json()
    assert h["status"] == "ok" and h["data_dir_writable"] is True and h["disk_free_gb"] > 0 and "version" in h and h["active_jobs"] >= 0


# ------------------------------------------------------------------ groundwater
def test_groundwater_workflow(client):
    assert client.get("/api/water/groundwater/wells?source=sample").status_code in (404, 200)
    r = client.post("/api/datasets/upload", data={"region": "banni", "key": "groundwater", "source": "sample"}, files={"file": ("gw.csv", _gw_csv(), "text/csv")})
    j = r.json()
    assert r.status_code == 200 and j["validation"]["n_wells"] == 3 and j["validation"]["rows_valid"] == 3 * 18 * 4 and "below ground" in j["validation"]["unit_assumption"]
    w = client.get("/api/water/groundwater/wells?source=sample").json()["result"]
    assert set(w["wells"]) == {"W0", "W1", "W2"} and len(w["trends"]) == 3
    assert all(t["direction"] == "increasing" and t["significant_fdr"] and "deepening" in t["meaning"] for t in w["trends"]) and "measured" in w["note"].lower()
    t = client.get("/api/water/trend?source=sample&variable=groundwater&agg=annual").json()
    assert t["meta"]["kind"] == "user-supplied" and t["result"]["mk"]["direction"] == "increasing"
    bad = client.post("/api/datasets/upload", data={"region": "banni", "key": "groundwater", "source": "sample"}, files={"file": ("x.csv", b"date,value\n2020-01-01,-5\n2020-02-01,999\n", "text/csv")})
    assert bad.status_code == 422 and "outside" in bad.json()["error"]["message"]


# ------------------------------------------------------------------ salinity + ground truth + indicator
def _points_csv(n=40, seed=1, cols="lat,lon,ec", gen=None):
    rng = np.random.default_rng(seed); rows = [cols]
    for i in range(n):
        lat, lon = rng.uniform(23.25, 23.9), rng.uniform(68.85, 69.9)
        rows.append(gen(i, lat, lon) if gen else f"{lat:.5f},{lon:.5f},{rng.uniform(0.5, 20):.2f}")
    return "\n".join(rows).encode()


def test_salinity_unvalidated_without_field_data_then_validated_statistics(client, sample):
    v = client.get("/api/salinity/validation?source=sample").json()["result"]
    assert v["status"] == "no_field_data" and "UNVALIDATED" in v["message"]
    up = client.post("/api/salinity/field-ec", data={"region": "banni", "source": "sample"}, files={"file": ("ec.csv", _points_csv(40), "text/csv")})
    assert up.status_code == 200 and up.json()["rows_valid"] == 40
    v = client.get("/api/salinity/validation?source=sample").json()["result"]
    assert v["status"] == "computed" and v["n"] == 40 and -1 <= v["spearman_rho"] <= 1 and "limitations" in v
    few = client.post("/api/salinity/field-ec", data={"region": "banni", "source": "sample"}, files={"file": ("ec.csv", _points_csv(5), "text/csv")})
    assert few.status_code == 200
    assert client.get("/api/salinity/validation?source=sample").json()["result"]["status"] == "insufficient"
    assert client.post("/api/salinity/field-ec", data={"region": "banni", "source": "sample"}, files={"file": ("ec.csv", b"lat,lon,ec\n1,2,-5\n", "text/csv")}).status_code == 422
    assert client.get("/api/salinity/trend?source=sample&variable=salinity_index&agg=annual").status_code == 200


def test_ground_truth_absent_means_no_species_claims(client, sample):
    st = client.get("/api/spatial/ground-truth/status?source=sample").json()
    assert st["available"] is False and "NOT possible" in st["message"] and "10 per class" in st["required"]
    ev = client.get("/api/spatial/evergreen?source=sample").json()["result"]
    assert "EXPLORATORY" in ev["status"] and "not a species classification" in ev["status"] and ev["ground_truth"]["available"] is False
    assert ev["pixels_tested"] > 0 and "Prosopis" in ev["interpretation"] and "cannot tell them apart" in ev["interpretation"]
    r = client.get("/api/spatial/indicator-validation?source=sample")
    assert r.status_code == 404 and r.json()["error"]["code"] == "no_ground_truth"
    assert client.get("/api/spatial/evergreen.png?source=sample&product=mean").content[:4] == b"\x89PNG"
    assert client.get("/api/spatial/evergreen.png?source=sample&product=trend").content[:4] == b"\x89PNG"


def test_ground_truth_upload_and_indicator_validation(client, sample):
    def gen(i, lat, lon):
        patch = i % 2 == 0
        la = 23.70 + np.random.default_rng(i).normal(0, .02) if patch else 23.35
        lo = 69.12 + np.random.default_rng(i + 99).normal(0, .03) if patch else 69.55 + 0.003 * i
        return f"{la:.5f},{lo:.5f},{'woody' if patch else 'grass'}"
    r = client.post("/api/spatial/ground-truth", data={"region": "banni", "source": "sample"}, files={"file": ("gt.csv", _points_csv(60, gen=gen, cols="lat,lon,class"), "text/csv")})
    assert r.status_code == 200 and set(r.json()["class_counts"]) == {"woody", "grass"}
    assert client.get("/api/spatial/ground-truth/status?source=sample").json()["available"] is True
    v = client.get("/api/spatial/indicator-validation?source=sample").json()["result"]
    pair = v["pairs"][0]
    assert pair["auc"] is None or 0.5 <= pair["auc"] <= 1 and "higher_class" in pair
    assert any("not a validated species map" in c for c in v["caveats"])
    one = client.post("/api/spatial/ground-truth", data={"region": "banni", "source": "sample"}, files={"file": ("gt.csv", b"lat,lon,class\n23.5,69.1,a\n23.6,69.2,a\n", "text/csv")})
    assert one.status_code == 422


# ------------------------------------------------------------------ masks, maps, agreement, QC
def test_rann_water_mask_in_pixel_trends(client, sample):
    base = client.get("/api/spatial/pixel-trend?source=sample&variable=ndvi&season=annual").json()["result"]
    m = client.get("/api/spatial/pixel-trend?source=sample&variable=ndvi&season=annual&mask=rann_water&water_thr=10").json()["result"]
    assert base["mask"] is None and m["mask"]["pixels_masked"] > 0 and m["mask"]["threshold_pct"] == 10 and m["mask"]["resampled_to_stack_grid"] is False
    assert m["pixels_tested"] < base["pixels_tested"]
    assert m["geometry_id"] == "handover_bbox" and m["raster_qc"]["ok"]
    assert client.get("/api/spatial/pixel-trend.png?source=sample&mask=rann_water").content[:4] == b"\x89PNG"
    assert client.get("/api/spatial/pixel-trend?source=sample&mask=bogus").status_code == 422
    assert client.get("/api/spatial/pixel-trend?source=processed&mask=rann_water").status_code == 404
    tif = client.get("/api/spatial/pixel-trend.tif?source=sample&mask=rann_water")
    with rasterio.MemoryFile(tif.content) as mf, mf.open() as ds:
        assert "water_mask" in ds.tags() and ds.tags()["geometry_id"] == "handover_bbox"


def test_difference_export_tif_and_qc(client, sample):
    d = client.get("/api/spatial/difference?source=sample&variable=ndvi&season=annual&a_start=2001&a_end=2005&b_start=2020&b_end=2024").json()["result"]
    assert d["mean_change"] > 0 and d["pct_increase"] > 90 and "not a significance test" in d["note"]
    assert client.get("/api/spatial/difference.png?source=sample").content[:4] == b"\x89PNG"
    assert client.get("/api/spatial/difference?source=sample&a_start=1900&a_end=1901").status_code == 422
    for kind in ("layer", "trend", "difference"):
        r = client.get(f"/api/spatial/export.png?source=sample&variable=ndvi&season=annual&kind={kind}&year=2010")
        assert r.status_code == 200 and r.content[:4] == b"\x89PNG" and len(r.content) > 20000 and "attachment" in r.headers["content-disposition"]
    t = client.get("/api/spatial/layer.tif?source=sample&variable=ndvi&season=annual&year=2015")
    with rasterio.MemoryFile(t.content) as mf, mf.open() as ds:
        assert ds.crs.to_epsg() == 4326 and ds.count == 1 and ds.tags()["kind"] == "synthetic" and abs(ds.bounds.left - 68.8) < 1e-6
    q = client.get("/api/spatial/qc?source=sample&variable=ndvi&season=annual").json()["result"]
    assert q["ok"] and q["crs"].endswith("4326") and q["pixel_size_m_approx"][0] > 1000
    assert client.get("/api/spatial/layer.tif?source=sample&variable=ndvi&season=annual&year=1900").status_code == 422


def test_layers_exclude_static_mask_and_include_new_stacks(client, sample):
    items = client.get("/api/spatial/layers?source=sample").json()["items"]
    keys = {(i["variable"], i["season"]) for i in items}
    assert ("ndvi", "summer") in keys and ("ndvi_landsat", "peak") in keys and not any(s == "static" for _, s in keys)


def test_trend_agreement_between_resolutions(client, sample):
    r = client.get("/api/spatial/trend-agreement?source=sample&coarse=ndvi&coarse_season=annual&fine=ndvi_landsat&fine_season=peak")
    assert r.status_code == 200
    a = r.json()["result"]
    assert a["n_years"] == 24 and a["spearman_rho"] > 0.3 and a["sign_agreement_pct"] > 60 and "does not prove" in a["note"]
    assert client.get("/api/spatial/trend-agreement?source=sample&fine=nope").status_code == 422


# ------------------------------------------------------------------ multi-variable comparison, region comparison, events, seasonal NDVI
def test_compare_endpoint(client, sample):
    r = client.get("/api/statistics/compare?source=sample&variables=ndvi,precip,lst_day,et&agg=monsoon&response=ndvi").json()
    res = r["result"]
    assert res["n"] >= 20 and len(res["pearson"]) == 4 and res["regression"]["response"] == "ndvi" and "vif" in res["regression"]
    assert res["prediction"]["r2_loo_cv"] <= res["prediction"]["r2_in_sample"] + 1e-9
    assert "cannot establish causation" in res["causation_note"] and "PREDICTION" in res["statement"] and r["meta"]["synthetic"] is True
    assert client.get("/api/statistics/compare?source=sample&variables=ndvi").status_code == 422
    assert client.get("/api/statistics/compare?source=sample&variables=ndvi,ndvi").status_code == 422
    assert client.get("/api/statistics/compare?source=sample&variables=ndvi,bogus").status_code == 422
    d = client.get("/api/statistics/compare?source=sample&variables=ndvi,precip&agg=annual&detrend=true&response=").json()["result"]
    assert d["detrended"] is True and "regression" not in d


def test_region_comparison_keeps_geometries_separate(client, sample):
    r = client.get("/api/statistics/region-comparison?source=sample&regions=banni,banni_grassland&variable=ndvi&agg=monsoon").json()["result"]
    items = {i["region"]: i for i in r["items"]}
    assert items["banni"]["status"] == "ok" and items["banni"]["geometry"]["id"] == "handover_bbox"
    assert items["banni_grassland"]["status"] == "unknown region"
    assert r["pending_geometries"] and "rectangle includes non-grassland" in r["note"]


def test_event_with_rain_adjustment(client, sample):
    r = client.get("/api/statistics/event?source=sample&variable=ndvi&event_id=biparjoy&adjust_rain=true").json()["result"]
    assert r["rain_adjusted"] and "attributes" in r["rain_adjusted"]["interpretation"] and r["rain_adjusted"]["adjustment"]["r2_non_event_years"] > 0
    assert client.get("/api/statistics/event?source=sample&variable=precip&adjust_rain=true").json()["result"]["rain_adjusted"] is None


def test_seasonal_ndvi_with_previous_monsoon_control(client, sample):
    r = client.get("/api/statistics/rainfall-adjusted?source=sample&response=ndvi&season=summer&rain_season=prev_monsoon").json()["result"]
    assert r["rain_season"] == "prev_monsoon" and r["n"] >= 20
    s = client.get("/api/vegetation/seasonal-comparison?source=sample&variable=ndvi").json()["result"]["seasons"]
    assert {"summer", "monsoon", "annual"} <= set(s) and "trend" in s["summer"]


# ------------------------------------------------------------------ pipeline: progress, cancel, retry, logs, gate, recovery
def _wait(jid, status=None, timeout=15):
    t = time.time()
    while time.time() - t < timeout:
        j = jobs.get(jid)
        if (status and j["status"] == status) or (not status and j["status"] in jobs.TERMINAL):
            return j
        time.sleep(0.03)
    raise AssertionError(f"job stuck in {jobs.get(jid)['status']}")


@pytest.fixture()
def fake_ee(monkeypatch):
    monkeypatch.setattr(eeclient, "get_ee", lambda: object())
    monkeypatch.setattr(extract, "get_ee", lambda: object())


def _months(y0, y1, v=1.0):
    return {f"{y}-{m:02d}": v for y in range(y0, y1 + 1) for m in range(1, 13)}


def test_job_progress_log_and_task_detail(client, fake_ee, monkeypatch):
    monkeypatch.setitem(extract.EXTRACTORS, "precip", lambda ee, r, a, b: _months(a, b))
    monkeypatch.setitem(extract.EXTRACTORS, "et", lambda ee, r, a, b: _months(a, b, 5.0))
    j = client.post("/api/datasets/jobs", json={"region": "banni", "start": 2001, "end": 2005, "tasks": [{"type": "series", "key": "precip"}, {"type": "series", "key": "et"}]}).json()
    done = _wait(j["id"])
    assert done["status"] == "completed" and done["progress"] == {"done": 2, "total": 2, "percent": 100} and [t["status"] for t in done["tasks"]] == ["done", "done"]
    assert done["tasks"][0]["attempts"] == 1 and done["tasks"][0]["detail"]["n_months"] == 60
    log = client.get(f"/api/datasets/jobs/{j['id']}/log").json()["log"]
    assert "start series:precip" in log and "done series:et" in log and "job completed" in log
    assert client.get("/api/datasets/jobs/nope/log").status_code == 404


def test_completeness_gate_stores_nothing(client, fake_ee, monkeypatch):
    for k in ("ndvi_qa",):
        p = store.series_path("processed", "banni", k)
        p.unlink(missing_ok=True)
    monkeypatch.setitem(extract.EXTRACTORS, "ndvi_qa", lambda ee, r, a, b: {f"{a}-01": 0.3, f"{a}-02": 0.3})        # 2 of 120 months
    j = client.post("/api/datasets/jobs", json={"region": "banni", "start": 2001, "end": 2010, "tasks": [{"type": "series", "key": "ndvi_qa"}]}).json()
    done = _wait(j["id"])
    assert done["status"] == "failed" and "completeness gate" in done["tasks"][0]["error"] and "NOTHING was stored" in done["tasks"][0]["error"]
    assert not store.series_path("processed", "banni", "ndvi_qa").exists()
    log = client.get(f"/api/datasets/jobs/{j['id']}/log").json()["log"]
    assert "Traceback" in log


def test_cancel_running_job_writes_nothing_and_retry_runs_only_unfinished(client, fake_ee, monkeypatch):
    store.series_path("processed", "banni", "sm_root").unlink(missing_ok=True)
    started = {"n": 0}
    calls = {"et": 0}

    def slow(ee, r, a, b):
        started["n"] += 1
        for _ in range(400):
            cancelmod.check_cancel(); time.sleep(0.01)
        return _months(a, b)

    def et(ee, r, a, b):
        calls["et"] += 1
        return _months(a, b, 4.0)

    monkeypatch.setitem(extract.EXTRACTORS, "sm_root", slow)
    monkeypatch.setitem(extract.EXTRACTORS, "et", et)
    j = client.post("/api/datasets/jobs", json={"region": "banni", "start": 2001, "end": 2003, "tasks": [{"type": "series", "key": "et"}, {"type": "series", "key": "sm_root"}]}).json()
    t = time.time()
    while started["n"] == 0 and time.time() - t < 10:
        time.sleep(0.02)
    c = client.post(f"/api/datasets/jobs/{j['id']}/cancel")
    assert c.status_code == 200
    done = _wait(j["id"])
    assert done["status"] == "cancelled" and done["tasks"][0]["status"] == "done" and done["tasks"][1]["status"] == "cancelled"
    assert not store.series_path("processed", "banni", "sm_root").exists()                     # cancelled task wrote nothing
    # retry: the finished ET task must not be repeated
    monkeypatch.setitem(extract.EXTRACTORS, "sm_root", lambda ee, r, a, b: _months(a, b, 50.0))
    assert client.post(f"/api/datasets/jobs/{j['id']}/retry").status_code == 202
    re = _wait(j["id"], "completed")
    assert calls["et"] == 1 and re["tasks"][1]["status"] == "done" and re["tasks"][1]["attempts"] == 2 and store.series_path("processed", "banni", "sm_root").exists()
    assert client.post(f"/api/datasets/jobs/{j['id']}/retry").status_code == 409            # completed jobs cannot be retried
    assert client.post("/api/datasets/jobs/zzz/cancel").status_code == 404


def test_cancel_queued_job_and_recovery_after_restart(client, fake_ee, monkeypatch, tmp_path):
    jobs._jobs["old1"] = {"id": "old1", "status": "running", "created": "2026-01-01T00:00:00+00:00", "spec": {}, "error": None, "cancel_requested": False,
                          "tasks": [{"id": 0, "label": "series:ndvi", "type": "series", "key": "ndvi", "status": "done", "attempts": 1, "error": None},
                                    {"id": 1, "label": "series:precip", "type": "series", "key": "precip", "status": "running", "attempts": 1, "error": None}], "progress": {}}
    jobs._persist()
    leftover = get_settings().data_dir / "processed" / "series" / "banni" / "ndvi.json.tmp"
    leftover.parent.mkdir(parents=True, exist_ok=True); leftover.write_text("{partial")
    jobs._jobs.pop("old1")
    jobs.recover()
    j = jobs.get("old1")
    assert j["status"] == "interrupted" and j["tasks"][1]["status"] == "interrupted" and j["tasks"][0]["status"] == "done" and "retry" in j["error"]
    assert not leftover.exists()                                                                  # partial files removed at start-up
    assert client.post("/api/datasets/jobs/old1/cancel").json()["status"] == "interrupted"


def test_atomic_write_leaves_no_temp_files(client, fake_ee, monkeypatch):
    monkeypatch.setitem(extract.EXTRACTORS, "lst_day", lambda ee, r, a, b: (_months(a, b, 30.0), [{"x": 1}]))
    extract.run_series_job("lst_day", "banni", 2001, 2003)
    assert not list(get_settings().data_dir.rglob("*.tmp"))
    assert store.series_path("processed", "banni", "lst_day").exists() and any(f.startswith("lst_day_") for f in store.list_raw("banni"))


# ------------------------------------------------------------------ job request validation for new datasets
def test_job_validation_for_new_keys(client, fake_ee):
    ok = lambda t: client.post("/api/datasets/jobs", json={"tasks": [t]}).status_code
    assert ok({"type": "stack", "key": "water_occurrence", "season": "static"}) == 202
    assert ok({"type": "stack", "key": "water_occurrence", "season": "annual"}) == 422
    assert ok({"type": "stack", "key": "ndvi", "season": "static"}) == 422
    assert ok({"type": "series", "key": "water_occurrence"}) == 422
    assert ok({"type": "stack", "key": "salinity_index", "season": "summer"}) == 202
    assert ok({"type": "stack", "key": "ndvi_landsat", "season": "peak"}) == 202
    assert ok({"type": "series", "key": "salinity_index"}) == 202
    assert ok({"type": "series", "key": "water_extent_mndwi"}) == 202
    assert ok({"type": "stack", "key": "water_extent", "season": "annual"}) == 422
    assert ok({"type": "series", "key": "groundwater"}) == 422


# ------------------------------------------------------------------ tiling and mosaics
def test_grid_and_tile_plan_cover_region_exactly():
    b = {"west": 68.8, "east": 69.95, "south": 23.2, "north": 23.95}
    for scale, bands in [(250, 24), (120, 24), (1000, 24), (250, 1)]:
        g = extract.grid_for(b, scale)
        tiles = extract.plan_tiles(g, bands)
        covered = np.zeros((g["H"], g["W"]), int)
        for t in tiles:
            covered[t["r0"]:t["r1"], t["c0"]:t["c1"]] += 1
            assert (t["c1"] - t["c0"]) * (t["r1"] - t["r0"]) * bands * 4 * 1.15 <= extract.MAX_TILE_BYTES
        assert (covered == 1).all(), (scale, bands)
        assert g["dx"] == pytest.approx(scale / 111319.49)
    assert len(extract.plan_tiles(extract.grid_for(b, 250), 1)) == 1 and len(extract.plan_tiles(extract.grid_for(b, 120), 24)) > 1
    assert extract.grid_for(b, 250) == extract.grid_for(dict(b), 250)           # same scale -> identical grid -> aligned layers


def test_tile_mosaic_roundtrip(tmp_path):
    from rasterio.crs import CRS
    from rasterio.transform import from_origin
    rng = np.random.default_rng(0)
    full = rng.normal(size=(3, 20, 30)).astype("float32")
    dx = 0.01
    paths = []
    for i, (c0, c1) in enumerate([(0, 12), (12, 30)]):
        p = tmp_path / f"t{i}.tif"
        with rasterio.open(p, "w", driver="GTiff", height=20, width=c1 - c0, count=3, dtype="float32", crs=CRS.from_epsg(4326),
                           transform=from_origin(68.8 + c0 * dx, 23.95, dx, dx), nodata=np.nan) as ds:
            ds.write(full[:, :, c0:c1])
            for k in range(3):
                ds.set_band_description(k + 1, f"y{2001 + k}")
        paths.append(p)
    out = tmp_path / "m.tif"
    extract.mosaic_tiles(paths, out)
    with rasterio.open(out) as ds:
        assert ds.shape == (20, 30) and ds.count == 3 and list(ds.descriptions) == ["y2001", "y2002", "y2003"]
        assert np.allclose(ds.read(), full) and abs(ds.transform.a - dx) < 1e-12


# ------------------------------------------------------------------ reports
def test_report_manifest_and_pdf_contents(client, sample):
    m = client.get("/api/reports/manifest?source=sample").json()
    assert m["ready"] and m["synthetic"] and all(s["available"] for s in m["sections"])
    pdf = client.get("/api/reports/pdf?source=sample")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF" and len(pdf.content) > 100_000
    from pypdf import PdfReader
    text = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf.content)).pages)
    for needle in ["1. Study region and period", "3. Datasets and provenance", "4. Processing and statistical methodology", "5. Trend estimates", "95% CI",
                   "6. Rainfall-adjusted vegetation analysis", "7. Reproduction of the research handover", "8. Maps", "9. Data quality", "10. Interpretation and limitations",
                   "11. References", "Hamed, K.H. and Rao", "Benjamini", "doi:10.5067/MODIS/MOD13Q1.061", "SYNTHETIC SAMPLE DATA", "handover_bbox", "not the Banni grassland boundary"]:
        assert needle in text, needle
    nomaps = client.get("/api/reports/pdf?source=sample&maps=false")
    assert len(nomaps.content) < len(pdf.content)
    assert client.get("/api/reports/pdf?source=processed&region=banni").status_code in (404, 200)


def test_report_degrades_honestly_when_data_missing(client):
    from app import reporting
    client.delete("/api/datasets/sample")
    m = reporting.manifest("banni", "sample")
    assert not m["ready"] and not any(s["available"] for s in m["sections"])
    r = client.get("/api/reports/pdf?source=sample")
    assert r.status_code == 404 and r.json()["error"]["code"] == "no_data"


# ------------------------------------------------------------------ coverage-aware completeness, land cover, GRACE
def test_completeness_gate_counts_only_product_coverage_years(client, fake_ee, monkeypatch):
    # Landsat 8 MNDWI starts in 2013: 2013-2024 cloud-free months must pass even though 2001-2012 cannot exist
    monkeypatch.setitem(extract.EXTRACTORS, "water_extent_mndwi", lambda ee, r, a, b: _months(2013, b, 40.0))
    res = extract.run_series_job("water_extent_mndwi", "banni", 2001, 2024)
    assert res["n_months"] == 144 and store.series_path("processed", "banni", "water_extent_mndwi").exists()
    # ... but sparse months inside the covered years are still rejected
    store.series_path("processed", "banni", "water_extent_mndwi").unlink()
    monkeypatch.setitem(extract.EXTRACTORS, "water_extent_mndwi", lambda ee, r, a, b: {f"{y}-01": 1.0 for y in range(2013, 2025)})
    with pytest.raises(RuntimeError, match="completeness gate"):
        extract.run_series_job("water_extent_mndwi", "banni", 2001, 2024)
    assert not store.series_path("processed", "banni", "water_extent_mndwi").exists()


class _FakeColl:
    def __init__(self, feats):
        self.feats = feats

    def select(self, *a):
        return self

    def filterDate(self, *a):
        return self

    def map(self, f):
        return self

    def getInfo(self):
        return {"features": [{"properties": p} for p in self.feats]}


class _FakeEE:
    def __init__(self, feats):
        self.ImageCollection = lambda cid: _FakeColl(feats)
        self.Geometry = type("G", (), {"Rectangle": staticmethod(lambda *a, **k: None)})


def _ms(y, m=1, d=1):
    from datetime import datetime, timezone
    return datetime(y, m, d, tzinfo=timezone.utc).timestamp() * 1000


def test_landcover_share_and_job(client, fake_ee, monkeypatch):
    feats = [{"t": _ms(2001), "hist": {"10": 60.0, "7": 30.0, "17": 10.0}}, {"t": _ms(2002), "hist": {"10": 50.0, "6": 25.0, "7": 25.0}}]
    out, raw = extract.annual_landcover_share(_FakeEE(feats), get_region("banni"), 2001, 2002, "lc_shrubland")
    assert out == {"2001-01": 30.0, "2002-01": 50.0} and raw[0]["total"] == 100.0
    g, _ = extract.annual_landcover_share(_FakeEE(feats), get_region("banni"), 2001, 2002, "lc_grassland")
    assert g == {"2001-01": 60.0, "2002-01": 50.0}
    monkeypatch.setitem(extract.EXTRACTORS, "lc_grassland", lambda ee, r, a, b: {f"{y}-01": 55.0 for y in range(a, b + 1)})
    assert extract.run_series_job("lc_grassland", "banni", 2001, 2024)["n_months"] == 24
    r = client.get("/api/landcover/timeseries?variable=lc_grassland&agg=annual").json()["result"]
    assert r["x"][0] == 2001 and len(r["x"]) == 24 and r["values"][0] == 55.0
    assert client.post("/api/datasets/jobs", json={"tasks": [{"type": "stack", "key": "lc_grassland", "season": "annual"}]}).status_code == 422
    store.series_path("processed", "banni", "lc_grassland").unlink()


def test_grace_monthly_mean_of_solutions_and_gap(client, fake_ee):
    feats = [{"t": _ms(2003, 1, 3), "v": -2.0}, {"t": _ms(2003, 1, 20), "v": -4.0}, {"t": _ms(2003, 2, 10), "v": None}, {"t": _ms(2003, 3, 10), "v": 1.5}]
    out, raw = extract.monthly_grace(_FakeEE(feats), get_region("banni"), 2003, 2003)
    assert out == {"2003-01": -3.0, "2003-03": 1.5} and len(raw) == 4
    assert client.post("/api/datasets/jobs", json={"tasks": [{"type": "stack", "key": "grace_tws", "season": "annual"}]}).status_code == 422
    assert client.post("/api/datasets/jobs", json={"tasks": [{"type": "stack", "key": "lst_night", "season": "summer"}]}).status_code == 202


# ------------------------------------------------------------------ trend dashboards
def test_dashboards_are_computed_from_stored_data_and_flag_missing_factors(client, sample):
    r = client.get("/api/dashboards/rain_green?source=sample")
    assert r.status_code == 200
    d, meta = r.json()["result"], r.json()["meta"]
    assert meta["synthetic"] is True and d["question"].startswith("Is Banni greener")
    ndvi = next(c for c in d["cards"] if c["key"] == "ndvi" and c["aggregation"] == "monsoon")
    t = client.get("/api/vegetation/trend?source=sample&agg=monsoon").json()["result"]["hr"]
    assert ndvi["available"] and ndvi["p"] == t["p"] and ndvi["slope"] == t["slope"] and ndvi["test"].startswith("Hamed-Rao")
    rr = d["derived"][0]
    assert rr["available"] and len(rr["series"]["observed"]) == len(rr["series"]["predicted"]) and rr["year_term"] is not None
    assert "precip:monsoon" in d["yearly"]["columns"] and len(d["yearly"]["columns"]["precip:monsoon"]) == len(d["yearly"]["years"])
    assert {(l["variable"], l["season"]) for l in d["layers"]} >= {("ndvi", "monsoon"), ("precip", "monsoon")}
    assert any("Before" not in x and "NDVI measures green cover" in x for x in d["limits"])
    assert all(s["url"].startswith("https://") for s in d["sources"])
    w = client.get("/api/dashboards/water_heat?source=sample").json()["result"]
    gw = next(c for c in w["cards"] if c["key"] == "groundwater")
    assert gw["available"] is False and "India-WRIS" in gw["reason"]           # never filled in
    assert client.get("/api/dashboards/nope").status_code == 422


# ------------------------------------------------------------------ Aqua / EVI checks (research brief s.7)
def test_sensor_index_checks_use_common_years_and_same_tests(client, sample):
    r = client.get("/api/statistics/sensor-index-checks?source=sample")
    assert r.status_code == 200
    res, meta = r.json()["result"], r.json()["meta"]
    assert meta["synthetic"] is True
    assert res["period"] == "2002-2024"                         # toy Aqua starts Jul 2002 like the real record
    assert [s["season"] for s in res["seasons"]] == ["monsoon", "summer"]
    for s in res["seasons"]:
        assert [x["key"] for x in s["rows"]] == ["ndvi", "ndvi_aqua", "evi"] and all(x["available"] for x in s["rows"])
        assert s["agreement"]["status"] in ("agree", "disagree")
    # the Terra row is the ordinary trend test restricted to the common years: nothing special-cased
    terra = res["seasons"][0]["rows"][0]
    t = client.get("/api/vegetation/trend?source=sample&agg=monsoon&start=2002&end=2024").json()["result"]["hr"]
    assert terra["raw_trend"]["p"] == t["p"] and terra["raw_trend"]["slope"] == t["slope"] and terra["n"] == t["n"] == 23
    adj = client.get("/api/statistics/rainfall-adjusted?source=sample&season=monsoon&start=2002&end=2024").json()["result"]
    assert terra["residual_trend"]["p"] == adj["residual_trend"]["hr"]["p"]
    assert res["terra_aqua_monsoon"]["n"] == 23 and res["terra_aqua_monsoon"]["pearson_r"] > 0.9
    evi = res["seasons"][0]["rows"][2]
    assert evi["slope_unit"] == "EVI per year"
    # the dashboard carries the same block and links both extra datasets
    d = client.get("/api/dashboards/rain_green?source=sample").json()["result"]
    assert d["checks"]["seasons"][0]["rows"][1]["residual_trend"] == res["seasons"][0]["rows"][1]["residual_trend"]
    assert {"ndvi_aqua", "evi"} <= {s["key"] for s in d["sources"]}
    assert any(s["url"].endswith("MODIS_061_MYD13Q1") for s in d["sources"])


def test_sensor_index_checks_name_a_missing_series_instead_of_filling_it(client, sample):
    from app.core import store
    store.series_path("sample", "banni", "ndvi_aqua").unlink()
    res = client.get("/api/statistics/sensor-index-checks?source=sample").json()["result"]
    assert res["period"] == "2001-2024" and res["terra_aqua_monsoon"] is None
    for s in res["seasons"]:
        aqua = next(x for x in s["rows"] if x["key"] == "ndvi_aqua")
        assert aqua["available"] is False and "ndvi_aqua" in aqua["reason"]
        assert "ndvi_aqua" in s["agreement"]["missing"] and s["agreement"]["status"] != "agree"


def test_agreement_rule_is_direction_and_significance():
    from app.services import _agreement
    def row(key, direction, sig, p=0.01):
        return {"key": key, "label": key, "available": True, "residual_trend": {"direction": direction, "significant": sig, "p": p}}
    ok = _agreement([row("ndvi", "increasing", True), row("ndvi_aqua", "increasing", True), row("evi", "increasing", True)], 0.05)
    assert ok["status"] == "agree" and ok["differ"] == []
    bad = _agreement([row("ndvi", "increasing", True), row("ndvi_aqua", "no trend", False, 0.3), row("evi", "increasing", True)], 0.05)
    assert bad["status"] == "disagree" and bad["differ"] == ["ndvi_aqua"] and "differs" in bad["text"]
    part = _agreement([row("ndvi", "increasing", True), {"key": "ndvi_aqua", "label": "a", "available": False}, row("evi", "increasing", True)], 0.05)
    assert part["status"] == "partial" and part["missing"] == ["ndvi_aqua"]
    assert _agreement([{"key": "ndvi", "label": "t", "available": False}], 0.05)["status"] == "unavailable"


def test_aqua_and_evi_are_extractable_series_not_stacks(client):
    from app.gee.extract import EXTRACTORS, COVERAGE_YEARS, EXPECTED_BANDS
    from app.verify_metadata import EXPECTATIONS
    assert {"ndvi_aqua", "evi"} <= set(EXTRACTORS) and COVERAGE_YEARS["ndvi_aqua"] == (2002, None)
    assert "EVI" in EXPECTED_BANDS["MODIS/061/MOD13Q1"] and "NDVI" in EXPECTED_BANDS["MODIS/061/MYD13Q1"]
    assert EXPECTATIONS["MODIS/061/MYD13Q1"][2]["EVI"]["scale"] == 0.0001
    assert client.post("/api/datasets/jobs", json={"tasks": [{"type": "series", "key": "ndvi_aqua"}]}).status_code != 422   # valid task (503 here: no EE in tests)
    assert client.post("/api/datasets/jobs", json={"tasks": [{"type": "stack", "key": "evi", "season": "annual"}]}).status_code == 422   # series-only check


def test_significant_only_trend_png_hides_non_significant_pixels(client, sample):
    from PIL import Image
    a = np.array(Image.open(io.BytesIO(client.get("/api/spatial/pixel-trend.png?source=sample&variable=ndvi&season=annual&product=class").content)))
    b = np.array(Image.open(io.BytesIO(client.get("/api/spatial/pixel-trend.png?source=sample&variable=ndvi&season=annual&product=significant").content)))
    assert (a[..., 3] > 0).sum() > (b[..., 3] > 0).sum() and set(np.unique(b[..., 3])) <= {0, 220}
