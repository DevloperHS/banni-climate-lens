import { useState } from "react";
import { PageHeader, Panel, Q, SectionHeader, Select, SyntheticBadge, useApi, useScope } from "../components/ui";
import { downloadUrl } from "../lib/api";

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
  const common = { region: sc.region, source: sc.source };

  return (
    <>
      <PageHeader
        title="Research Reports"
        subtitle="Dynamically generated findings derived exclusively from executed pipeline statistics. Every export embeds full sensor lineage, spatial metadata, and processing provenance."
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
        title="Executive Research Synthesis"
        subtitle="Core empirical findings tailored to specific stakeholder audiences."
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

      {/* Manifest Section */}
      <Panel
        title="Report Section Manifest"
        subtitle="Dynamically generated from current data availability at generation time. Unprocessed sections are omitted and marked with exact missing requisites."
      >
        <Q q={man} h={60}>
          {(m) => (
            <ul className="grid gap-2 sm:grid-cols-2 text-xs" data-testid="manifest">
              {m.sections.map((x) => (
                <li
                  key={x.id}
                  className="flex items-center justify-between p-2.5 rounded-md bg-[var(--bg-soft)] border border-[var(--border)]"
                >
                  <div className="flex items-center gap-2">
                    <span className={`badge ${x.available ? "badge-ok" : ""}`}>
                      {x.available ? "included" : "omitted"}
                    </span>
                    <span className="font-medium text-[var(--text)]">{x.title}</span>
                  </div>
                  {!x.available && (
                    <span className="muted text-[11px]">Requires {x.needs}</span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Q>
      </Panel>

      {/* Export Controls */}
      <SectionHeader
        title="Scientific Data & Document Exports"
        description="Download publication-grade PDFs, GeoJSON vectors, GeoTIFF spatial rasters, and tabular CSV files."
      />

      <Panel title="Document & Spatial Raster Downloads">
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
      </Panel>
    </>
  );
}
