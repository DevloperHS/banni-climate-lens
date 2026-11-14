import time

from app import jobs
from app.gee import client as eeclient, extract


def _wait(jid, timeout=10):
    t = time.time()
    while time.time() - t < timeout:
        j = jobs.get(jid)
        if j["status"] not in ("queued", "running"):
            return j
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def test_failed_extraction_is_surfaced_not_replaced(client, monkeypatch):
    """If Earth Engine fails, the job reports failure and NO series is written."""
    monkeypatch.setattr(eeclient, "get_ee", lambda: object())
    monkeypatch.setattr(extract, "get_ee", lambda: object())

    def boom(ee, region, y0, y1):
        raise RuntimeError("simulated EE quota error")

    monkeypatch.setitem(extract.EXTRACTORS, "ndvi", boom)
    r = client.post("/api/datasets/jobs", json={"region": "banni", "start": 2001, "end": 2002, "tasks": [{"type": "series", "key": "ndvi"}]})
    assert r.status_code == 202
    j = _wait(r.json()["id"])
    assert j["status"] == "failed"
    assert "simulated EE quota error" in j["tasks"][0]["error"]
    assert client.get("/api/datasets?source=processed").json()["items"][0]["available"] is False


def test_successful_job_persists_processed_series_with_provenance(client, monkeypatch):
    monkeypatch.setattr(eeclient, "get_ee", lambda: object())
    monkeypatch.setattr(extract, "get_ee", lambda: object())
    monkeypatch.setitem(extract.EXTRACTORS, "precip", lambda ee, region, y0, y1: {f"{y}-{m:02d}": 10.0 for y in range(y0, y1 + 1) for m in range(1, 13)})
    r = client.post("/api/datasets/jobs", json={"region": "banni", "start": 2001, "end": 2012, "tasks": [{"type": "series", "key": "precip"}]})
    j = _wait(r.json()["id"])
    assert j["status"] == "completed"
    ts = client.get("/api/rainfall/timeseries?source=processed&agg=annual").json()
    assert ts["meta"]["synthetic"] is False and ts["meta"]["kind"] == "observed"
    assert ts["meta"]["dataset"]["ee_id"] == "NASA/GPM_L3/IMERG_MONTHLY_V07"
    assert ts["meta"]["dataset"]["retrieval_date"] and ts["meta"]["dataset"]["scale_factor"]
    assert ts["result"]["values"][0] == 120.0
    # processed data is separate from the sample store
    client.delete("/api/datasets/sample")
    assert client.get("/api/rainfall/timeseries?source=processed&agg=annual").status_code == 200


def test_unknown_job_404(client):
    assert client.get("/api/datasets/jobs/nope").status_code == 404
