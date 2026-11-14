"""dashboards router: the three Banni 'Trend Detective' dashboards (Rain and Green, Water and Heat, Where It Changed).

Each dashboard is assembled ONLY from stored series and raster stacks through the same services every other page uses:
one yearly table (a column per factor), one trend result per factor, and the list of map layers with bounds and legends.
Nothing is hard-coded except the question each dashboard asks and its standing limitations. A factor without data is
returned as unavailable with the reason; it is never filled in.
"""
from __future__ import annotations
from typing import Literal
from fastapi import APIRouter, Query

from .. import services as svc
from ..core import groundwater as GW
from ..core import store
from ..core.catalog import CATALOG
from ..science import stats as S

Source = Literal["processed", "sample"]
dashboards = APIRouter(prefix="/api/dashboards", tags=["dashboards"])

CATALOG_URL = "https://developers.google.com/earth-engine/datasets/catalog/"
EXTRA_SOURCES = {"groundwater": ("CGWB groundwater levels via India-WRIS", "https://indiawris.gov.in/wris/#/groundWater")}

# Limits that apply to every dashboard (research brief, section 8)
COMMON_LIMITS = [
    "All series are averages over the whole analysis rectangle (~9,751 km²); a change in one village will not show.",
    "Twenty-four yearly points is a short series, so single wet or dry years carry weight.",
    "A trend describes a satellite-derived quantity. It does not by itself identify a cause or a species.",
]

# factor = (key, aggregation, role); role is shown on the card
DASHBOARDS = {
    "rain_green": {
        "title": "Rain and Green",
        "question": "Is Banni greener than its rain explains?",
        "factors": [("precip", "monsoon", "Monsoon rainfall total"), ("ndvi", "monsoon", "Monsoon greenness"),
                    ("ndvi", "summer", "Dry-season greenness (Mar-May)")],
        "derived": [("rain_removed", "ndvi", "monsoon", "monsoon", "Monsoon greenness with the rain effect removed"),
                    ("rain_removed", "ndvi", "summer", "prev_monsoon", "Dry-season greenness with the previous monsoon's rain removed")],
        "layers": [("ndvi", "monsoon"), ("ndvi", "summer"), ("precip", "monsoon")],
        "limits": ["The Aqua and EVI checks guard against a single-sensor or single-index artefact. All three come from MODIS "
                   "on the same 250 m grid, so they do not test errors the sensors share.",
                   "NDVI measures green cover. It cannot tell grass from shrub; a rising dry-season trend is consistent with, "
                   "but does not prove, woody (evergreen) cover such as Prosopis juliflora.",
                   "The rain-removed series depends on a linear rain-greenness relation; other drivers (grazing, irrigation, "
                   "flooding near the Rann, regional greening across north-west India) are not ruled out."],
    },
    "water_heat": {
        "title": "Water and Heat",
        "question": "What is the extra greenness doing to water and temperature?",
        "factors": [("et", "annual", "Evapotranspiration, annual total"), ("sm_root", "annual", "Root-zone soil moisture"),
                    ("lst_day", "annual", "Land surface temperature, day"), ("lst_night", "annual", "Land surface temperature, night"),
                    ("grace_tws", "annual", "Total water storage (regional context)"), ("groundwater", "annual", "Groundwater depth in wells")],
        "derived": [("rain_removed", "et", "annual", "annual", "Evapotranspiration with the rain effect removed")],
        "layers": [("et", "annual"), ("sm_root", "annual"), ("lst_day", "summer"), ("lst_night", "summer")],
        "limits": ["MODIS evapotranspiration uses vegetation greenness as an input, so part of its rise echoes the NDVI rise.",
                   "GLDAS soil moisture is a model on a ~28 km grid and does not represent shrub cover or pumping.",
                   "GRACE mascons are 3 degrees across, far larger than Banni: regional context only.",
                   "Only measured well levels can support a statement about the water table."],
    },
    "where_changed": {
        "title": "Where It Changed",
        "question": "Where inside Banni is the change, and what is the land turning into?",
        "factors": [("ndvi_landsat", "annual", "Greenness at 30 m (Landsat, Sep-Oct)"), ("lc_grassland", "annual", "Grassland share"),
                    ("lc_shrubland", "annual", "Shrubland share"), ("lc_savanna", "annual", "Savanna / woody savanna share"),
                    ("water_extent", "annual", "Surface-water extent (JRC)"), ("water_extent_mndwi", "annual", "Surface-water extent (Landsat MNDWI)")],
        "derived": [],
        "layers": [("ndvi", "monsoon"), ("ndvi_landsat", "peak")],
        "landcover": ["lc_grassland", "lc_shrubland", "lc_savanna", "lc_cropland", "lc_barren", "lc_water"],
        "limits": ["Pixels are spatially autocorrelated, so the false-discovery-rate control on the trend map is approximate.",
                   "MCD12Q1 is a global 500 m classifier, not validated for Banni; part of the year-to-year class change is classification noise.",
                   "Surface-water records end in 2021 (JRC) or start in 2013 (Landsat 8 MNDWI); neither covers all of 2001-2024."],
    },
}


