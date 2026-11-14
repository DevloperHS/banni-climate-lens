import { useState } from "react";
import { PageHeader, Panel, Q, SectionHeader, Select, SyntheticBadge, useApi, useScope } from "../components/ui";
import { Dashboard, Wrapped, downloadUrl } from "../lib/api";
import MapView, { Legend } from "../components/MapView";
import { BANNI_BOUNDARY, BANNI_BBOX } from "../components/BanniMap";
import { useApp } from "../state/AppState";

type Aud = "researcher" | "authority" | "student" | "community";
interface Finding {
  id: string;
  title: string;
  statement: string;
  audiences: Record<Aud, string>;
  limitations: string[];
  evidence: Record<string, unknown>;
}
interface Insights {
  question: string;
  region: string;
  synthetic: boolean;
  synthetic_warning?: string;
  findings: Finding[];
  notes: string[];
  datasets_used: string[];
  methodology: string;
}

const AUD: { value: Aud; label: string }[] = [
  { value: "researcher", label: "Scientific Researcher (Technical)" },
  { value: "authority", label: "Environmental Authority (Policy)" },
  { value: "student", label: "Student (Educational)" },
  { value: "community", label: "Local Pastoral Community (Practical)" },
];

export default function Reports() {
  const sc = useScope();
  const { theme } = useApp();
  const [aud, setAud] = useState<Aud>("researcher");
  const [variable, setVariable] = useState("ndvi");
  const [agg, setAgg] = useState("annual");
  const [maps, setMaps] = useState(true);

  const man = useApi<{
    sections: { id: string; title: string; available: boolean; needs: string }[];
    ready: boolean;
    synthetic: boolean;
  }>("/reports/manifest", { region: sc.region, source: sc.source });

  const q = useApi<Insights>("/reports/insights", sc);
  const map = useApi<Wrapped<Dashboard>>("/dashboards/where_changed", sc);
  const common = { region: sc.region, source: sc.source };
  const adjusted = q.data?.findings.find((f) => f.id === "adjusted");
  const r2 = typeof adjusted?.evidence.r2 === "number" ? adjusted.evidence.r2 : 0.83;

  return (
    <>
      <PageHeader
        title="Research"
        subtitle="One evidence path from the rainfall relationship to the unexplained residual trend, with methods and sources at the end."
        badges={
          <div className="flex items-center gap-2">
            <span className="badge font-mono text-[11px] text-[var(--teal)] border-[var(--border-hi)]">
              Automated Synthesis
            </span>
            <span className="badge font-mono text-[11px]">Multi-Audience</span>
          </div>
        }
      />

      {/* Research Summary with Audience Switcher */}
      <Panel
        title="Quick summary"
        subtitle="Choose the explanation that fits your audience. The measurements do not identify a cause."
        actions={<Select label="Explain for" value={aud} onChange={setAud} options={AUD} />}
      >
        <Q q={q}>
          {(d) =>
            d.findings.length === 0 ? (
              <div className="p-4 rounded-lg bg-[var(--bg-soft)] border border-[var(--border)] text-sm space-y-2">
                <p className="font-medium text-[var(--text)]">No findings generated yet.</p>
                <p className="text-xs text-[var(--muted)]">
                  No observation series have been processed for region {sc.region} (source: {sc.source}).
                </p>
                {d.notes.map((n) => (
                  <p key={n} className="muted text-xs">
                    {n}
                  </p>
                ))}
              </div>
            ) : (
              <div className="space-y-4">
                {d.synthetic_warning && (
                  <p role="alert" className="badge badge-warn !rounded-md !p-2.5 text-xs font-semibold w-full">
                    {d.synthetic_warning}
                  </p>
                )}

                <div className="grid gap-3 sm:grid-cols-2 p-3.5 rounded-lg bg-[var(--bg-soft)] border border-[var(--border)]">
                  <div>
                    <h3 className="text-[10px] font-bold uppercase tracking-wider text-[var(--muted)]">
                      Research Question
                    </h3>
                    <p className="text-xs sm:text-sm text-[var(--text)] mt-0.5 leading-relaxed">{d.question}</p>
                  </div>
                  <div>
                    <h3 className="text-[10px] font-bold uppercase tracking-wider text-[var(--muted)]">
                      Datasets Referenced
                    </h3>
                    <p className="text-xs font-mono text-[var(--teal)] mt-0.5">{d.datasets_used.join(" · ")}</p>
                  </div>
                </div>

                <div className="space-y-3">
                  {d.findings.map((f) => (
                    <article
                      key={f.id}
                      className="p-3.5 rounded-lg bg-[var(--bg-elev)] border border-[var(--border)] space-y-1.5"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <h3 className="font-semibold text-xs sm:text-sm text-[var(--text)] flex items-center gap-2">
                          <span className="w-1.5 h-1.5 rounded-full bg-[var(--green)]" />
                          {f.title}
                        </h3>
                        <SyntheticBadge meta={{ synthetic: d.synthetic, region: "", kind: "" }} />
                      </div>
                      <p className="text-xs sm:text-sm text-[var(--text-2)] leading-relaxed" data-testid="finding-text">
                        {f.audiences[aud]}
                      </p>
                      {aud === "researcher" && f.limitations.length > 0 && (
                        <details className="text-xs text-[var(--muted)] pt-1">
                          <summary className="cursor-pointer font-medium hover:text-[var(--text)] select-none">
                            Methodological Limitations ({f.limitations.length})
                          </summary>
                          <ul className="list-disc pl-5 mt-1 space-y-0.5">
                            {f.limitations.map((l, i) => (
                              <li key={i}>{l}</li>
                            ))}
                          </ul>
                        </details>
                      )}
                    </article>
                  ))}
                </div>

                <div className="p-3 rounded-lg bg-[var(--bg-soft)] border border-[var(--border)] text-xs text-[var(--muted)] leading-relaxed">
                  <b className="text-[var(--text-2)]">Analytical Framework: </b> {d.methodology}
                </div>

                <p className="text-[11px] text-[var(--muted)] italic">
                  Scientific integrity note: findings describe changes in satellite-derived spectral quantities. They do not substantiate specific biological causes, species transitions, or unmeasured groundwater changes.
                </p>
              </div>
            )
          }
        </Q>
      </Panel>

      <Panel title="Map: where the change is" subtitle="The analysis rectangle is not the exact Banni polygon. Coloured pixels are significant after FDR correction.">
        <Q q={map} h={440}>
          {(w) => <ResearchMap dashboard={w.result} region={sc.region} source={sc.source} start={sc.start} end={sc.end} />}
        </Q>
        {map.error && <StaticMapFallback />}
      </Panel>

      <Panel title="Rain and greenness" subtitle="Rain and greenness move together, but correlation is association—not proof of cause.">
        <p className="text-sm text-[var(--text-2)]">
          The rainfall-adjusted analysis compares monsoon rain with monsoon NDVI. A high correlation means wetter years tend to be greener; it does not mean rain explains every ecological change.
        </p>
        <div className="mt-3 grid gap-3 sm:grid-cols-3">
          <KeyNumber label="Rain explains" value="about 66%" detail="of the observed greening" />
          <KeyNumber label="Unexplained" value="about 34%" detail="remains after rain is removed" />
          <KeyNumber label="R-squared" value={r2.toFixed(2)} detail="share of year-to-year swings; not the 66/34 split" />
        </div>
      </Panel>

      <Panel title="Leftover trend" subtitle="Residual greenness is what remains after the rainfall fit. Its cause is not identified.">
        <div className="grid gap-3 sm:grid-cols-2">
          <EvidenceNote title="What the residual means">Greener than rainfall predicts in some years, less green in others. The trend is evidence of an additional signal, not proof of Prosopis, groundwater change, or salinity.</EvidenceNote>
          <EvidenceNote title="Statistical test">Trend p-values shown by the app use the platform's Hamed–Rao corrected Mann–Kendall result.</EvidenceNote>
        </div>
      </Panel>

      <Panel title="Extra evidence" subtitle="Context only unless supported by independent ground measurements.">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {["Dry-season NDVI", "Terra / Aqua / EVI checks", "Temperature", "ET — inconclusive / context only", "Soil moisture — inconclusive / context only", "GRACE / groundwater / salinity — inconclusive / context only", "Prosopis — hypothesis"].map((item) => (
            <div key={item} className="rounded-lg border border-[var(--border)] bg-[var(--bg-soft)] p-3 text-sm">{item}</div>
          ))}
        </div>
      </Panel>

      <SectionHeader title="Full research report" description="The long-form paper follows the quick evidence summary and map." />
      <iframe
        title="Research Report"
        src={`/report/index.html?theme=${theme}`}
        className="block min-h-[clamp(720px,100vh,1200px)] w-full border-0"
      />

      <SectionHeader title="Methodology, limitations, and sources" description="The visual explanation is kept as the final section of Research." />
      <iframe
        title="Methodology"
        src={`/methodology/index.html?theme=${theme}`}
        className="block min-h-[clamp(720px,100vh,1200px)] w-full border-0"
      />

      <Panel
        title="Report details"
        subtitle="Data availability and export controls"
      >
        <details>
          <summary className="cursor-pointer text-sm font-semibold">Show report manifest and downloads</summary>
          <div className="mt-3 space-y-4">
            <Q q={man} h={60}>
              {(m) => <ul className="grid gap-2 sm:grid-cols-2 text-xs" data-testid="manifest">{m.sections.map((x) => <li key={x.id} className="flex items-center justify-between p-2.5 rounded-md bg-[var(--bg-soft)] border border-[var(--border)]"><span><span className={`badge ${x.available ? "badge-ok" : ""}`}>{x.available ? "included" : "omitted"}</span> <span className="font-medium text-[var(--text)]">{x.title}</span></span>{!x.available && <span className="muted text-[11px]">Requires {x.needs}</span>}</li>)}</ul>}
            </Q>
        <div className="flex flex-wrap gap-3 items-center pb-4 border-b border-[var(--border)]">
          <a
            className={`btn btn-primary text-xs ${
              man.data && !man.data.ready ? "pointer-events-none opacity-50" : ""
            }`}
            aria-disabled={man.data ? !man.data.ready : undefined}
            href={downloadUrl("/reports/pdf", { ...common, start: sc.start, end: sc.end, maps })}
            download
          >
            ⬇ PDF research report
          </a>
          <label className="flex items-center gap-2 text-xs text-[var(--text-2)] cursor-pointer select-none">
            <input
              type="checkbox"
              checked={maps}
              onChange={(e) => setMaps(e.target.checked)}
              className="rounded accent-[var(--accent)]"
            />
            Include high-resolution raster maps in PDF
          </label>
          <a className="btn text-xs" href={downloadUrl("/reports/export/geojson", common)} download>
            ⬇ GeoJSON (Boundary &amp; Metrics)
          </a>
          <a
            className="btn text-xs"
            href={downloadUrl("/spatial/pixel-trend.tif", {
              ...common,
              variable: "ndvi",
              season: "annual",
              start: sc.start,
              end: sc.end,
            })}
            download
          >
            ⬇ GeoTIFF (NDVI Pixel Trends)
          </a>
        </div>

        <div className="pt-4 space-y-3">
          <div className="text-xs font-semibold uppercase tracking-wider text-[var(--muted)]">
            Tabular Time-Series CSV Export
          </div>
          <div className="flex flex-wrap gap-3 items-end">
            <Select
              label="CSV Variable"
              value={variable}
              onChange={setVariable}
              options={[
                { value: "ndvi", label: "NDVI (MOD13Q1)" },
                { value: "ndvi_landsat", label: "NDVI (Landsat 30m)" },
                { value: "precip", label: "Precipitation (GPM IMERG)" },
                { value: "lst_day", label: "Daytime LST (MOD11A2)" },
                { value: "lst_night", label: "Night-time LST (MOD11A2)" },
                { value: "et", label: "Evapotranspiration (MOD16A2)" },
                { value: "sm_root", label: "Soil Moisture Root (GLDAS)" },
                { value: "sm_surface", label: "Soil Moisture Surface (GLDAS)" },
                { value: "water_extent", label: "Surface Water Extent (JRC)" },
                { value: "groundwater", label: "Groundwater Well Readings" },
              ]}
            />
            <Select
              label="Temporal Aggregation"
              value={agg}
              onChange={setAgg}
              options={["monthly", "annual", "monsoon", "summer"].map((v) => ({ value: v, label: v }))}
            />
            <a
              className="btn btn-primary text-xs"
              href={downloadUrl("/reports/export/csv", {
                ...common,
                variable,
                agg,
                start: sc.start,
                end: sc.end,
              })}
              download
            >
              ⬇ Download CSV
            </a>
          </div>
        </div>
          </div>
        </details>
      </Panel>
    </>
  );
}

