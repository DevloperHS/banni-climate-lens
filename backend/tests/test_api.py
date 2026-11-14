import pytest


def test_health_and_regions(client):
    assert client.get("/api/health").json()["status"] == "ok"
    b = client.get("/api/regions").json()["items"][0]
    assert b["id"] == "banni" and b["boundary"]["geometry"]["type"] == "Polygon"
    assert b["computed_bbox_area_km2"] > 9000          # box is much larger than the 2,618 km2 reference
    assert client.get("/api/regions/nowhere").status_code == 404


def test_ee_not_configured_is_reported_not_faked(client):
    s = client.get("/api/health/earthengine").json()
    assert s["project_configured"] is False and s["setup_help"] and s["verified"] is False
    r = client.post("/api/datasets/jobs", json={"region": "banni", "start": 2001, "end": 2024,
                                                "tasks": [{"type": "series", "key": "ndvi"}]})
    assert r.status_code == 503 and r.json()["error"]["code"] == "earth_engine_unavailable"


def test_no_data_returns_clear_404_before_sample(client):
    r = client.get("/api/vegetation/timeseries?source=processed")
    assert r.status_code == 404 and r.json()["error"]["code"] == "no_data"
    assert "Earth Engine" in r.json()["error"]["message"]
    assert client.get("/api/reports/insights?source=processed").json()["findings"] == []


def test_validation_errors(client):
    assert client.get("/api/vegetation/timeseries?agg=bogus").status_code == 422
    assert client.get("/api/vegetation/timeseries?variable=precip&source=sample").status_code == 422
    assert client.get("/api/vegetation/trend?alpha=0.9").status_code == 422
    assert client.post("/api/datasets/jobs", json={"tasks": []}).status_code == 422
    assert client.post("/api/datasets/jobs", json={"start": 2024, "end": 2001, "tasks": [{"type": "series", "key": "ndvi"}]}).status_code == 422
    assert client.post("/api/statistics/trend", json={"values": [1, 2]}).status_code == 422


def test_sample_is_labelled_synthetic_everywhere(client, sample):
    assert "SYNTHETIC" in sample["disclaimer"]
    r = client.get("/api/vegetation/timeseries?source=sample&agg=annual").json()
    assert r["meta"]["synthetic"] is True and "SYNTHETIC" in r["meta"]["disclaimer"]
    cat = client.get("/api/datasets?source=sample").json()
    assert all(i["kind"] == "synthetic" for i in cat["items"] if i["available"])
    assert client.get("/api/datasets?source=processed").json()["items"][0]["available"] is False


def test_series_and_aggregations(client, sample):
    m = client.get("/api/rainfall/timeseries?source=sample&variable=precip&agg=monthly").json()["result"]
    assert len(m["x"]) == 24 * 12 and m["unit"].startswith("mm")
    ann = client.get("/api/rainfall/timeseries?source=sample&agg=annual").json()["result"]
    mon = client.get("/api/rainfall/timeseries?source=sample&agg=monsoon").json()["result"]
    assert len(ann["x"]) == 24 and all(a >= b for a, b in zip(ann["values"], mon["values"]))
    y0 = [v for d, v in zip(m["x"], m["values"]) if d.startswith("2001")]
    assert ann["values"][0] == pytest.approx(sum(y0))
    sub = client.get("/api/vegetation/timeseries?source=sample&start=2010&end=2012&agg=annual").json()["result"]
    assert sub["x"] == [2010, 2011, 2012]


def test_trend_endpoint(client, sample):
    r = client.get("/api/vegetation/trend?source=sample&agg=annual").json()
    res = r["result"]
    assert res["mk"]["direction"] == "increasing" and res["hr"]["test"].startswith("Hamed")
    assert "does not identify its cause" in res["interpretation"]
    assert r["meta"]["synthetic"] and res["limitations"]


def test_other_variable_endpoints(client, sample):
    for url in ["/api/vegetation/anomalies?source=sample&agg=annual", "/api/vegetation/anomalies?source=sample&agg=monthly",
                "/api/vegetation/monthly-pattern?source=sample", "/api/vegetation/seasonal-comparison?source=sample",
                "/api/temperature/trend?source=sample&variable=lst_night", "/api/water/trend?source=sample&variable=sm_root&agg=summer",
                "/api/water/trend?source=sample&variable=et", "/api/water/trend?source=sample&variable=water_extent",
                "/api/vegetation/variables?source=sample", "/api/water/investigations?source=sample"]:
        assert client.get(url).status_code == 200, url
    assert client.get("/api/water/trend?source=sample&variable=groundwater").status_code == 404


def test_landsat_comparison(client, sample):
    r = client.get("/api/vegetation/landsat-comparison?source=sample")
    assert r.status_code == 200
    d = r.json()["result"]
    assert d["species_discrimination"]["status"] == "not attempted" and d["correlation"]["pearson_r"] > 0.5


def test_rainfall_adjusted(client, sample):
    r = client.get("/api/statistics/rainfall-adjusted?source=sample&season=monsoon").json()["result"]
    assert r["n"] >= 20 and len(r["residuals"]) == r["n"]
    assert r["regression"]["r2"] > 0.3
    names = " ".join(s["name"] for s in r["sensitivity"])
    assert "S2" in names and "S3" in names and "S5" in names
    assert r["verdict"]["residual_direction"] in ("increasing", "decreasing", "no significant trend")
    assert "does not identify the cause" in r["verdict"]["text"]
    assert client.get("/api/statistics/rainfall-adjusted?source=sample&response=precip").status_code == 422