def _slope_unit(key: str, agg: str) -> str:
    """Slope unit for a yearly value: summed variables (rainfall, ET) are seasonal TOTALS in mm, not monthly rates."""
    if CATALOG[key].reducer == "sum":
        return f"mm ({agg} total) per year"
    return f"{svc.short_unit(key)} per year"


def _card(key: str, agg: str, role: str, region, source, start, end, alpha) -> dict:
    spec = CATALOG[key]
    base = {"key": key, "aggregation": agg, "role": role, "label": spec.label, "dataset": spec.ee_id or spec.provider, "unit": spec.unit}
    try:
        if key == "groundwater":
            return {**base, **_wells_card(region, source)}
        r = svc.trend_payload(region, key, source, agg, start, end, alpha)
    except svc.AppError as e:
        return {**base, "available": False, "reason": e.message}
    t = r["result"]["hr"]          # the brief's protocol: Hamed-Rao corrected Mann-Kendall on every card
    return {**base, "available": True, "test": t["test"], "direction": t["direction"], "slope": t["slope"], "slope_unit": _slope_unit(key, agg),
            "ci": [t["slope_ci_low"], t["slope_ci_high"]], "p": t["p"], "significant": t["significant"], "n": t["n"],
            "period": r["meta"]["period"], "synthetic": r["meta"]["synthetic"],
            "series": {"years": r["result"]["years"], "values": r["result"]["values"], "line": r["result"]["line"]}}


def _wells_card(region, source) -> dict:
    w = GW.load_wells(source, region)
    if not w:
        return {"available": False, "reason": "No measured well levels uploaded. Download CGWB readings from India-WRIS and upload them in Water Resources."}
    trends = GW.per_well_trends(w)
    tested = [t for t in trends if t["status"] == "tested"]
    return {"available": bool(tested), "reason": None if tested else "No well has enough years for a trend test.",
            "direction": f"{sum(t['direction'] == 'increasing' for t in tested)} deepening / {sum(t['direction'] == 'decreasing' for t in tested)} shallowing"
            if tested else None, "n": len(tested), "test": "Mann-Kendall per well, BH-FDR across wells", "synthetic": False,
            "wells": [{"well_id": k, "lat": v.get("lat"), "lon": v.get("lon"), **next((t for t in trends if t["well_id"] == k), {})}
                      for k, v in w["wells"].items()]}


def _derived(kind, response, season, rain_season, role, region, source, start, end, alpha) -> dict:
    spec = CATALOG[response]
    base = {"key": f"{response}_rain_removed", "aggregation": season, "role": role, "label": f"{spec.label}, rainfall removed",
            "dataset": f"{spec.ee_id} + {CATALOG['precip'].ee_id}", "unit": spec.unit, "derived": True}
    try:
        r = svc.rainfall_adjusted_payload(region, source, response, season, start, end, alpha, rain_season)
    except svc.AppError as e:
        return {**base, "available": False, "reason": e.message}
    res = r["result"]; t = res["residual_trend"]["hr"]
    year_term = next(({"coef": s["year_coef_per_year"], "p": s["ols_p"], "hac_p": s["hac_p"]} for s in res["sensitivity"]
                      if s["name"].startswith("S3")), None)          # second method: response ~ rainfall + year
    return {**base, "available": True, "test": t["test"], "direction": t["direction"], "slope": t["slope"], "slope_unit": _slope_unit(response, season),
            "ci": [t["slope_ci_low"], t["slope_ci_high"]], "p": t["p"], "significant": t["significant"], "n": t["n"],
            "period": f"{min(res['years'])}-{max(res['years'])}", "synthetic": r["meta"]["synthetic"], "r2_rain": res["regression"]["r2"],
            "year_term": year_term, "verdict": res["verdict"]["text"],
            "series": {"years": res["years"], "observed": res["ndvi"], "predicted": res["predicted"], "rainfall": res["rainfall"]}}


