"""Automated verification of our dataset assumptions against Google's official Earth Engine STAC records.

    python -m app.cli verify-metadata

Fetches the catalogue JSON for every collection we use and checks bands, units, scale factors, resolution and
temporal coverage against `EXPECTATIONS`. Needs network access but NOT Earth Engine credentials.
"""
from __future__ import annotations
import json
import urllib.request
from datetime import date

STAC = "https://storage.googleapis.com/earthengine-stac/catalog/{provider}/{slug}.json"

# collection -> (provider folder, slug, {band: {"units": ..., "scale": ...}}, gsd, must_cover_to)
EXPECTATIONS = {
    "MODIS/061/MOD13Q1": ("MODIS", "MODIS_061_MOD13Q1", {"NDVI": {"scale": 0.0001}, "EVI": {"scale": 0.0001}, "SummaryQA": {}}, 250, "2024-12-31"),
    "MODIS/061/MYD13Q1": ("MODIS", "MODIS_061_MYD13Q1", {"NDVI": {"scale": 0.0001}, "EVI": {"scale": 0.0001}}, 250, "2024-12-31"),
    "NASA/GPM_L3/IMERG_MONTHLY_V07": ("NASA", "NASA_GPM_L3_IMERG_MONTHLY_V07", {"precipitation": {"units": "mm/hr"}}, 11132, "2024-12-31"),
    "MODIS/061/MOD11A2": ("MODIS", "MODIS_061_MOD11A2", {"LST_Day_1km": {"units": "K", "scale": 0.02}, "LST_Night_1km": {"units": "K", "scale": 0.02}, "QC_Day": {}, "QC_Night": {}}, 1000, "2024-12-31"),
    "MODIS/061/MOD16A2GF": ("MODIS", "MODIS_061_MOD16A2GF", {"ET": {"units": "kg/m^2/8day", "scale": 0.1}, "ET_QC": {}}, 500, "2024-12-31"),
    "NASA/GLDAS/V021/NOAH/G025/T3H": ("NASA", "NASA_GLDAS_V021_NOAH_G025_T3H", {"RootMoist_inst": {"units": "kg/m^2"}, "SoilMoi0_10cm_inst": {"units": "kg/m^2"}}, 27830, "2024-12-31"),
    "JRC/GSW1_4/MonthlyHistory": ("JRC", "JRC_GSW1_4_MonthlyHistory", {"water": {}}, 30, "2021-12-31"),
    "JRC/GSW1_4/GlobalSurfaceWater": ("JRC", "JRC_GSW1_4_GlobalSurfaceWater", {"occurrence": {}}, 30, None),
    "LANDSAT/LC08/C02/T1_L2": ("LANDSAT", "LANDSAT_LC08_C02_T1_L2", {"SR_B3": {}, "SR_B4": {}, "SR_B5": {}, "SR_B6": {}, "QA_PIXEL": {}}, 30, "2024-12-31"),
    "LANDSAT/LE07/C02/T1_L2": ("LANDSAT", "LANDSAT_LE07_C02_T1_L2", {"SR_B2": {}, "SR_B3": {}, "SR_B4": {}, "QA_PIXEL": {}}, 30, None),
    "LANDSAT/LT05/C02/T1_L2": ("LANDSAT", "LANDSAT_LT05_C02_T1_L2", {"SR_B2": {}, "SR_B3": {}, "SR_B4": {}, "QA_PIXEL": {}}, 30, None),
}


def fetch(provider: str, slug: str, timeout: int = 30) -> dict:
    req = urllib.request.Request(STAC.format(provider=provider, slug=slug), headers={"User-Agent": "GlobalClimateLens-verify/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def check_record(cid: str, stac: dict, expect: dict, gsd: int | None, cover_to: str | None) -> dict:
    """Compare one STAC record against expectations. Pure function (unit-tested with fixtures)."""
    bands = {b["name"]: b for b in stac.get("summaries", {}).get("eo:bands", [])}
    issues, notes = [], []
    for name, want in expect.items():
        b = bands.get(name)
        if b is None:
            issues.append(f"band '{name}' not in catalogue")
            continue
        if "units" in want and b.get("gee:units") != want["units"]:
            issues.append(f"{name}: units {b.get('gee:units')!r} != expected {want['units']!r}")
        if "scale" in want and b.get("gee:scale") != want["scale"]:
            issues.append(f"{name}: scale {b.get('gee:scale')!r} != expected {want['scale']!r}")
    got_gsd = (stac.get("summaries", {}).get("gsd") or [None])[0]
    if gsd is not None and got_gsd != gsd:
        issues.append(f"gsd {got_gsd} != expected {gsd}")
    interval = (stac.get("extent", {}).get("temporal", {}).get("interval") or [[None, None]])[0]
    end = interval[1]
    if cover_to and end and end[:10] < cover_to:
        issues.append(f"coverage ends {end[:10]}, before required {cover_to}")
    notes.append(f"coverage {str(interval[0])[:10]} -> {str(end)[:10] if end else 'ongoing'}")
    return {"collection": cid, "ok": not issues, "issues": issues, "notes": notes, "id_in_catalogue": stac.get("id")}


def verify_all(fetcher=fetch) -> dict:
    out = {"retrieved": date.today().isoformat(), "results": []}
    for cid, (prov, slug, expect, gsd, cover) in EXPECTATIONS.items():
        try:
            out["results"].append(check_record(cid, fetcher(prov, slug), expect, gsd, cover))
        except Exception as e:
            out["results"].append({"collection": cid, "ok": False, "issues": [f"fetch failed: {type(e).__name__}: {e}"], "notes": []})
    out["all_ok"] = all(r["ok"] for r in out["results"])
    return out
