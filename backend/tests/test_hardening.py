"""Rate limiting and Content-Security-Policy."""
import pytest

from app.core import ratelimit
from app.core.config import get_settings
from app.core.security import CSP


@pytest.fixture()
def limited():
    s = get_settings(); old = s.rate_limit_per_min; s.rate_limit_per_min = 12
    yield
    s.rate_limit_per_min = old


def test_buckets():
    assert ratelimit.bucket_for("GET", "/api/regions") == "read"
    assert ratelimit.bucket_for("GET", "/api/reports/pdf") == "heavy"
    assert ratelimit.bucket_for("GET", "/api/spatial/pixel-trend.png") == "heavy"
    assert ratelimit.bucket_for("POST", "/api/datasets/jobs") == "write"
    assert ratelimit.bucket_for("DELETE", "/api/datasets/sample") == "write"


def test_read_limit_returns_429_with_retry_after_and_health_is_exempt(client, limited):
    codes = [client.get("/api/regions").status_code for _ in range(15)]
    assert codes[:12] == [200] * 12 and set(codes[12:]) == {429}
    r = client.get("/api/regions")
    assert r.status_code == 429 and int(r.headers["retry-after"]) >= 1 and r.json()["error"]["code"] == "rate_limited"
    assert client.get("/api/health").status_code == 200                  # probes must never be throttled
    assert client.post("/api/datasets/sample?region=banni").status_code == 200   # separate write bucket is independent of reads


def test_heavy_bucket_is_stricter_than_reads(client, sample, limited):
    codes = [client.get("/api/statistics/compare?source=sample&variables=ndvi,precip").status_code for _ in range(8)]
    assert codes[:5] == [200] * 5 and 429 in codes[5:]


def test_limiter_disabled_by_default_in_tests(client):
    assert get_settings().rate_limit_per_min == 0
    assert all(client.get("/api/regions").status_code == 200 for _ in range(30))


def test_csp_on_api_and_exempt_for_docs(client):
    h = client.get("/api/health").headers["content-security-policy"]
    assert h == CSP
    assert "script-src 'self'" in h and "unsafe-eval" not in h and "script-src 'self' 'unsafe-inline'" not in h
    assert "object-src 'none'" in h and "frame-ancestors 'none'" in h and "base-uri 'self'" in h and "form-action 'self'" in h and "connect-src 'self'" in h
    assert "https://tile.openstreetmap.org" in h and "https://server.arcgisonline.com" in h and "*" not in h.replace("default-src", "")
    assert "content-security-policy" not in client.get("/docs").headers          # Swagger UI needs CDN scripts
    assert "content-security-policy" not in client.get("/openapi.json").headers


# ------------------------------------------------------------------ offline field-data validator (CLI)
def _ns(kind, path):
    class A: pass
    a = A(); a.kind, a.file = kind, str(path); return a


def test_validate_csv_cli_exit_codes(tmp_path, capsys):
    from app import cli
    good = tmp_path / "g.csv"; good.write_text("lat,lon,class\n" + "\n".join(f"23.{i:02d},69.1,woody" for i in range(12)) + "\n" + "\n".join(f"23.{i:02d},69.5,grass" for i in range(12)))
    assert cli.validate_csv(_ns("ground-truth", good)) == 0 and "SUFFICIENT" in capsys.readouterr().out
    few = tmp_path / "f.csv"; few.write_text("lat,lon,class\n23.5,69.1,a\n23.6,69.2,a\n23.7,69.3,b\n")
    assert cli.validate_csv(_ns("ground-truth", few)) == 9 and "INSUFFICIENT" in capsys.readouterr().out
    empty = tmp_path / "e.csv"; empty.write_text("lat,lon,class\n")
    assert cli.validate_csv(_ns("ground-truth", empty)) == 8
    ec = tmp_path / "ec.csv"; ec.write_text("lat,lon,ec\n" + "\n".join(f"23.{i:02d},69.1,{i}" for i in range(4)))
    assert cli.validate_csv(_ns("field-ec", ec)) == 9
    ec.write_text("lat,lon,ec\n" + "\n".join(f"23.{i:02d},69.1,{i + 1}" for i in range(12)))
    assert cli.validate_csv(_ns("field-ec", ec)) == 0
    gw = tmp_path / "gw.csv"; gw.write_text("date,value\n" + "\n".join(f"{2010 + i}-05-01,{8 + i * .1}" for i in range(10)))
    assert cli.validate_csv(_ns("groundwater", gw)) == 0


def test_templates_are_header_only_so_they_cannot_be_mistaken_for_data():
    from pathlib import Path
    for f in Path(__file__).resolve().parents[2].joinpath("data-templates").glob("*.csv"):
        assert len(f.read_text().strip().splitlines()) == 1, f.name