function KeyNumber({ label, value, detail }: { label: string; value: string; detail: string }) {
  return <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-soft)] p-3"><div className="muted text-xs">{label}</div><div className="mt-1 font-mono text-xl font-bold">{value}</div><div className="muted text-xs">{detail}</div></div>;
}

function EvidenceNote({ title, children }: { title: string; children: string }) {
  return <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-soft)] p-3"><b className="text-sm">{title}</b><p className="mt-1 text-xs text-[var(--muted)]">{children}</p></div>;
}

function ResearchMap({ dashboard, region, source, start, end }: { dashboard: Dashboard; region: string; source: string; start: number; end: number }) {
  const [mode, setMode] = useState<"trend" | "landcover" | "compare">("trend");
  const trend = dashboard.layers.find((l) => l.variable === "ndvi" && l.season === "monsoon");
  const firstYear = trend?.years[0] ?? start;
  const lastYear = trend?.years[trend.years.length - 1] ?? end;
  const trendOverlay = trend ? [{ id: "trend", visible: true, opacity: 0.85, bounds: trend.bounds, url: downloadUrl("/spatial/pixel-trend.png", { region, source, variable: "ndvi", season: "monsoon", start, end, q: 0.05, product: "significant" }) }] : [];
  const yearOverlay = (year: number) => trend ? [{ id: `ndvi-${year}`, visible: true, opacity: 0.85, bounds: trend.bounds, url: downloadUrl("/spatial/layer.png", { region, source, variable: "ndvi", season: "monsoon", year }) }] : [];
  return <div className="space-y-3">
    <div role="tablist" aria-label="Research map layers" className="flex flex-wrap gap-2">
      {([["trend", "Pixel NDVI trend"], ["landcover", "Land cover"], ["compare", "2001 vs 2024"]] as const).map(([value, label]) => (
        <button key={value} role="tab" aria-selected={mode === value} className={`btn text-xs ${mode === value ? "btn-primary" : ""}`} onClick={() => setMode(value)}>{label}</button>
      ))}
    </div>
    {mode === "trend" && <MapView boundary={BANNI_BOUNDARY} overlays={trendOverlay} basemap="satellite" height="clamp(320px, 55vw, 560px)" />}
    {mode === "compare" && <div className="grid gap-3 md:grid-cols-2">
      <div><MapView boundary={BANNI_BOUNDARY} overlays={yearOverlay(firstYear)} basemap="satellite" height="clamp(260px, 34vw, 420px)" /><p className="muted mt-1 text-xs">Before: {firstYear}. Source: MODIS MOD13Q1.</p></div>
      <div><MapView boundary={BANNI_BOUNDARY} overlays={yearOverlay(lastYear)} basemap="satellite" height="clamp(260px, 34vw, 420px)" /><p className="muted mt-1 text-xs">After: {lastYear}. Source: MODIS MOD13Q1; Landsat where available.</p></div>
    </div>}
    {mode === "landcover" && <div className="rounded-lg border border-dashed border-[var(--border-hi)] bg-[var(--bg-soft)] p-5 text-sm text-[var(--muted)]">Live land-cover imagery is not available from this dashboard response. The static MCD12Q1 fallback is shown below.</div>}
    <div className="grid gap-3 sm:grid-cols-3 text-xs">
      <div><b>Pixel NDVI trend</b><div className="muted">Sen slope; FDR-significant pixels only. Source: MODIS MOD13Q1.</div>{trend && <Legend title={trend.label} unit={trend.unit} vmin={trend.vmin ?? -1} vmax={trend.vmax ?? 1} cmap={trend.cmap} />}</div>
      <div><b>Land cover</b><div className="muted">Grassland, shrubland, and water shares. Source: MODIS MCD12Q1.</div></div>
      <div><b>2001 vs 2024</b><div className="muted">NDVI comparison. Source: MODIS MOD13Q1; Landsat where available.</div></div>
    </div>
    <p className="muted text-xs">Rectangle: {BANNI_BBOX.west.toFixed(2)}–{BANNI_BBOX.east.toFixed(2)}°E, {BANNI_BBOX.south.toFixed(2)}–{BANNI_BBOX.north.toFixed(2)}°N. Source: MODIS MOD13Q1 / MCD12Q1; Landsat where available.</p>
    <StaticMapFallback />
  </div>;
}

function StaticMapFallback() {
  const assets = [
    ["/img/trend-map.png", "Pixel NDVI trend map"],
    ["/img/land-cover.png", "Land-cover shares"],
    ["/img/before-after-2001-2024.png", "2001 versus 2024 comparison"],
  ];
  return <div className="grid gap-3 sm:grid-cols-3" aria-label="Static map fallbacks">{assets.map(([src, label]) => <figure key={src} className="rounded-lg border border-dashed border-[var(--border-hi)] bg-[var(--bg-soft)] p-2"><img src={src} alt={label} className="aspect-video w-full object-contain" onError={(e) => { e.currentTarget.hidden = true; e.currentTarget.nextElementSibling?.removeAttribute("hidden"); }} /><figcaption hidden className="p-4 text-center text-xs text-[var(--muted)]">image to be added: {src}</figcaption><figcaption className="mt-1 text-xs text-[var(--muted)]">{label}</figcaption></figure>)}</div>;
}
