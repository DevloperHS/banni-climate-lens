import json
import math
from functools import lru_cache
from pathlib import Path

CONFIG = Path(__file__).resolve().parents[1] / "config" / "regions.json"
GEOMS = Path(__file__).resolve().parents[1] / "config" / "geometries"
# WGS84 ellipsoidal areas via the authalic (equal-area) sphere: exact for the ellipsoid, unlike a plain
# spherical formula which overstates mid-latitude areas by ~0.5%.
_A = 6378137.0
_F = 1 / 298.257223563
_E2 = _F * (2 - _F)
_E = math.sqrt(_E2)


def _q(phi: float) -> float:
    sp = math.sin(phi)
    return (1 - _E2) * (sp / (1 - _E2 * sp * sp) - (1 / (2 * _E)) * math.log((1 - _E * sp) / (1 + _E * sp)))


_QP = _q(math.pi / 2)
R_KM = _A * math.sqrt(_QP / 2) / 1000.0          # authalic radius, km


def _authalic_sin(lat_deg: float) -> float:
    return _q(math.radians(lat_deg)) / _QP        # sin(beta)


def bbox_area_km2(b: dict) -> float:
    """WGS84 ellipsoidal area of a lat/lon box."""
    return abs(math.radians(b["east"] - b["west"]) * R_KM**2 * (_authalic_sin(b["north"]) - _authalic_sin(b["south"])))


def ring_area_km2(ring: list[list[float]]) -> float:
    """WGS84 ellipsoidal area of a lon/lat ring (Chamberlain & Duquette on the authalic sphere)."""
    s = 0.0
    for i in range(len(ring) - 1):
        (lon1, lat1), (lon2, lat2) = ring[i], ring[i + 1]
        s += math.radians(lon2 - lon1) * (2 + _authalic_sin(lat1) + _authalic_sin(lat2))
    return abs(s) * R_KM**2 / 2


def polygon_area_km2(geom: dict) -> float:
    polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
    return sum(ring_area_km2(p[0]) - sum(ring_area_km2(h) for h in p[1:]) for p in polys)


def _coords(geom):
    polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
    return [pt for p in polys for ring in p for pt in ring]


def boundary_geojson(region: dict) -> dict:
    if region.get("polygon"):
        return {"type": "Feature", "geometry": region["polygon"],
                "properties": {"id": region["id"], "name": region["name"], "kind": "polygon", "source": region["geometry"]["source"]}}
    b = region["bbox"]
    ring = [[b["west"], b["south"]], [b["east"], b["south"]], [b["east"], b["north"]],
            [b["west"], b["north"]], [b["west"], b["south"]]]
    return {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring]},
            "properties": {"id": region["id"], "name": region["name"], "kind": "study bounding box"}}


def load_polygon(path: Path, parent: dict) -> tuple[dict | None, str | None]:
    """Validate a boundary file. Returns (feature_info, error)."""
    try:
        gj = json.loads(path.read_text(encoding="utf-8"))
        feat = gj["features"][0] if gj.get("type") == "FeatureCollection" else gj
        geom, props = feat["geometry"], feat.get("properties") or {}
        if geom["type"] not in ("Polygon", "MultiPolygon"):
            return None, "geometry must be Polygon or MultiPolygon"
        miss = [k for k in ("source", "retrieved", "license") if not props.get(k)]
        if miss:
            return None, f"properties missing: {', '.join(miss)}"
        b = parent["bbox"]; tol = 0.05
        for lon, lat in _coords(geom):
            if not (b["west"] - tol <= lon <= b["east"] + tol and b["south"] - tol <= lat <= b["north"] + tol):
                return None, "vertices fall outside the parent region's rectangle (is it EPSG:4326 lon/lat?)"
        return {"geometry": geom, "props": props}, None
    except Exception as e:
        return None, f"unreadable: {type(e).__name__}: {e}"


@lru_cache
def _load() -> tuple[dict[str, dict], list[dict]]:
    regs = json.loads(CONFIG.read_text(encoding="utf-8"))
    out: dict[str, dict] = {}
    problems: list[dict] = []
    for r in regs:
        r["computed_bbox_area_km2"] = round(bbox_area_km2(r["bbox"]), 1)
        r["geometry"] = {**r.get("geometry", {"id": "bbox", "kind": "bbox", "source": "config"}),
                         "area_km2": r["computed_bbox_area_km2"]}
        out[r["id"]] = r
        f = GEOMS / f"{r['id']}_grassland.geojson"
        if f.exists():
            info, err = load_polygon(f, r)
            if err:
                problems.append({"region": r["id"], "file": f.name, "error": err})
                continue
            area = round(polygon_area_km2(info["geometry"]), 1)
            lons = [c[0] for c in _coords(info["geometry"])]; lats = [c[1] for c in _coords(info["geometry"])]
            d = {**r, "id": f"{r['id']}_grassland", "name": f"{r['name']} (grassland polygon)", "parent": r["id"],
                 "bbox": {"south": min(lats), "north": max(lats), "west": min(lons), "east": max(lons)},
                 "polygon": info["geometry"], "pending_geometry": None,
                 "geometry": {"id": "grassland", "kind": "polygon", "area_km2": area, "source": info["props"]["source"],
                              "retrieved": info["props"]["retrieved"], "license": info["props"]["license"]}}
            d["computed_bbox_area_km2"] = area
            d["reference_area_note"] = (f"Area computed from the supplied polygon ({area:,.0f} km2); source: {info['props']['source']}.")
            out[d["id"]] = d
    return out, problems


def list_regions() -> list[dict]:
    return list(_load()[0].values())


def geometry_problems() -> list[dict]:
    return _load()[1]


def get_region(region_id: str) -> dict:
    try:
        return _load()[0][region_id]
    except KeyError:
        raise KeyError(f"Unknown region '{region_id}'. Available: {', '.join(_load()[0])}")
