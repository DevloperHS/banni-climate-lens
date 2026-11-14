import { useState } from "react";
import MapView, { Basemap } from "../components/MapView";
import { PageHeader, MapPanel, Panel, Select, Skeleton } from "../components/ui";
import { useApp } from "../state/AppState";

export default function Regions() {
  const { regions, region, setRegionId, start, end, setPeriod } = useApp();
  const [basemap, setBasemap] = useState<Basemap>("satellite");

  if (!region) return <Skeleton h={600} />;

  const years = Array.from(
    { length: region.study_period.end - region.study_period.start + 1 },
    (_, i) => region.study_period.start + i
  );

  return (
    <div className="space-y-6">
      {/* ── Page Header & Region Summary ── */}
      <PageHeader
        title="Regions"
        subtitle={`Geographic extents and spatial boundaries configured for Earth observation retrieval. Currently analyzing ${region.name} (${region.state}, ${region.country}).`}
        badges={
          <div className="flex items-center gap-2">
            <span className="badge font-mono text-[11px] text-[var(--teal)] border-[var(--border-hi)]">
              {region.id}
            </span>
            <span className="badge font-mono text-[11px] bg-[var(--bg-soft)]">
              {region.geometry.kind.toUpperCase()}
            </span>
            <span className="badge font-mono text-[11px]">EPSG:4326</span>
          </div>
        }
      />

      {/* ── Compact Region Summary Banner ── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 p-4 rounded-lg bg-[var(--bg-elev)] border border-[var(--border-subtle)]">
        <div>
          <div className="text-[11px] font-bold uppercase tracking-wider text-[var(--muted)]">Active Region</div>
          <div className="text-sm font-semibold text-[var(--text)] mt-0.5 truncate">{region.name}</div>
          <div className="text-xs text-[var(--muted)]">{region.state}, {region.country}</div>
        </div>
        <div>
          <div className="text-[11px] font-bold uppercase tracking-wider text-[var(--muted)]">Study Period</div>
          <div className="text-sm font-semibold font-mono text-[var(--teal)] mt-0.5">{start} – {end}</div>
          <div className="text-xs text-[var(--muted)]">{end - start + 1} annual cycles</div>
        </div>
        <div>
          <div className="text-[11px] font-bold uppercase tracking-wider text-[var(--muted)]">Analysis Rectangle</div>
          <div className="text-sm font-semibold font-mono text-[var(--text)] mt-0.5">
            {Math.round(region.computed_bbox_area_km2).toLocaleString()} km²
          </div>
          <div className="text-xs text-[var(--muted)]">Handover standard grid</div>
        </div>
        <div>
          <div className="text-[11px] font-bold uppercase tracking-wider text-[var(--muted)]">Reference Footprint</div>
          <div className="text-sm font-semibold font-mono text-[var(--green)] mt-0.5">
            ≈ {region.reference_area_km2.toLocaleString()} km²
          </div>
          <div className="text-xs text-[var(--muted)]">Grassland core estimate</div>
        </div>
      </div>

      {/* ── Geospatial Workspace: Map as Centerpiece (68% width) + Information Dock (32% width) ── */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left/Center: Large Interactive Map (Centerpiece ~68% width) */}
        <div className="lg:col-span-8">
          <MapPanel
            title={`${region.name} Spatial Boundary`}
            subtitle="Dashed border denotes the rectangular extraction window (EPSG:4326) across Kutch, Gujarat"
            actions={
              <div className="flex items-center gap-2">
                <span className="text-xs text-[var(--muted)] font-medium">Basemap:</span>
                <select
                  className="field !py-1 !px-2.5 text-xs font-medium"
                  value={basemap}
                  onChange={(e) => setBasemap(e.target.value as Basemap)}
                  aria-label="Basemap"
                >
                  <option value="satellite">Satellite Imagery (Esri World Imagery)</option>
                  <option value="streets">Terrain &amp; Streets (OpenStreetMap)</option>
                  <option value="none">Blank Vector Grid</option>
                </select>
              </div>
            }
            footer={
              <div className="flex flex-wrap items-center justify-between gap-3 text-[11px] text-[var(--muted)]">
                <span>Bounding Box: {region.bbox.south}°N–{region.bbox.north}°N, {region.bbox.west}°E–{region.bbox.east}°E</span>
                <span className="font-mono">Projection: WGS84 Plate Carrée</span>
              </div>
            }
          >
            <div className="h-[600px] w-full">
              <MapView boundary={region.boundary} overlays={[]} basemap={basemap} height={600} />
            </div>
          </MapPanel>
        </div>

        {/* Right: Compact Information Dock (~32% width) */}
        <div className="lg:col-span-4 space-y-4">
          {/* Study Area Switcher */}
          <Panel title="Study Area Selection" subtitle="Configured geographic regions">
            <ul className="space-y-2" aria-label="Available study areas">
              {regions.map((r) => {
                const isSelected = r.id === region.id;
                return (
                  <li key={r.id}>
                    <button
                      className="btn w-full !justify-between !p-3 text-left transition-all"
                      aria-pressed={isSelected}
                      onClick={() => setRegionId(r.id)}
                      style={{
                        borderColor: isSelected ? "var(--green)" : "var(--border)",
                        background: isSelected ? "color-mix(in srgb, var(--green) 10%, var(--bg-soft))" : "var(--bg-elev)",
                      }}
                    >
                      <div>
                        <div className="font-semibold text-xs sm:text-sm text-[var(--text)]">{r.name}</div>
                        <div className="text-[11px] text-[var(--muted)] mt-0.5">
                          {r.state}, {r.country}
                        </div>
                      </div>
                      {isSelected ? (
                        <span className="badge badge-ok font-mono text-[10px]">CURRENT</span>
                      ) : (
                        <span className="text-xs text-[var(--muted)]">Select →</span>
                      )}
                    </button>
                  </li>
                );
              })}
            </ul>
          </Panel>

          {/* Temporal Window Filter */}
          <Panel title="Analysis Period" subtitle="Global multi-annual observation range">
            <div className="grid grid-cols-2 gap-3">
              <Select
                label="From"
                value={String(start)}
                onChange={(v) => setPeriod(Number(v), end)}
                options={years.map((y) => ({ value: String(y), label: String(y) }))}
              />
              <Select
                label="To"
                value={String(end)}
                onChange={(v) => setPeriod(start, Number(v))}
                options={years.map((y) => ({ value: String(y), label: String(y) }))}
              />
            </div>
            <p className="text-[11px] text-[var(--muted)] mt-2.5 leading-relaxed">
              Propagates to all research modules. Monotonic trend tests require ≥4 years; gridded pixel trends require ≥10 years.
            </p>
          </Panel>

          {/* Geometry Provenance & Area Differentiation */}
          <Panel title="Geometry Provenance & Area Distinction">
            <div className="tbl-wrap">
              <table className="tbl">
                <tbody>
                  <tr>
                    <td className="muted w-2/5">Geometry ID</td>
                    <td data-testid="geometry-id" className="font-mono text-xs font-semibold text-[var(--text)]">
                      {region.geometry.id} ({region.geometry.kind})
                    </td>
                  </tr>
                  <tr>
                    <td className="muted">Bounding Box Area</td>
                    <td className="font-mono text-xs">
                      {Math.round(region.computed_bbox_area_km2).toLocaleString()} km²
                    </td>
                  </tr>
                  <tr>
                    <td className="muted">Actual Grassland Area</td>
                    <td className="font-mono text-xs text-[var(--teal)] font-semibold">
                      ≈ {region.reference_area_km2.toLocaleString()} km² (reference)
                    </td>
                  </tr>
                  <tr>
                    <td className="muted">Source</td>
                    <td className="text-xs">{region.geometry.source}</td>
                  </tr>
                  <tr>
                    <td className="muted">Known Events</td>
                    <td className="text-xs">{region.events.map((e) => `${e.name} (${e.date})`).join("; ") || "None"}</td>
                  </tr>
                </tbody>
              </table>
            </div>

            {region.pending_geometry && (
              <div className="p-3 rounded bg-[var(--bg-soft)] border border-[var(--amber)] text-xs text-[var(--amber)] mt-3">
                ⚠ Grassland polygon pending: {region.pending_geometry.needed}
              </div>
            )}

            {region.published_area_figures && region.published_area_figures.length > 0 && (
              <details className="mt-3 text-xs bg-[var(--bg-soft)] p-3 rounded border border-[var(--border)]">
                <summary className="cursor-pointer font-semibold text-[var(--text)] select-none">
                  Published Grassland Area Figures ({region.published_area_figures.length})
                </summary>
                <ul className="list-disc pl-5 text-[11px] text-[var(--muted)] mt-2 space-y-1">
                  {region.published_area_figures.map((f) => (
                    <li key={f.source}>
                      <b className="text-[var(--text-2)]">{f.km2.toLocaleString()} km²</b>: {f.source} (<i>{f.verified}</i>)
                    </li>
                  ))}
                </ul>
              </details>
            )}

            <div className="text-[11px] text-[var(--muted)] mt-3 pt-2 border-t border-[var(--border-subtle)] leading-relaxed">
              {region.reference_area_note}
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}
