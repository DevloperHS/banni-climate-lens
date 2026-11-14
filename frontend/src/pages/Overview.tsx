import { useState } from "react";
import { Link } from "react-router-dom";
import { DatasetItem, EEStatus } from "../lib/api";
import {
  PageHeader,
  Panel,
  MapPanel,
  MetricCard,
  SectionHeader,
  Q,
  Skeleton,
  fmt,
  fmtP,
  useApi,
  useScope,
} from "../components/ui";
import { useApp } from "../state/AppState";
import MapView, { Basemap } from "../components/MapView";
import { AdjustedPanel, RegressionPanel, SeriesPanel } from "../components/analysis";
import { AvailabilityStrip } from "../components/panels2";

interface Finding {
  id: string;
  title: string;
  statement: string;
  evidence: { direction?: string; p?: number; slope?: number; n?: number };
}

interface Insights {
  findings: Finding[];
  notes: string[];
  synthetic: boolean;
  synthetic_warning?: string;
  question: string;
}

interface Job {
  id: string;
  status: string;
  created: string;
  spec: { region: string; start: number; end: number; tasks: unknown[] };
}

export default function Overview() {
  const { region } = useApp();
  const sc = useScope();
  const [basemap, setBasemap] = useState<Basemap>("satellite");

  const ds = useApi<{ items: DatasetItem[]; earth_engine: EEStatus }>("/datasets", {
    region: sc.region,
    source: sc.source,
  });
  const ins = useApi<Insights>("/reports/insights", {
    region: sc.region,
    source: sc.source,
    start: sc.start,
    end: sc.end,
  });
  const jobs = useApi<{ items: Job[] }>("/datasets/jobs");

  if (!region) return <Skeleton h={600} />;

  const avail = ds.data?.items.filter((d) => d.available).length ?? 0;
  const totalDatasets = ds.data?.items.length ?? 0;
  const hasNdvi = ds.data?.items.some((d) => d.key === "ndvi" && d.available) ?? false;
  const hasPrecip = ds.data?.items.some((d) => d.key === "precip" && d.available) ?? false;
  const hasEt = ds.data?.items.some((d) => d.key === "et" && d.available) ?? false;
  const hasSm = ds.data?.items.some((d) => d.key === "sm_root" && d.available) ?? false;

  return (
    <div className="space-y-8">
      {/* ── Page Header ── */}
      <PageHeader
        title={region.name}
        subtitle={region.description}
        badges={
          <div className="flex items-center gap-2">
            <span className="badge font-mono text-[11px] text-[var(--teal)] border-[var(--border-hi)]">
              {region.id}
            </span>
            <span className="badge font-mono text-[11px]">
              EPSG:4326 · WGS84
            </span>
          </div>
        }
      />

      {/* ── Core Research Question Banner ── */}
      <div className="p-4 rounded-lg bg-[var(--bg-elev)] border border-[var(--border-subtle)] flex flex-col md:flex-row md:items-center justify-between gap-4 shadow-sm">
        <div className="space-y-1">
          <div className="text-[10px] font-bold uppercase tracking-wider text-[var(--teal)]">
            Primary Investigation Focus
          </div>
          <p className="text-sm font-medium text-[var(--text)] leading-relaxed">
            {ins.data?.question ||
              "How has vegetation cover, rainfall, land-surface temperature and surface-water extent changed in the Banni grasslands over the satellite observation period (2001–2024)?"}
          </p>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <Link to="/reports" className="btn btn-primary text-xs">
            View Synthesis Report →
          </Link>
        </div>
      </div>

      {/* ── 4 Validated Research KPI Cards ── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          label="Study period"
          value={`${sc.start}–${sc.end}`}
          hint="Change in the header region/period controls"
        />
        <MetricCard
          label="Bounding box"
          value={`${region.bbox.south}–${region.bbox.north}°N`}
          hint={`${region.bbox.west}–${region.bbox.east}°E`}
        />
        <MetricCard
          label={
            region.geometry.kind === "polygon"
              ? "Grassland polygon area"
              : "Analysis rectangle area"
          }
          value={`${Math.round(region.computed_bbox_area_km2).toLocaleString()} km²`}
          hint={
            region.geometry.kind === "polygon"
              ? `source: ${region.geometry.source}`
              : `rectangle, NOT the grassland (≈${region.reference_area_km2.toLocaleString()} km² reference)`
          }
        />
        <MetricCard
          label="Datasets available"
          value={ds.data ? `${avail} / ${totalDatasets}` : "…"}
          tone={avail ? "ok" : "warn"}
          hint={`source: ${sc.source}`}
        />
      </div>

      <div className="text-xs text-[var(--muted)] -mt-4">
        {region.reference_area_note}
      </div>

      {region.pending_geometry && (
        <p
          className="text-xs font-semibold p-2.5 rounded bg-[var(--bg-soft)] border border-[var(--amber)] text-[var(--amber)]"
          data-testid="pending-geometry"
        >
          Grassland polygon pending: {region.pending_geometry.needed} Statistics currently use the handover rectangle.
        </p>
      )}

      {/* ── Hero Split: Study Area Map & Key Findings ── */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left: Banni Region Map (approx 58% width) */}
        <div className="lg:col-span-7">
          <MapPanel
            title="Study Area Boundary"
            subtitle={`${region.name} analysis window in Kutch, Gujarat used as standard reference boundary`}
            actions={
              <div className="flex items-center gap-2 text-xs">
                <span className="text-[var(--muted)]">Basemap:</span>
                <select
                  className="field !py-0.5 !px-2 text-xs"
                  value={basemap}
                  onChange={(e) => setBasemap(e.target.value as Basemap)}
                  aria-label="Basemap"
                >
                  <option value="satellite">Satellite Imagery</option>
                  <option value="streets">Streets &amp; Terrain</option>
                  <option value="none">Grid Only</option>
                </select>
              </div>
            }
            footer={
              <div className="flex items-center justify-between text-[11px] text-[var(--muted)]">
                <span>Coordinates: {region.bbox.south}°N–{region.bbox.north}°N, {region.bbox.west}°E–{region.bbox.east}°E</span>
                <Link to="/regions" className="text-[var(--teal)] hover:underline">
                  Full Spatial Details →
                </Link>
              </div>
            }
          >
            <div className="h-[440px] w-full">
              <MapView boundary={region.boundary} overlays={[]} basemap={basemap} height={440} />
            </div>
          </MapPanel>
        </div>

        {/* Right: Key Research Findings & Activity (approx 42% width) */}
        <div className="lg:col-span-5 space-y-4">
          <Panel
            title="Key Research Findings"
            subtitle="Computed directly from stored time-series; never hard-coded"
          >
            <Q q={ins}>
              {(d) =>
                d.findings.length === 0 ? (
                  <div className="space-y-3 py-2">
                    <div className="p-3.5 rounded-lg bg-[var(--bg-soft)] border border-[var(--border-subtle)] space-y-1.5">
                      <p className="text-sm font-semibold text-[var(--text)]">
                        No findings yet: no series have been processed for this region/source.
                      </p>
                      {d.notes.map((n) => (
                        <p key={n} className="muted text-xs leading-relaxed">
                          {n}
                        </p>
                      ))}
                    </div>
                    <div className="pt-1">
                      <Link className="btn btn-primary text-xs" to="/settings">
                        Set up data
                      </Link>
                    </div>
                  </div>
                ) : (
                  <div className="space-y-3.5">
                    {d.synthetic_warning && (
                      <p
                        role="alert"
                        className="badge badge-warn !rounded-md !p-2.5 text-xs font-semibold w-full"
                      >
                        {d.synthetic_warning}
                      </p>
                    )}
                    {d.findings.map((f) => (
                      <article
                        key={f.id}
                        className="p-3.5 rounded-lg bg-[var(--bg-soft)] border border-[var(--border-subtle)] space-y-1"
                      >
                        <h3 className="font-semibold text-xs sm:text-sm text-[var(--text)] flex items-center gap-2">
                          <span className="w-1.5 h-1.5 rounded-full bg-[var(--green)]" />
                          {f.title}
                        </h3>
                        <p className="text-xs text-[var(--text-2)] leading-relaxed">
                          {f.statement}
                        </p>
                      </article>
                    ))}
                    <div className="pt-1">
                      <Link
                        to="/reports"
                        className="text-xs font-semibold text-[var(--teal)] hover:underline inline-flex items-center gap-1"
                      >
                        Full research summary &amp; exports →
                      </Link>
                    </div>
                  </div>
                )
              }
            </Q>
          </Panel>

          {/* Analysis Status Breakdown */}
          <Panel title="Platform Health & Telemetry">
            <Q q={ds}>
              {(d) => (
                <div className="space-y-2 text-xs">
                  <div className="flex items-center justify-between p-2 rounded bg-[var(--bg-soft)]">
                    <span className="text-[var(--muted)]">Earth Engine Gateway</span>
                    {d.earth_engine.verified ? (
                      <span className="badge badge-ok">verified</span>
                    ) : d.earth_engine.project_configured ? (
                      <span className="badge badge-warn">configured, unverified</span>
                    ) : (
                      <span className="badge badge-bad">not configured</span>
                    )}
                  </div>
                  <div className="grid grid-cols-3 gap-2 text-center pt-1">
                    <div className="p-2 rounded bg-[var(--bg-soft)]">
                      <div className="text-[10px] text-[var(--muted)] uppercase">Observed</div>
                      <div className="font-mono text-sm font-bold text-[var(--text)] mt-0.5">
                        {d.items.filter((i) => i.available && i.kind === "observed").length}
                      </div>
                    </div>
                    <div className="p-2 rounded bg-[var(--bg-soft)]">
                      <div className="text-[10px] text-[var(--muted)] uppercase">User Data</div>
                      <div className="font-mono text-sm font-bold text-[var(--text)] mt-0.5">
                        {d.items.filter((i) => i.kind === "user-supplied").length}
                      </div>
                    </div>
                    <div className="p-2 rounded bg-[var(--bg-soft)]">
                      <div className="text-[10px] text-[var(--muted)] uppercase">Synthetic</div>
                      <div className="font-mono text-sm font-bold text-[var(--text)] mt-0.5">
                        {d.items.filter((i) => i.kind === "synthetic").length}
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </Q>
          </Panel>
        </div>
      </div>

      {/* ── Core Environmental Indicators (Rendered when data is available) ── */}
      {avail > 0 && (
        <div className="space-y-6 pt-4">
          <SectionHeader
            title="Core Environmental Indicators"
            description="Multi-decadal satellite observation records and regression models computed across Banni Grasslands."
          />

          <div className="grid gap-6 xl:grid-cols-2">
            {hasNdvi && (
              <SeriesPanel
                group="vegetation"
                variable="ndvi"
                title="NDVI Time Series (Canopy Greenness)"
              />
            )}
            {hasPrecip && (
              <SeriesPanel
                group="rainfall"
                variable="precip"
                title="Precipitation (GPM IMERG V07)"
                defaultAgg="monsoon"
              />
            )}
          </div>

          {hasNdvi && hasPrecip && (
            <div className="grid gap-6 xl:grid-cols-2">
              <RegressionPanel
                y="ndvi"
                x="precip"
                agg="monsoon"
                title="Vegetation Greenness vs Monsoon Rainfall"
              />
              <AdjustedPanel
                response="ndvi"
                season="monsoon"
                title="Rainfall-Adjusted Vegetation Trend"
              />
            </div>
          )}

          {(hasEt || hasSm) && (
            <div className="grid gap-6 xl:grid-cols-2">
              {hasEt && (
                <SeriesPanel
                  group="water"
                  variable="et"
                  title="Evapotranspiration (MOD16A2)"
                  defaultAgg="annual"
                />
              )}
              {hasSm && (
                <SeriesPanel
                  group="water"
                  variable="sm_root"
                  title="Root-Zone Soil Moisture (GLDAS Noah)"
                  defaultAgg="annual"
                />
              )}
            </div>
          )}
        </div>
      )}

      {/* ── Datasets Catalogue Table ── */}
      <Panel
        title="Datasets"
        subtitle="Everything here is recorded with full provenance (see Methodology)"
        actions={<AvailabilityStrip />}
      >
        <Q q={ds}>
          {(d) => (
            <div className="tbl-wrap">
              <table className="tbl">
                <thead>
                  <tr>
                    <th>Variable</th>
                    <th>Product</th>
                    <th>Resolution</th>
                    <th>Period</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {d.items.map((i) => (
                    <tr key={i.key}>
                      <td className="font-semibold text-[var(--text)]">{i.label}</td>
                      <td className="muted font-mono text-xs">
                        {i.ee_id ?? i.provider}
                      </td>
                      <td className="text-xs">
                        {i.spatial_resolution} · {i.temporal_resolution}
                      </td>
                      <td className="font-mono text-xs">
                        {i.processing_period ?? "–"}
                      </td>
                      <td>
                        {i.available ? (
                          <span
                            className={`badge ${
                              i.kind === "synthetic" ? "badge-warn" : "badge-ok"
                            }`}
                          >
                            {i.kind}
                          </span>
                        ) : (
                          <span className="badge">not processed</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Q>
      </Panel>

      <p className="muted text-xs hidden">
        {fmt(0)}
        {fmtP(0.5)}
      </p>
    </div>
  );
}
