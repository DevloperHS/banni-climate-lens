import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

export interface Overlay { id: string; url: string; bounds: { south: number; north: number; west: number; east: number }; opacity: number; visible: boolean }
export interface MapPoint { id: string; lat: number; lon: number; color: string; label: string }
export type Basemap = "satellite" | "streets" | "none";

const BASEMAPS: Record<Exclude<Basemap, "none">, { url: string; attribution: string }> = {
  satellite: { url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", attribution: "Imagery © Esri, Maxar, Earthstar Geographics" },
  streets: { url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png", attribution: "© OpenStreetMap contributors" },
};

interface Props {
  boundary?: GeoJSON.Feature;
  overlays: Overlay[];
  basemap: Basemap;
  onClick?: (lat: number, lon: number) => void;
  marker?: { lat: number; lon: number } | null;
  height?: number;
  onCursor?: (lat: number, lon: number) => void;
  points?: MapPoint[];
}

export default function MapView({ boundary, overlays, basemap, onClick, marker, height = 460, onCursor, points }: Props) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const base = useRef<L.TileLayer | null>(null);
  const ovl = useRef<Map<string, L.ImageOverlay>>(new Map());
  const bnd = useRef<L.GeoJSON | null>(null);
  const mk = useRef<L.CircleMarker | null>(null);
  const pts = useRef<L.LayerGroup | null>(null);
  const cb = useRef({ onClick, onCursor });
  cb.current = { onClick, onCursor };

  useEffect(() => {
    if (!el.current || map.current) return;
    const m = L.map(el.current, { zoomControl: true, attributionControl: true, worldCopyJump: true }).setView([23.6, 69.4], 8);
    m.on("click", (e: L.LeafletMouseEvent) => cb.current.onClick?.(e.latlng.lat, e.latlng.lng));
    m.on("mousemove", (e: L.LeafletMouseEvent) => cb.current.onCursor?.(e.latlng.lat, e.latlng.lng));
    map.current = m;
    return () => { m.remove(); map.current = null; ovl.current.clear(); bnd.current = null; pts.current = null; base.current = null; mk.current = null; };
  }, []);

  useEffect(() => {
    const m = map.current; if (!m) return;
    base.current?.remove(); base.current = null;
    if (basemap !== "none") {
      base.current = L.tileLayer(BASEMAPS[basemap].url, { attribution: BASEMAPS[basemap].attribution, maxZoom: 17 }).addTo(m);
      base.current.bringToBack();
    }
  }, [basemap]);

  useEffect(() => {
    const m = map.current; if (!m) return;
    bnd.current?.remove(); bnd.current = null;
    if (boundary) {
      bnd.current = L.geoJSON(boundary, { style: { color: "#38bdf8", weight: 2, fillOpacity: 0, dashArray: "6 4" } }).addTo(m);
      m.fitBounds(bnd.current.getBounds(), { padding: [20, 20] });
    }
  }, [boundary]);

  useEffect(() => {
    const m = map.current; if (!m) return;
    const want = new Set(overlays.filter((o) => o.visible).map((o) => o.id));
    ovl.current.forEach((layer, id) => { if (!want.has(id)) { layer.remove(); ovl.current.delete(id); } });
    overlays.filter((o) => o.visible).forEach((o) => {
      const b: L.LatLngBoundsExpression = [[o.bounds.south, o.bounds.west], [o.bounds.north, o.bounds.east]];
      const ex = ovl.current.get(o.id);
      if (ex) { if ((ex as unknown as { _url: string })._url !== o.url) ex.setUrl(o.url); ex.setOpacity(o.opacity); }
      else { const l = L.imageOverlay(o.url, b, { opacity: o.opacity, interactive: false }).addTo(m); ovl.current.set(o.id, l); }
    });
  }, [overlays]);

  useEffect(() => {
    const m = map.current; if (!m) return;
    mk.current?.remove(); mk.current = null;
    if (marker) mk.current = L.circleMarker([marker.lat, marker.lon], { radius: 6, color: "#fbbf24", weight: 2, fillOpacity: 0.4 }).addTo(m);
  }, [marker]);

  useEffect(() => {
    const m = map.current; if (!m) return;
    pts.current?.remove(); pts.current = null;
    if (points?.length) {
      pts.current = L.layerGroup(points.map((p) => L.circleMarker([p.lat, p.lon], { radius: 6, color: "#0c121d", weight: 1.5, fillColor: p.color, fillOpacity: 0.95 })
        .bindTooltip(p.label))).addTo(m);
    }
  }, [points]);

  return <div ref={el} style={{ height }} role="application" aria-label="Interactive map" data-testid="map" />;
}

export function Legend({ title, unit, vmin, vmax, cmap }: { title: string; unit?: string; vmin: number; vmax: number; cmap: string }) {
  const grad: Record<string, string> = {
    YlGn: "#ffffe5,#d9f0a3,#78c679,#238443,#004529", Blues: "#f7fbff,#c6dbef,#6baed6,#2171b5,#08306b", inferno: "#000004,#781c6d,#ed6925,#fcffa4",
    magma: "#000004,#721f81,#f1605d,#fcfdbf", BuGn: "#f7fcfd,#ccece6,#66c2a4,#238b45,#00441b", PuBu: "#fff7fb,#d0d1e6,#74a9cf,#0570b0,#023858",
    PuBuGn: "#fff7fb,#d0d1e6,#67a9cf,#02818a,#014636", viridis: "#440154,#3b528b,#21918c,#5ec962,#fde725",
  };
  return (
    <div aria-label="Map legend" className="text-xs">
      <div className="mb-1 font-semibold">{title}{unit ? ` (${unit})` : ""}</div>
      <div style={{ height: 10, borderRadius: 4, background: `linear-gradient(90deg, ${grad[cmap] ?? grad.viridis})` }} />
      <div className="flex justify-between muted mt-0.5"><span>{vmin.toPrecision(3)}</span><span>{vmax.toPrecision(3)}</span></div>
    </div>
  );
}
