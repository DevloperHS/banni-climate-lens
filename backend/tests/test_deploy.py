"""Single-process deployment: API + built frontend. Path-traversal safety of the static fallback, health probes, logging."""
import importlib
import json
import logging

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings


@pytest.fixture()
def spa_client(tmp_path):
    static = tmp_path / "dist"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<!doctype html><title>SPA</title>", encoding="utf-8")
    (static / "assets" / "app.js").write_text("console.log('x')", encoding="utf-8")
    (static / "favicon.txt").write_text("fav", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("TOP-SECRET", encoding="utf-8")                  # outside the static dir
    s = get_settings(); old = s.static_dir; s.static_dir = static
    import app.main as m
    m = importlib.reload(m)
    try:
        yield TestClient(m.app, raise_server_exceptions=False)
    finally:
        s.static_dir = old
        importlib.reload(m)


def test_spa_fallback_assets_and_api_precedence(spa_client):
    c = spa_client
    assert c.get("/").text.startswith("<!doctype html>")
    assert c.get("/vegetation").text.startswith("<!doctype html>")                       # client-side route -> index.html
    assert c.get("/assets/app.js").text == "console.log('x')"
    assert c.get("/favicon.txt").text == "fav"
    assert c.get("/api/health").json()["status"] == "ok"                                   # API wins over the catch-all
    r = c.get("/api/does-not-exist")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    assert c.head("/api/health").status_code == 200


@pytest.mark.parametrize("path", ["/../secret.txt", "/%2e%2e/secret.txt", "/..%2fsecret.txt", "/assets/../../secret.txt", "/assets/..%5c..%5csecret.txt",
                                  "/....//secret.txt", "/%252e%252e/secret.txt"])
def test_static_fallback_never_serves_files_outside_dist(spa_client, path):
    r = spa_client.get(path)
    assert "TOP-SECRET" not in r.text


def test_security_headers_on_spa_and_api(spa_client):
    for p in ("/", "/api/health"):
        h = spa_client.get(p).headers
        assert h["x-content-type-options"] == "nosniff" and h["x-frame-options"] == "DENY"


def test_health_degrades_when_data_dir_not_writable(client, monkeypatch, tmp_path):
    s = get_settings(); old = s.data_dir
    ro = tmp_path / "file_not_dir"; ro.write_text("x")
    s.data_dir = ro                                                                         # mkdir/writes beneath a *file* fail
    try:
        h = client.get("/api/health").json()
        assert h["status"] == "degraded" and h["data_dir_writable"] is False
    finally:
        s.data_dir = old


def test_json_logging_formatter_and_redaction():
    from app.main import JsonFormatter
    from app.core.security import RedactingFilter
    rec = logging.LogRecord("gcl.x", logging.INFO, __file__, 1, "call Authorization: Bearer abc123 token=zzz", (), None)
    assert RedactingFilter().filter(rec)
    out = json.loads(JsonFormatter().format(rec))
    assert out["level"] == "INFO" and out["logger"] == "gcl.x" and "abc123" not in out["msg"] and "zzz" not in out["msg"]


def test_request_logging_has_no_query_strings(client, caplog):
    with caplog.at_level(logging.INFO, logger="gcl.api"):
        client.get("/api/health?token=supersecret")
    assert "supersecret" not in caplog.text and "/api/health" in caplog.text
