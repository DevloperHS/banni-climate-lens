import { useEffect, useMemo, useState } from "react";
import MapView, { Basemap, Legend, Overlay } from "../components/MapView";
import { ChartFrame, LinesChart } from "../components/charts";
import { PageHeader, MapPanel, Panel, Q, Select, Skeleton, fmt, useApi, useScope } from "../components/ui";
import { downloadUrl, Wrapped } from "../lib/api";
import { useApp } from "../state/AppState";

export interface Layer {
  variable: string;
  season: string;
  label: string;
  unit: string;
  cmap: string;
  years: number[];
  bounds: { south: number; north: number; west: number; east: number };
  vmin: number;
  vmax: number;
  crs: string;
  kind: string;
}

interface Inspect {
  lat: number;
  lon: number;
  years: number[];
  values: (number | null)[];
  unit: string;
  trend?: { direction: string; p: number; slope: number };
  trend_note?: string;
}

export default function Satellite() {
  const sc = useScope();
  const { region } = useApp();
  const layers = useApi<{ items: Layer[] }>("/spatial/layers", { region: sc.region, source: sc.source });
  const [variable, setVariable] = useState("ndvi");
  const [season, setSeason] = useState("annual");
  const [year, setYear] = useState<number | null>(null);
  const [opacity, setOpacity] = useState(0.85);
  const [visible, setVisible] = useState(true);
  const [showBoundary, setShowBoundary] = useState(true);
  const [basemap, setBasemap] = useState<Basemap>("satellite");
  const [pt, setPt] = useState<{ lat: number; lon: number } | null>(null);
  const [cursor, setCursor] = useState<{ lat: number; lon: number } | null>(null);

  const items = layers.data?.items ?? [];
  const vars = Array.from(new Set(items.map((l) => l.variable)));
  const seasons = items.filter((l) => l.variable === variable).map((l) => l.season);
  const layer = items.find((l) => l.variable === variable && l.season === season) ?? items.find((l) => l.variable === variable);

  useEffect(() => {
    if (items.length && !items.some((l) => l.variable === variable)) setVariable(items[0].variable);
  }, [items, variable]);

  useEffect(() => {
    if (layer && layer.season !== season) setSeason(layer.season);
  }, [layer, season]);

  useEffect(() => {
    if (layer && (year === null || !layer.years.includes(year))) {
      setYear(layer.years[layer.years.length - 1] ?? null);
    }
  }, [layer, year]);

  const overlays: Overlay[] = useMemo(
    () =>
      layer && year
        ? [
            {
              id: "layer",
              visible,
              opacity,
              bounds: layer.bounds,
              url: downloadUrl("/spatial/layer.png", {
                region: sc.region,
                source: sc.source,
                variable: layer.variable,
                season: layer.season,
                year,
              }),
            },
          ]
        : [],
    [layer, year, visible, opacity, sc.region, sc.source]
  );

  const insp = useApi<Wrapped<Inspect>>(
    "/spatial/inspect",
    {
      region: sc.region,
      source: sc.source,
      variable: layer?.variable,
      season: layer?.season,
      lat: pt?.lat,
      lon: pt?.lon,
    },
    !!pt && !!layer
  );

  if (layers.isLoading) return <Skeleton h={600} />;

  const hasLayers = items.length > 0;

  return (
    <div className="space-y-6">
      {/* ── Page Header ── */}
      <PageHeader
        title="Satellite Explorer"
        subtitle="Geospatial raster workbench visualizing multi-sensor gridded products exported from Google Earth Engine. Click any map pixel to inspect its full multi-decadal time-series."
        badges={
          layer ? (
            <div className="flex items-center gap-2">
              <span className="badge font-mono text-[11px] text-[var(--teal)] border-[var(--border-hi)]">
                {layer.crs}
              </span>
              <span className="badge font-mono text-[11px] bg-[var(--bg-soft)]">
                {layer.variable.toUpperCase()} ({layer.season})
              </span>
              {layer.kind === "synthetic" && <span className="badge badge-warn font-semibold">SYNTHETIC SAMPLE</span>}
            </div>
          ) : (
            <span className="badge font-mono text-[11px] text-[var(--amber)]">STANDBY MODE</span>
          )
        }
      />

      {/* ── Main Geospatial Workspace ── */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left/Main: Interactive Geospatial Canvas (~70% width) */}
        <div className="lg:col-span-8 space-y-4">
          <MapPanel
            title={layer ? `${layer.label} - ${layer.season.toUpperCase()} (${year})` : "Study Area Boundary Preview"}
            subtitle={
              cursor
                ? `Pointer Coordinates: ${cursor.lat.toFixed(4)}°N, ${cursor.lon.toFixed(4)}°E (WGS84)`
                : "Move cursor over map to inspect coordinates · Click any cell to sample pixel time-series"
            }
            actions={
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-mono text-[11px] px-2 py-0.5 rounded bg-[var(--bg-soft)] border border-[var(--border)] text-[var(--text-2)]" aria-live="polite">
                  {cursor ? `${cursor.lat.toFixed(4)}°N, ${cursor.lon.toFixed(4)}°E` : "Awaiting pointer"}
                </span>
                {layer && (
                  <>
                    <a
                      className="btn text-xs !py-1 !px-2"
                      href={downloadUrl("/spatial/export.png", {
                        region: sc.region,
                        source: sc.source,
                        variable: layer.variable,
                        season: layer.season,
                        year,
                        kind: "layer",
                      })}
                      download
                    >
                      ⬇ PNG
                    </a>
                    <a
                      className="btn text-xs !py-1 !px-2"
                      href={downloadUrl("/spatial/layer.tif", {
                        region: sc.region,
                        source: sc.source,
                        variable: layer.variable,
                        season: layer.season,
                        year,
                      })}
                      download
                    >
                      ⬇ GeoTIFF
                    </a>
                  </>
                )}
              </div>
            }
            footer={
              <div className="flex flex-wrap items-center justify-between gap-4 text-xs text-[var(--muted)]">
                <span>
                  {layer
                    ? `Native Resolution: ${layer.crs} · Percentile Range [${layer.vmin} – ${layer.vmax}] ${layer.unit}`
                    : "No raster overlay loaded. Study area outline displayed."}
                </span>
                <span className="font-mono text-[11px]">EPSG:4326 Coordinate Space</span>
              </div>
            }
          >
            <div className="h-[620px] w-full relative">
              <MapView
                boundary={showBoundary ? region?.boundary : undefined}
                overlays={overlays}
                basemap={basemap}
                marker={pt}
                onClick={(lat, lon) => setPt({ lat, lon })}
                onCursor={(lat, lon) => setCursor({ lat, lon })}
                height={620}
              />
            </div>
          </MapPanel>

          {/* Pixel Time-Series Inspection Dock */}
          <Panel
            title="Pixel inspector"
            subtitle={
              pt
                ? `Sampled grid cell: ${pt.lat.toFixed(4)}°N, ${pt.lon.toFixed(4)}°E (Click elsewhere to re-sample)`
                : "Click anywhere on the map above to extract that pixel's 2001–2024 temporal series"
            }
          >
            {pt ? (
              <Q q={insp} h={220}>
                {(r) => (
                  <div className="space-y-4">
                    <ChartFrame
                      title={`${layer?.label ?? "Pixel"} (${layer?.season ?? ""}) Inter-Annual Record`}
                      meta={r.meta}
                      filename="pixel_series"
                      height={220}
                    >
                      <LinesChart
                        rows={r.result.years.map((y, i) => ({ x: y, v: r.result.values[i] }))}
                        lines={[{ key: "v", name: layer?.label ?? "Value", dots: true, color: "var(--teal)" }]}
                        unit={r.result.unit}
                      />
                    </ChartFrame>
                    {r.result.trend && (
                      <div className="p-3.5 rounded-lg bg-[var(--bg-soft)] border border-[var(--border)] text-xs flex flex-wrap items-center justify-between gap-3">
                        <div>
                          <span className="font-bold text-[var(--text)]">Single-pixel trend: </span>
                          <span
                            className="font-semibold"
                            style={{
                              color:
                                r.result.trend.direction === "increasing"
                                  ? "var(--green)"
                                  : r.result.trend.direction === "decreasing"
                                  ? "var(--amber)"
                                  : "var(--muted)",
                            }}
                          >
                            {r.result.trend.direction}
                          </span>{" "}
                          <span className="font-mono text-[var(--text-2)]">
                            (p={fmt(r.result.trend.p, 3)}, slope {fmt(r.result.trend.slope, 4)} {r.result.unit}/yr)
                          </span>
                        </div>
                        <span className="text-xs muted font-mono">{r.result.trend_note}</span>
                      </div>
                    )}
                  </div>
                )}
              </Q>
            ) : (
              <div className="py-8 text-center text-xs sm:text-sm text-[var(--muted)] border border-dashed border-[var(--border)] rounded-lg">
                No coordinate point selected. Click on the map to inspect local vegetative or climatic trends.
              </div>
            )}
          </Panel>
        </div>

        {/* Right: Layer Configuration & Legend Dock (~30% width) */}
        <div className="lg:col-span-4 space-y-4">
          {hasLayers ? (
            <>
              {/* Layer Selection Dock */}
              <Panel title="Layer & Time Controls" subtitle="Select Earth observation layer & slice">
                <div className="space-y-4">
                  <Select
                    label="Variable"
                    value={variable}
                    onChange={setVariable}
                    options={vars.map((v) => ({
                      value: v,
                      label: items.find((l) => l.variable === v)!.label,
                    }))}
                  />

                  <Select
                    label="Season"
                    value={season}
                    onChange={setSeason}
                    options={seasons.map((s) => ({ value: s, label: s }))}
                  />

                  {layer && year !== null && (
                    <div className="space-y-1.5 p-3 rounded-lg bg-[var(--bg-soft)] border border-[var(--border)]">
                      <div className="flex justify-between items-center text-xs">
                        <span className="font-semibold text-[var(--muted)]">Observation Year</span>
                        <span className="font-mono font-bold text-sm text-[var(--text)] px-2 py-0.5 rounded bg-[var(--bg-elev)] border border-[var(--border)]">
                          {year}
                        </span>
                      </div>
                      <input
                        type="range"
                        min={layer.years[0]}
                        max={layer.years[layer.years.length - 1]}
                        value={year}
                        onChange={(e) => setYear(Number(e.target.value))}
                        aria-label="Year"
                        className="w-full accent-[var(--accent)]"
                      />
                      <div className="flex justify-between text-[10px] font-mono text-[var(--muted)]">
                        <span>{layer.years[0]}</span>
                        <span>{layer.years[layer.years.length - 1]}</span>
                      </div>
                    </div>
                  )}

                  <div className="space-y-3 pt-2 border-t border-[var(--border-subtle)]">
                    <label className="flex flex-col gap-1.5 text-xs text-[var(--muted)] font-medium">
                      <div className="flex justify-between">
                        <span>Raster Opacity</span>
                        <span className="font-mono text-xs text-[var(--text)]">{Math.round(opacity * 100)}%</span>
                      </div>
                      <input
                        type="range"
                        min={0.1}
                        max={1}
                        step={0.05}
                        value={opacity}
                        onChange={(e) => setOpacity(Number(e.target.value))}
                        aria-label="Layer opacity"
                        className="w-full accent-[var(--accent)]"
                      />
                    </label>

                    <div className="space-y-2 pt-1">
                      <label className="flex items-center gap-2 text-xs font-medium text-[var(--text-2)] cursor-pointer select-none">
                        <input
                          type="checkbox"
                          checked={visible}
                          onChange={(e) => setVisible(e.target.checked)}
                          className="rounded accent-[var(--accent)]"
                        />
                        Show data layer
                      </label>
                      <label className="flex items-center gap-2 text-xs font-medium text-[var(--text-2)] cursor-pointer select-none">
                        <input
                          type="checkbox"
                          checked={showBoundary}
                          onChange={(e) => setShowBoundary(e.target.checked)}
                          className="rounded accent-[var(--accent)]"
                        />
                        Show region boundary
                      </label>
                    </div>

                    <Select
                      label="Basemap"
                      value={basemap}
                      onChange={setBasemap}
                      options={[
                        { value: "satellite", label: "Satellite Imagery (Esri)" },
                        { value: "streets", label: "Street Map (OSM)" },
                        { value: "none", label: "Blank (No Tile Layer)" },
                      ]}
                    />
                  </div>
                </div>
              </Panel>

              {/* Colormap Legend */}
              {layer && (
                <Panel title="Color Scale Legend" subtitle={`Colormap: ${layer.cmap}`}>
                  <Legend
                    title={layer.label}
                    unit={layer.unit}
                    vmin={layer.vmin}
                    vmax={layer.vmax}
                    cmap={layer.cmap}
                  />
                  <div className="text-[11px] text-[var(--muted)] mt-3 leading-relaxed">
                    Stretched across 2nd–98th percentile pixel distribution. Native grid CRS: {layer.crs}.
                  </div>
                </Panel>
              )}
            </>
          ) : (
            <Panel title="No raster layers">
              <div className="p-4 rounded-lg bg-[var(--bg-soft)] border border-[var(--border)] text-xs sm:text-sm space-y-2.5">
                <div className="font-semibold text-[var(--amber)] flex items-center gap-2">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                    <circle cx="12" cy="12" r="10" />
                    <line x1="12" y1="8" x2="12" y2="12" />
                    <line x1="12" y1="16" x2="12.01" y2="16" />
                  </svg>
                  Raster Stacks Unavailable
                </div>
                <p className="text-[var(--text-2)] leading-relaxed">
                  No gridded stacks are available for this region/source. Run "stack" jobs from Settings (requires Earth Engine) or enable the synthetic sample.
                </p>
                <div className="pt-2">
                  <a href="/settings" className="btn btn-primary text-xs">
                    Open Settings to Schedule Ingestion →
                  </a>
                </div>
              </div>
            </Panel>
          )}
        </div>
      </div>
    </div>
  );
}
