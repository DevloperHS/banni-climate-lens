# Boundary polygons

A file named `<region>_grassland.geojson` here is picked up automatically and registered as an additional
region `<region>_grassland` (own results, own provenance, never mixed with the rectangle).

Requirements (validated on load; invalid files are skipped and reported by `GET /api/regions`):
- GeoJSON Feature or FeatureCollection with one Polygon/MultiPolygon, coordinates in EPSG:4326
- `properties.source` (who produced it), `properties.retrieved` (ISO date), `properties.license`
- vertices inside the parent region's rectangle (with 0.05 deg tolerance)

Do not draw an approximate polygon and present it as the grassland boundary. Use an authoritative source
(Gujarat Forest Department / Banni Grassland Division demarcation survey, ISRO Bhuvan, a published dataset)
and cite it in `properties.source`.
