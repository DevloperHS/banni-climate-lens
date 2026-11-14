import { useMemo, useState } from "react";
import MapView, { Basemap, Overlay } from "../components/MapView";
import { PageHeader, Panel, Q, SectionHeader, Select, Stat, fmt, useApi, useScope } from "../components/ui";
import { downloadUrl, Wrapped } from "../lib/api";
import { useApp } from "../state/AppState";
import { Layer } from "./Satellite";
import { AgreementPanel, DifferencePanel } from "../components/panels2";

interface Pix {
  pixels_tested: number;
  fdr_q: number;
  significant_increase_fdr: number;
  significant_decrease_fdr: number;
  not_significant: number;
  significant_increase_uncorrected: number;
  significant_decrease_uncorrected: number;
  pct_increase_fdr: number | null;
  pct_decrease_fdr: number | null;
  mask?: { pixels_masked: number; threshold_pct: number } | null;
  median_slope: number | null;
  years: number[];
  n_years: number;
  bounds: Layer["bounds"];
  method: string;
  limitations: string[];
  slope_unit: string;
  note: string;
}

export default function Spatial() {
  const sc = useScope();
  const { region } = useApp();
  const layers = useApi<{ items: Layer[] }>("/spatial/layers", { region: sc.region, source: sc.source });
  const [variable, setVariable] = useState("ndvi");
  const [season, setSeason] = useState("annual");
  const [q, setQ] = useState("0.05");
  const [product, setProduct] = useState<"class" | "slope" | "uncorrected">("class");
  const [basemap, setBasemap] = useState<Basemap>("satellite");
  const [opacity, setOpacity] = useState(0.85);
  const [mask, setMask] = useState<"none" | "rann_water">("none");

  const items = layers.data?.items ?? [];
  const vars = Array.from(new Set(items.map((l) => l.variable)));
  const seasons = items.filter((l) => l.variable === variable).map((l) => l.season);
  const params = { region: sc.region, source: sc.source, variable, season, start: sc.start, end: sc.end, q, mask };
  const enabled = items.some((l) => l.variable === variable && l.season === season);
  const pix = useApi<Wrapped<Pix>>("/spatial/pixel-trend", params, enabled);

  const overlays: Overlay[] = useMemo(
    () =>
      pix.data
        ? [
            {
              id: "pix",
              visible: true,
              opacity,
              bounds: pix.data.result.bounds,
              url: downloadUrl("/spatial/pixel-trend.png", { ...params, product }),
            },
          ]
        : [],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [pix.data, product, opacity, sc.region, sc.source, variable, season, sc.start, sc.end, q, mask]
  );

  return (
    <>
      <PageHeader
        title="Spatial Analysis"
        subtitle="Vectorised pixel-by-pixel Mann-Kendall tests with Sen's slope estimation across thousands of grid cells. Multiple-hypothesis testing is rigorously controlled using the Benjamini-Hochberg False Discovery Rate (FDR) procedure."
        badges={
          <div className="flex items-center gap-2">
            <span className="badge font-mono text-[11px] text-[var(--teal)] border-[var(--border-hi)]">
              FDR Control (BH q={q})
            </span>
            <span className="badge font-mono text-[11px]">Sen's Slope</span>
          </div>
        }
      />

      <Q q={layers}>
        {(d) =>
          d.items.length === 0 ? (
            <Panel title="No raster stacks">
              <div className="p-4 rounded-lg bg-[var(--bg-soft)] border border-[var(--border)] text-sm space-y-2">
                <p className="font-medium text-[var(--text)]">No raster stacks available.</p>
                <p className="text-xs text-[var(--muted)]">
                  Pixel trend computations require multi-year GeoTIFF stacks. Run stack processing jobs in Settings or enable the synthetic sample.
                </p>
              </div>
            </Panel>
          ) : (
            <>
              <div className="grid gap-5 xl:grid-cols-[330px_1fr]">
                {/* Control Panel */}
                <div className="space-y-4">
                  <Panel title="Analysis Controls" subtitle="Select layer parameters & masks">
                    <div className="space-y-3.5">
                      <Select
                        label="Variable"
                        value={variable}
                        onChange={(v) => {
                          setVariable(v);
                          const s = items.find((l) => l.variable === v)?.season;
                          if (s) setSeason(s);
                        }}
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
                      <Select
                        label="FDR Level (q)"
                        value={q}
                        onChange={setQ}
                        options={[
                          { value: "0.01", label: "q = 0.01 (1% False Discovery Rate)" },
                          { value: "0.05", label: "q = 0.05 (Standard 5% FDR)" },
                          { value: "0.10", label: "q = 0.10 (Relaxed 10% FDR)" },
                        ]}
                      />
                      <Select
                        label="Rann-water mask (JRC)"
                        value={mask}
                        onChange={setMask}
                        options={[
                          { value: "none", label: "None (unmasked)" },
                          { value: "rann_water", label: "Mask water occurrence ≥ 10%" },
                        ]}
                      />
                      <Select
                        label="Map Product"
                        value={product}
                        onChange={setProduct}
                        options={[
                          { value: "class", label: "Significant Trend (FDR-corrected)" },
                          { value: "slope", label: "Trend Magnitude (Sen slope)" },
                          { value: "uncorrected", label: "Uncorrected p<0.05 (diagnostic only)" },
                        ]}
                      />

                      <div className="pt-2 border-t border-[var(--border)] space-y-3">
                        <label className="flex flex-col gap-1 text-xs text-[var(--muted)] font-medium">
                          <div className="flex justify-between">
                            <span>Overlay Opacity</span>
                            <span className="font-mono text-[11px] text-[var(--text)]">{Math.round(opacity * 100)}%</span>
                          </div>
                          <input
                            type="range"
                            min={0.1}
                            max={1}
                            step={0.05}
                            value={opacity}
                            onChange={(e) => setOpacity(Number(e.target.value))}
                            aria-label="Overlay opacity"
                            className="w-full accent-[var(--accent)]"
                          />
                        </label>

                        <Select
                          label="Basemap"
                          value={basemap}
                          onChange={setBasemap}
                          options={[
                            { value: "satellite", label: "Satellite Imagery (Esri)" },
                            { value: "streets", label: "Street Map (OSM)" },
                            { value: "none", label: "None" },
                          ]}
                        />
                      </div>

                      <div className="flex gap-2 pt-2">
                        <a className="btn text-xs flex-1 justify-center" href={downloadUrl("/spatial/pixel-trend.tif", params)} download>
                          ⬇ GeoTIFF (5 bands)
                        </a>
                        <a className="btn text-xs flex-1 justify-center" href={downloadUrl("/spatial/export.png", { ...params, kind: "trend" })} download>
                          ⬇ Map image (PNG)
                        </a>
                      </div>
                    </div>
                    <p className="muted text-[11px] mt-3">Period {sc.start}–{sc.end} (at least 10 valid years required per pixel).</p>
                  </Panel>

                  <Panel title="Map Legend">
                    {product === "slope" ? (
                      <p className="text-xs sm:text-sm text-[var(--text-2)]">
                        Continuous diverged colorbar (red → blue/green): negative → positive Sen slope ({pix.data?.result.slope_unit}), symmetric around zero.
                      </p>
                    ) : (
                      <ul className="text-xs sm:text-sm space-y-2">
                        <li className="flex items-center gap-2">
                          <span style={{ background: "rgb(27,158,119)" }} className="w-3.5 h-3.5 rounded-sm flex-shrink-0" />
                          <span className="text-[var(--text)] font-medium">Significant increase (FDR q={q})</span>
                        </li>
                        <li className="flex items-center gap-2">
                          <span style={{ background: "rgb(217,95,2)" }} className="w-3.5 h-3.5 rounded-sm flex-shrink-0" />
                          <span className="text-[var(--text)] font-medium">Significant decrease (FDR q={q})</span>
                        </li>
                        <li className="flex items-center gap-2">
                          <span style={{ background: "rgba(150,150,150,.4)" }} className="w-3.5 h-3.5 rounded-sm flex-shrink-0 border border-[var(--border)]" />
                          <span className="text-[var(--muted)]">Not statistically significant</span>
                        </li>
                      </ul>
                    )}
                  </Panel>
                </div>

                {/* Spatial Map Display */}
                <Panel
                  title="Pixel Trend Map"
                  subtitle={`${variable.toUpperCase()} (${season}) · Benjamini-Hochberg Multiple-Testing Controlled`}
                  actions={pix.data?.meta.synthetic ? <span className="badge badge-warn">SYNTHETIC SAMPLE</span> : undefined}
                >
                  <div className="rounded-lg overflow-hidden border border-[var(--border)] shadow-sm">
                    <MapView boundary={region?.boundary} overlays={overlays} basemap={basemap} height={520} />
                  </div>
                </Panel>
              </div>

              {/* Statistical Summary of Spatial Testing */}
              <Panel title="Statistical Summary" subtitle="Rigorous demonstration of multiple-testing adjustment">
                <Q q={pix}>
                  {(r) => {
                    const s = r.result;
                    return (
                      <div className="space-y-4">
                        <div className="grid gap-3 grid-cols-2 lg:grid-cols-4">
                          <Stat
                            label="Pixels tested"
                            value={s.pixels_tested.toLocaleString()}
                            hint={`${s.n_years} years (${s.years[0]}–${s.years[1]})`}
                          />
                          <Stat
                            label={`Increase (FDR q=${s.fdr_q})`}
                            value={s.significant_increase_fdr.toLocaleString()}
                            tone="ok"
                            hint={`${fmt(s.pct_increase_fdr, 1)}% of total pixels`}
                          />
                          <Stat
                            label={`Decrease (FDR q=${s.fdr_q})`}
                            value={s.significant_decrease_fdr.toLocaleString()}
                            tone="warn"
                            hint={`${fmt(s.pct_decrease_fdr, 1)}% of total pixels`}
                          />
                          <Stat
                            label="Median Sen slope"
                            value={fmt(s.median_slope, 4)}
                            hint={s.slope_unit}
                          />
                        </div>

                        <div className="p-3.5 rounded-lg bg-[var(--bg-soft)] border border-[var(--border)] text-xs sm:text-sm text-[var(--text-2)] space-y-1.5 leading-relaxed">
                          <p>
                            Without correction, <b className="font-mono text-[var(--text)]">{(s.significant_increase_uncorrected + s.significant_decrease_uncorrected).toLocaleString()}</b> pixels would appear significant at raw p &lt; 0.05; after FDR control (q={s.fdr_q}), <b className="font-mono text-[var(--text)]">{(s.significant_increase_fdr + s.significant_decrease_fdr).toLocaleString()}</b> pixels remain.
                          </p>
                          {s.mask && (
                            <p className="text-[var(--amber)] pt-1" data-testid="mask-summary">
                              Rann-water mask: {s.mask.pixels_masked.toLocaleString()} pixels removed (≥{s.mask.threshold_pct}% long-term water occurrence).
                            </p>
                          )}
                        </div>

                        <div className="text-xs space-y-1 text-[var(--muted)] pt-2 border-t border-[var(--border)]">
                          <p><b>Method.</b> {s.method}</p>
                          <ul className="list-disc pl-5 space-y-0.5">
                            {s.limitations.map((l) => (
                              <li key={l}>{l}</li>
                            ))}
                          </ul>
                        </div>
                      </div>
                    );
                  }}
                </Q>
              </Panel>

              <SectionHeader
                title="Period Difference Analysis"
                description="Comparative baseline contrast (Period B minus Period A) mapping net delta over multi-year windows."
              />
              <DifferencePanel
                variables={vars.map((v) => ({
                  value: v,
                  label: items.find((l) => l.variable === v)!.label,
                  season: items.find((l) => l.variable === v)!.season,
                }))}
              />

              <SectionHeader
                title="Cross-Sensor Spatial Agreement"
                description="Evaluating spatial correlation between 250m MODIS and 30m Landsat gridded trends."
              />
              <AgreementPanel />
            </>
          )
        }
      </Q>
    </>
  );
}