def _layers(region, source, wanted) -> list[dict]:
    from .analysis import layers as list_layers
    have = {(i["variable"], i["season"]): i for i in list_layers(region, source)["items"]}
    return [have[w] for w in wanted if w in have]


def _yearly(cards: list[dict]) -> dict:
    """One yearly table: a column per factor (only factors with data)."""
    years = sorted({y for c in cards if c.get("available") and c.get("series") for y in c["series"]["years"]})
    cols = {}
    for c in cards:
        s = c.get("series") if c.get("available") else None
        if not s:
            continue
        if "values" in s:
            vals = dict(zip(s["years"], s["values"]))
        else:                     # derived rain-removed factor: the residual, observed minus rainfall-predicted
            vals = {y: o - p for y, o, p in zip(s["years"], s["observed"], s["predicted"])}
        cols[f"{c['key']}:{c['aggregation']}"] = [vals.get(y) for y in years]
    return {"years": years, "columns": cols}


def _sources(cards: list[dict]) -> list[dict]:
    out, seen = [], set()
    for c in cards:
        key = c["key"].replace("_rain_removed", "")
        if key in seen or key not in CATALOG:
            continue
        seen.add(key)
        spec = CATALOG[key]
        if key in EXTRA_SOURCES:
            name, url = EXTRA_SOURCES[key]
        elif spec.ee_id and "{" not in spec.ee_id and "," not in spec.ee_id and "+" not in spec.ee_id:
            name, url = spec.ee_id, CATALOG_URL + spec.ee_id.replace("/", "_")
        else:
            name, url = spec.ee_id or spec.provider, CATALOG_URL
        out.append({"key": key, "label": spec.label, "dataset": name, "provider": spec.provider, "url": url,
                    "resolution": f"{spec.spatial_resolution} · {spec.temporal_resolution}"})
    return out


@dashboards.get("")
def dashboard_list():
    return {"items": [{"id": k, "title": d["title"], "question": d["question"]} for k, d in DASHBOARDS.items()]}


@dashboards.get("/{dash_id}")
def dashboard(dash_id: Literal["rain_green", "water_heat", "where_changed"], region: str = "banni", source: Source = "processed",
              start: int | None = None, end: int | None = None, alpha: float = Query(0.05, gt=0, lt=0.5)):
    svc.check(region)
    d = DASHBOARDS[dash_id]
    cards = [_card(k, agg, role, region, source, start, end, alpha) for k, agg, role in d["factors"]]
    derived = [_derived(*x, region, source, start, end, alpha) for x in d["derived"]]
    out = {"id": dash_id, "title": d["title"], "question": d["question"], "cards": cards, "derived": derived,
           "yearly": _yearly(cards + derived), "layers": _layers(region, source, d["layers"]),
           "limits": d["limits"] + COMMON_LIMITS, "sources": _sources(cards + derived)}
    if dash_id == "rain_green":           # brief s.7/s.8: 'repeat with Aqua and with EVI' before trusting 'not explained by rain'
        try:
            out["checks"] = svc.sensor_index_checks_payload(region, source, start, end, alpha)["result"]
            shown = {r["key"] for s in out["checks"]["seasons"] for r in s["rows"] if r["available"]}
            out["sources"] += _sources([{"key": k} for k in ("ndvi_aqua", "evi") if k in shown])
        except svc.AppError as e:
            out["checks"] = {"available": False, "reason": e.message}
    if "landcover" in d:
        lc = []
        for k in d["landcover"]:
            try:
                a, _ = svc.annual(region, k, source, "annual", start, end)
                lc.append({"key": k, "label": CATALOG[k].label.split(": ")[1].split(" (MODIS")[0], "years": [int(i) for i in a.index], "values": [float(v) for v in a.values]})
            except svc.AppError:
                pass
        out["landcover"] = lc
    synthetic = any(c.get("synthetic") for c in cards + derived)
    return {"result": out, "meta": {"region": region, "source": source, "kind": "synthetic" if synthetic else "observed", "synthetic": synthetic,
                                    "disclaimer": None, "method": "Mann-Kendall + Hamed-Rao, Sen slope; rainfall removed by OLS residuals"}}