def test_regression_and_correlation(client, sample):
    r = client.get("/api/statistics/regression?source=sample&y=ndvi&x=precip,lst_day&agg=monsoon").json()["result"]
    assert [c["name"] for c in r["coefficients"]] == ["intercept", "precip", "lst_day"]
    assert "causes" in r["interpretation"]
    c = client.get("/api/statistics/correlation?source=sample&a=ndvi&b=precip&detrend=true").json()["result"]
    assert -1 <= c["pearson_r"] <= 1 and c["detrended"] and "causation" in c["note"]
    assert client.get("/api/statistics/regression?source=sample&x=a,b,c,d").status_code == 422


def test_arbitrary_trend(client):
    r = client.post("/api/statistics/trend", json={"values": [1, 2, 3, 4, 5, 6, 7, 8], "times": list(range(2000, 2008))}).json()["result"]
    assert r["mk"]["slope"] == pytest.approx(1.0) and r["mk"]["direction"] == "increasing"


def test_event_study(client, sample):
    r = client.get("/api/statistics/event?source=sample&variable=ndvi&event_id=biparjoy").json()
    assert "Association only" in r["result"]["interpretation"] and r["result"]["event"]["date"] == "2023-06-15"
    assert client.get("/api/statistics/event?source=sample&event_id=zzz").status_code == 404


def test_spatial(client, sample):
    L = client.get("/api/spatial/layers?source=sample").json()
    assert L["total"] == 10 and all(i["kind"] == "synthetic" for i in L["items"])
    lay = next(i for i in L["items"] if i["variable"] == "ndvi" and i["season"] == "annual")
    assert lay["crs"] == "EPSG:4326" and lay["bounds"]["west"] == pytest.approx(68.8)
    png = client.get("/api/spatial/layer.png?source=sample&variable=ndvi&season=annual&year=2010")
    assert png.status_code == 200 and png.content[:4] == b"\x89PNG"
    assert client.get("/api/spatial/layer.png?source=sample&variable=ndvi&season=annual&year=1900").status_code == 422
    assert client.get("/api/spatial/layer.png?source=sample&variable=et&season=summer&year=2010").status_code == 404
    pt = client.get("/api/spatial/pixel-trend?source=sample&variable=ndvi&season=annual").json()["result"]
    assert pt["pixels_tested"] == 60 * 90 and pt["significant_increase_fdr"] > 0
    assert pt["significant_increase_uncorrected"] >= pt["significant_increase_fdr"]
    assert "Benjamini-Hochberg" in pt["method"]
    for prod in ("class", "slope", "uncorrected"):
        assert client.get(f"/api/spatial/pixel-trend.png?source=sample&product={prod}").content[:4] == b"\x89PNG"
    tif = client.get("/api/spatial/pixel-trend.tif?source=sample")
    assert tif.status_code == 200
    import rasterio
    with rasterio.MemoryFile(tif.content) as mf, mf.open() as ds:
        assert ds.count == 5 and ds.crs.to_epsg() == 4326 and ds.descriptions[3] == "fdr_q_value"
    ins = client.get("/api/spatial/inspect?source=sample&lat=23.5&lon=69.2").json()["result"]
    assert len(ins["values"]) == 24 and "exploratory" in ins["trend_note"]
    assert client.get("/api/spatial/inspect?source=sample&lat=10&lon=10").status_code == 422
    assert client.get("/api/spatial/pixel-trend?source=sample&start=2020&end=2024").status_code == 422


def test_exports_and_reports(client, sample):
    csv = client.get("/api/reports/export/csv?source=sample&variable=ndvi&agg=annual")
    assert csv.status_code == 200 and "WARNING: SYNTHETIC" in csv.text and "# ee_id: MODIS/061/MOD13Q1" in csv.text
    assert "period,value" in csv.text
    gj = client.get("/api/reports/export/geojson?source=sample").json()
    assert gj["type"] == "Feature" and "ndvi_annual" in gj["properties"]["trends"] and "WARNING" in gj["properties"]
    ins = client.get("/api/reports/insights?source=sample").json()
    assert ins["synthetic"] and ins["synthetic_warning"] and len(ins["findings"]) >= 4
    assert all(set(f["audiences"]) == {"researcher", "authority", "student", "community"} for f in ins["findings"])
    pdf = client.get("/api/reports/pdf?source=sample")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF" and len(pdf.content) > 20000
    assert client.get("/api/reports/pdf?source=processed").status_code == 404


def test_upload_groundwater(client):
    csv = "date,value\n" + "\n".join(f"{2010 + i // 4}-{(i % 4) * 3 + 1:02d}-15,{10 + i * 0.2}" for i in range(40))
    r = client.post("/api/datasets/upload", data={"region": "banni", "key": "groundwater", "source": "sample"},
                    files={"file": ("gw.csv", csv, "text/csv")})
    assert r.status_code == 200 and r.json()["months"] == 40
    t = client.get("/api/water/trend?source=sample&variable=groundwater&agg=annual").json()
    assert t["meta"]["kind"] == "user-supplied" and t["result"]["mk"]["direction"] == "increasing"
    bad = client.post("/api/datasets/upload", data={"region": "banni", "key": "groundwater"}, files={"file": ("x.csv", "a,b\n1,2", "text/csv")})
    assert bad.status_code == 422
    nogee = client.post("/api/datasets/upload", data={"region": "banni", "key": "ndvi"}, files={"file": ("x.csv", csv, "text/csv")})
    assert nogee.status_code == 422


def test_catalog_pagination_and_cleanup(client, sample):
    c = client.get("/api/datasets?source=sample&page=2&page_size=4").json()
    assert c["total"] == len(__import__("app.core.catalog", fromlist=["CATALOG"]).CATALOG) and len(c["items"]) == 4 and c["page"] == 2
    assert client.delete("/api/datasets/sample").json()["removed_files"] > 0
    assert client.get("/api/vegetation/timeseries?source=sample").status_code == 404

