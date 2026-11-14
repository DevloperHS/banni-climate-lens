import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import MapView, { Basemap, Legend, MapPoint, Overlay } from "../components/MapView";
import { ChartFrame, GapChart, LinesChart, StackedShareChart } from "../components/charts";
import { MapPanel, PageHeader, Panel, Q, RequireData, SectionHeader, Select, SyntheticBadge, fmt, fmtP, useApi, useScope } from "../components/ui";
import { CheckTrend, DashCard, DashLayer, Dashboard, SensorIndexChecks, Wrapped, downloadUrl } from "../lib/api";
import { useApp } from "../state/AppState";

type DashId = Dashboard["id"];
const TABS: { id: DashId; label: string; n: string }[] = [
  { id: "rain_green", label: "Rain and Green", n: "1" },
  { id: "water_heat", label: "Water and Heat", n: "2" },
  { id: "where_changed", label: "Where It Changed", n: "3" },
];
const LC_COLORS: Record<string, string> = {
  lc_grassland: "#84cc16", lc_shrubland: "#b45309", lc_savanna: "#ca8a04", lc_cropland: "#ec4899", lc_barren: "#a8a29e", lc_water: "#38bdf8",
};

/* ------------------------------------------------------------------ shared year control */

function YearControl({ years, year, setYear }: { years: number[]; year: number; setYear: (y: number) => void }) {
  const [playing, setPlaying] = useState(false);
  useEffect(() => {
    if (!playing) return;
    const t = setInterval(() => {
      const i = years.indexOf(year);
      if (i < 0 || i >= years.length - 1) { setPlaying(false); return; }
      setYear(years[i + 1]);
    }, 900);
    return () => clearInterval(t);
  }, [playing, year, years, setYear]);
  if (!years.length) return null;
  return (
    <div className="space-y-1.5 p-3 rounded-lg bg-[var(--bg-soft)] border border-[var(--border)]">
      <div className="flex justify-between items-center text-xs">
        <span className="font-semibold text-[var(--muted)]">Year (shared by every panel)</span>
        <div className="flex items-center gap-2">
          <button
            className="btn text-xs"
            onClick={() => { if (!playing && year === years[years.length - 1]) setYear(years[0]); setPlaying(!playing); }}
            aria-label={playing ? "Pause year animation" : "Play year animation"}
          >
            {playing ? "❚❚ Pause" : "▶ Play"}
          </button>
          <span className="font-mono font-bold text-sm text-[var(--text)] px-2 py-0.5 rounded bg-[var(--bg-elev)] border border-[var(--border)]" data-testid="dash-year">
            {year}
          </span>
        </div>
      </div>
      <input
        type="range"
        min={years[0]}
        max={years[years.length - 1]}
        value={year}
        onChange={(e) => { setPlaying(false); setYear(Number(e.target.value)); }}
        aria-label="Dashboard year"
        className="w-full accent-[var(--accent)]"
      />
      <div className="flex justify-between text-[10px] font-mono text-[var(--muted)]">
        <span>{years[0]}</span>
        <span>{years[years.length - 1]}</span>
      </div>
    </div>
  );
}

/** Rain drawn over the map; drop count and speed scale with the selected year's monsoon total within the record's range. */
function RainOverlay({ intensity }: { intensity: number | null }) {
  const drops = useMemo(() => Array.from({ length: 140 }, (_, i) => ({ left: (i * 37.3) % 100, delay: ((i * 0.618) % 1) * 1.4, len: 14 + ((i * 7) % 12) })), []);
  if (intensity === null) return null;
  const n = Math.round(8 + intensity * 132);
  const dur = 1.25 - intensity * 0.6;
  return (
    <div className="rain-layer" aria-hidden="true" data-testid="rain" data-drops={n}>
      {drops.slice(0, n).map((d, i) => (
        <span key={i} className="rain-drop" style={{ left: `${d.left}%`, height: d.len, animationDuration: `${dur}s`, animationDelay: `${d.delay}s` }} />
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ result cards */

function ResultCard({ c }: { c: DashCard }) {
  const tone = c.direction === "increasing" ? "var(--green)" : c.direction === "decreasing" ? "var(--amber)" : "var(--muted)";
  return (
    <div className="p-3 rounded-lg bg-[var(--bg-soft)] border border-[var(--border)] text-xs space-y-1.5" data-testid="result-card">
      <div className="flex justify-between gap-2 items-start">
        <div className="font-semibold text-[var(--text)] text-[13px] leading-snug">{c.role}</div>
        {c.derived && <span className="badge text-[10px] whitespace-nowrap">derived</span>}
      </div>
      {c.available ? (
        <>
          <div className="font-semibold text-sm" style={{ color: tone }}>
            {c.direction === "increasing" ? "▲ " : c.direction === "decreasing" ? "▼ " : "● "}
            {c.direction}
          </div>
          {c.slope !== undefined && (
            <div>
              <span className="muted">Slope </span>
              <b className="font-mono text-[var(--text)]">{c.slope >= 0 ? "+" : ""}{fmt(c.slope, 4)}</b>{" "}
              <span className="muted">{c.slope_unit}</span>
            </div>
          )}
          {c.p !== undefined && (
            <div>
              <span className="muted">p = </span>
              <b className="font-mono text-[var(--text)]">{fmtP(c.p)}</b>{" "}
              <span className="muted">· n={c.n} · {c.period}</span>
            </div>
          )}
          {c.year_term && (
            <div className="muted">
              Second method (… ~ rain + year): <span className="font-mono text-[var(--text)]">{c.year_term.coef >= 0 ? "+" : ""}{fmt(c.year_term.coef, 4)}</span>/yr,
              p = <span className="font-mono text-[var(--text)]">{fmtP(c.year_term.p)}</span>
            </div>
          )}
          <div className="muted font-mono text-[10.5px] pt-1 border-t border-[var(--border)] break-all">{c.dataset}</div>
          <div className="muted text-[10.5px]">{c.test}</div>
        </>
      ) : (
        <>
          <div className="font-semibold text-[var(--amber)]">Not available</div>
          <p className="muted leading-relaxed">{c.reason}</p>
          <div className="muted font-mono text-[10.5px] pt-1 border-t border-[var(--border)] break-all">{c.dataset}</div>
        </>
      )}
    </div>
  );
}

function TrustBox({ limits }: { limits: string[] }) {
  return (
    <div
      role="note"
      aria-label="Before you trust this"
      className="rounded-lg p-4 border text-xs sm:text-sm"
      style={{ borderColor: "var(--amber)", background: "color-mix(in srgb, var(--amber) 8%, transparent)", color: "var(--text-2)" }}
    >
      <div className="font-semibold text-[var(--amber)] mb-1.5">Before you trust this</div>
      <ul className="list-disc pl-5 space-y-1">{limits.map((l, i) => <li key={i}>{l}</li>)}</ul>
    </div>
  );
}

function Sources({ items }: { items: Dashboard["sources"] }) {
  return (
    <Panel title="Sources" subtitle="Every factor on this dashboard, linked to its dataset page.">
      <div className="tbl-wrap">
        <table className="tbl">
          <thead><tr><th>Factor</th><th>Dataset</th><th>Provider</th><th>Resolution</th></tr></thead>
          <tbody>
            {items.map((s) => (
              <tr key={s.key}>
                <td>{s.label}</td>
                <td><a href={s.url} target="_blank" rel="noreferrer noopener" className="font-mono text-xs text-[var(--teal)] hover:underline break-all">{s.dataset}</a></td>
                <td className="text-xs">{s.provider}</td>
                <td className="text-xs muted">{s.resolution}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

/* ------------------------------------------------------------------ dashboard-specific panels */

function RainGreenPanels({ d, year, meta }: { d: Dashboard; year: number; meta: Wrapped<Dashboard>["meta"] }) {
  return (
    <div className="grid gap-5 xl:grid-cols-2">
      {d.derived.map((c) => (
        <Panel key={c.key + c.aggregation} title={c.role} subtitle="Actual NDVI against the NDVI that rainfall alone predicts; the gap between them is shaded.">
          {c.available && c.series?.observed && c.series.predicted ? (
            <div className="space-y-3">
              <ChartFrame title={`NDVI (${c.aggregation === "summer" ? "dry season, Mar–May" : "monsoon, Jun–Sep"})`} meta={meta} filename={`${c.key}_${c.aggregation}_gap`} height={250}>
                <GapChart years={c.series.years} observed={c.series.observed} predicted={c.series.predicted} unit="NDVI" markYear={year} obsName="Actual NDVI" predName="Predicted from rainfall" />
              </ChartFrame>
              {c.verdict && <p className="text-xs sm:text-sm text-[var(--text-2)]"><b className="text-[var(--text)]">Result.</b> {c.verdict}</p>}
              {c.r2_rain !== undefined && <p className="muted text-xs">Rainfall explains R² = <span className="font-mono">{fmt(c.r2_rain, 2)}</span> of the year-to-year variation.</p>}
            </div>
          ) : (
            <p className="muted text-sm">{c.reason}</p>
          )}
        </Panel>
      ))}
    </div>
  );
}

const AGREE_TONE: Record<string, string> = { agree: "var(--green)", partial: "var(--teal)", disagree: "var(--amber)", unavailable: "var(--muted)" };
const AGREE_LABEL: Record<string, string> = { agree: "Checks agree", partial: "Agree so far", disagree: "Checks disagree", unavailable: "Not yet run" };

function TrendCell({ t }: { t?: CheckTrend }) {
  if (!t) return <td className="muted">–</td>;
  const tone = !t.significant ? "var(--muted)" : t.direction === "increasing" ? "var(--green)" : "var(--amber)";
  return (
    <td>
      <div className="font-semibold" style={{ color: tone }}>{t.significant ? t.direction : "no significant trend"}</div>
      <div className="font-mono text-[11px] muted">
        {t.slope >= 0 ? "+" : ""}{t.slope.toFixed(4)}/yr · p = {fmtP(t.p)}
      </div>
    </td>
  );
}

/** Research brief s.7: the same tests on Aqua NDVI and on EVI, to rule out a single-sensor or single-index artefact. */
function SensorIndexChecksPanel({ checks }: { checks: Dashboard["checks"] }) {
  if (!checks) return null;
  if (!("seasons" in checks)) {
    return (
      <Panel title="Sensor and index checks" subtitle="Repeat the tests with the Aqua satellite and with EVI.">
        <p className="muted text-sm">{checks.reason}</p>
      </Panel>
    );
  }
  const c = checks as SensorIndexChecks;
  return (
    <Panel
      title="Sensor and index checks"
      subtitle={`Same tests on a second satellite (Aqua) and a second index (EVI), all over ${c.period}. ${c.note}`}
    >
      <div className="space-y-5" data-testid="sensor-checks">
        {c.seasons.map((s) => (
          <div key={s.season} className="space-y-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="font-semibold text-sm text-[var(--text)]">{s.label} <span className="muted font-normal text-xs">· rain removed using the {s.rain_control}</span></div>
              <span className="badge text-[11px]" style={{ color: AGREE_TONE[s.agreement.status], borderColor: AGREE_TONE[s.agreement.status] }} data-testid={`agreement-${s.season}`}>
                {AGREE_LABEL[s.agreement.status]}
              </span>
            </div>
            <div className="tbl-wrap">
              <table className="tbl text-xs">
                <thead><tr><th>Series</th><th>Trend</th><th>Trend with rain removed</th><th>Rain R²</th><th>… ~ rain + year</th></tr></thead>
                <tbody>
                  {s.rows.map((r) => (
                    <tr key={r.key}>
                      <td>
                        <div className="font-semibold text-[var(--text)]">{r.label}</div>
                        <div className="muted text-[11px]">{r.role}</div>
                      </td>
                      {r.available ? (
                        <>
                          <TrendCell t={r.raw_trend} />
                          <TrendCell t={r.residual_trend} />
                          <td className="font-mono">{fmt(r.r2_rain ?? null, 2)}</td>
                          <td className="font-mono text-[11px]">
                            {r.year_term ? <>{r.year_term.coef >= 0 ? "+" : ""}{r.year_term.coef.toFixed(4)}/yr<br /><span className="muted">p = {fmtP(r.year_term.p)}</span></> : "–"}
                          </td>
                        </>
                      ) : (
                        <td colSpan={4} className="muted">{r.reason}</td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="text-xs sm:text-sm text-[var(--text-2)]">{s.agreement.text}</p>
          </div>
        ))}
        {c.terra_aqua_monsoon && (
          <p className="muted text-xs">
            Terra and Aqua monsoon NDVI move together: r = <span className="font-mono text-[var(--text)]">{fmt(c.terra_aqua_monsoon.pearson_r, 3)}</span> over {c.terra_aqua_monsoon.n} years;
            Aqua minus Terra averages <span className="font-mono text-[var(--text)]">{fmt(c.terra_aqua_monsoon.mean_difference_aqua_minus_terra, 4)}</span> NDVI.
          </p>
        )}
        <p className="muted text-[11px]">{c.method}.</p>
      </div>
    </Panel>
  );
}

function SmallMultiples({ cards, year, meta }: { cards: DashCard[]; year: number; meta: Wrapped<Dashboard>["meta"] }) {
  const ok = cards.filter((c) => c.available && c.series?.values);
  return (
    <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
      {ok.map((c) => (
        <div key={c.key} className="panel !p-3">
          <ChartFrame title={c.role} subtitle={`${c.unit} · Sen trend line dashed`} meta={meta} filename={`${c.key}_trend`} height={170}>
            <LinesChart
              rows={c.series!.years.map((y, i) => ({ x: y, v: c.series!.values![i], t: c.series!.line?.[i], sel: y === year ? c.series!.values![i] : null }))}
              lines={[{ key: "v", name: c.role, dots: false }, { key: "t", name: "Trend", dashed: true, color: "var(--muted)" }, { key: "sel", name: String(year), dots: true, color: "var(--amber)" }]}
            />
          </ChartFrame>
        </div>
      ))}
    </div>
  );
}

function SwipePanel({ layers, year, start }: { layers: DashLayer[]; year: number; start: number }) {
  const sc = useScope();
  const [key, setKey] = useState(layers[0] ? `${layers[0].variable}:${layers[0].season}` : "");
  const [pos, setPos] = useState(50);
  const layer = layers.find((l) => `${l.variable}:${l.season}` === key) ?? layers[0];
  if (!layer) return <p className="muted text-sm">No raster layers have been processed for this dashboard.</p>;
  const before = layer.years.includes(start) ? start : layer.years[0];
  const after = layer.years.includes(year) ? year : layer.years[layer.years.length - 1];
  const url = (y: number) => downloadUrl("/spatial/layer.png", { region: sc.region, source: sc.source, variable: layer.variable, season: layer.season, year: y });
  const b = layer.bounds;
  const aspect = (b.east - b.west) * Math.cos(((b.north + b.south) / 2) * Math.PI / 180) / (b.north - b.south);
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-3 items-end">
        <Select label="Layer" value={key || `${layer.variable}:${layer.season}`} onChange={setKey}
          options={layers.map((l) => ({ value: `${l.variable}:${l.season}`, label: `${l.label} · ${l.season}` }))} />
        <p className="muted text-xs pb-1">Left: <b className="text-[var(--text)]">{before}</b> · Right: <b className="text-[var(--text)]">{after}</b> (move the shared year slider to change)</p>
      </div>
      <div className="swipe-frame" style={{ aspectRatio: String(aspect) }} data-testid="swipe">
        <img src={url(after)} alt={`${layer.label} ${after}`} />
        <img src={url(before)} alt={`${layer.label} ${before}`} style={{ clipPath: `inset(0 ${100 - pos}% 0 0)` }} />
        <div className="swipe-handle" style={{ left: `${pos}%` }} />
      </div>
      <input type="range" min={0} max={100} value={pos} onChange={(e) => setPos(Number(e.target.value))} aria-label="Swipe position" className="w-full accent-[var(--amber)]" />
      {layer.vmin !== null && layer.vmax !== null && <Legend title={layer.label} unit={layer.unit} vmin={layer.vmin} vmax={layer.vmax} cmap={layer.cmap} />}
    </div>
  );
}

interface PixSummary { significant_increase_fdr: number; significant_decrease_fdr: number; pixels_tested: number; pct_increase_fdr: number | null; pct_decrease_fdr?: number | null; years: number[]; method: string }

function WhereChangedPanels({ d, year, meta }: { d: Dashboard; year: number; meta: Wrapped<Dashboard>["meta"] }) {
  const sc = useScope();
  const { region } = useApp();
  const start = region?.study_period.start ?? 2001;
  const pix = useApi<Wrapped<PixSummary>>("/spatial/pixel-trend", { region: sc.region, source: sc.source, variable: "ndvi", season: "monsoon", start: sc.start, end: sc.end, q: 0.05 },
    d.layers.some((l) => l.variable === "ndvi" && l.season === "monsoon"));
  const lc = d.landcover ?? [];
  const years = Array.from(new Set(lc.flatMap((s) => s.years))).sort((a, b) => a - b);
  const rows = years.map((y) => {
    const r: Record<string, number | string> = { x: y };
    lc.forEach((s) => { const i = s.years.indexOf(y); if (i >= 0) r[s.key] = s.values[i]; });
    return r;
  });
  return (
    <>
      <div className="grid gap-5 xl:grid-cols-2">
        <Panel title="Before / after swipe" subtitle="Drag to compare the start of the record with the selected year.">
          <SwipePanel layers={d.layers} year={year} start={start} />
        </Panel>
        <Panel title="Pixel trend: monsoon NDVI" subtitle="Per-pixel Mann-Kendall + Sen slope, Benjamini-Hochberg FDR (q = 0.05). Only significant pixels are coloured on the map.">
          <Q q={pix}>
            {(p) => (
              <div className="space-y-3 text-xs sm:text-sm">
                <div className="grid grid-cols-2 gap-3">
                  <div className="p-3 rounded-lg bg-[var(--bg-soft)] border border-[var(--border)]">
                    <div className="muted text-xs">Significant greening</div>
                    <div className="font-mono font-bold text-lg text-[var(--green)]">{fmt(p.result.pct_increase_fdr, 1)}%</div>
                    <div className="muted text-[11px]">{p.result.significant_increase_fdr.toLocaleString()} pixels</div>
                  </div>
                  <div className="p-3 rounded-lg bg-[var(--bg-soft)] border border-[var(--border)]">
                    <div className="muted text-xs">Significant browning</div>
                    <div className="font-mono font-bold text-lg text-[var(--amber)]">{fmt(p.result.pct_decrease_fdr ?? (100 * p.result.significant_decrease_fdr / Math.max(p.result.pixels_tested, 1)), 1)}%</div>
                    <div className="muted text-[11px]">{p.result.significant_decrease_fdr.toLocaleString()} pixels</div>
                  </div>
                </div>
                <p className="muted text-xs">{p.result.pixels_tested.toLocaleString()} pixels tested, {p.result.years[0]}–{p.result.years[1]}. {p.result.method}.</p>
                <SyntheticBadge meta={p.meta} />
              </div>
            )}
          </Q>
        </Panel>
      </div>
      <Panel title="Share of each land-cover class by year" subtitle="MODIS MCD12Q1 IGBP classes over the analysis rectangle.">
        {rows.length ? (
          <ChartFrame title="Land-cover class shares" meta={meta} filename="landcover_shares" height={280}>
            <StackedShareChart rows={rows} series={lc.map((s) => ({ key: s.key, name: s.label, color: LC_COLORS[s.key] ?? "var(--c4)" }))} />
          </ChartFrame>
        ) : (
          <p className="muted text-sm">Land cover has not been processed for this region.</p>
        )}
      </Panel>
    </>
  );
}

/* ------------------------------------------------------------------ page */

export default function Dashboards() {
  const sc = useScope();
  const { region } = useApp();
  const [params, setParams] = useSearchParams();
  const id = (TABS.find((t) => t.id === params.get("d"))?.id ?? "rain_green") as DashId;
  const q = useApi<Wrapped<Dashboard>>(`/dashboards/${id}`, sc);
  const span = region ? { a: Math.max(region.study_period.start, sc.start ?? 0), b: Math.min(region.study_period.end, sc.end ?? 9999) } : { a: 2001, b: 2024 };
  const years = useMemo(() => Array.from({ length: Math.max(span.b - span.a + 1, 0) }, (_, i) => span.a + i), [span.a, span.b]);
  const [year, setYear] = useState<number>(span.b);
  useEffect(() => { if (!years.includes(year) && years.length) setYear(years[years.length - 1]); }, [years, year]);
  const [layerKey, setLayerKey] = useState("");
  const [mapMode, setMapMode] = useState<"layer" | "trend">("layer");
  const [opacity, setOpacity] = useState(0.85);
  const [basemap, setBasemap] = useState<Basemap>("satellite");

  const d = q.data?.result;
  const layer = d ? d.layers.find((l) => `${l.variable}:${l.season}` === layerKey) ?? d.layers[0] : undefined;
  const layerYear = layer ? (layer.years.includes(year) ? year : null) : null;

  const overlays: Overlay[] = useMemo(() => {
    if (!d) return [];
    if (d.id === "where_changed" && mapMode === "trend" && d.layers.some((l) => l.variable === "ndvi" && l.season === "monsoon")) {
      const b = d.layers.find((l) => l.variable === "ndvi" && l.season === "monsoon")!.bounds;
      return [{ id: "trend", visible: true, opacity, bounds: b, url: downloadUrl("/spatial/pixel-trend.png", { region: sc.region, source: sc.source, variable: "ndvi", season: "monsoon", start: sc.start, end: sc.end, q: 0.05, product: "significant" }) }];
    }
    if (!layer || !layerYear) return [];
    return [{ id: "dash", visible: true, opacity, bounds: layer.bounds, url: downloadUrl("/spatial/layer.png", { region: sc.region, source: sc.source, variable: layer.variable, season: layer.season, year: layerYear }) }];
  }, [d, layer, layerYear, mapMode, opacity, sc.region, sc.source, sc.start, sc.end]);

  const rain = d?.yearly.columns["precip:monsoon"];
  const intensity = useMemo(() => {
    if (!d || d.id !== "rain_green" || !rain) return null;
    const vals = rain.filter((v): v is number => v !== null);
    const v = rain[d.yearly.years.indexOf(year)];
    if (v === null || v === undefined || !vals.length) return null;
    const lo = Math.min(...vals), hi = Math.max(...vals);
    return hi > lo ? (v - lo) / (hi - lo) : 0.5;
  }, [d, rain, year]);

  const wells: MapPoint[] = useMemo(() => {
    const w = d?.cards.find((c) => c.key === "groundwater")?.wells ?? [];
    return w.filter((x) => x.lat !== null && x.lon !== null).map((x) => ({
      id: x.well_id, lat: x.lat!, lon: x.lon!,
      color: x.direction === "increasing" ? "#f59e0b" : x.direction === "decreasing" ? "#38bdf8" : "#94a3b8",
      label: `${x.well_id}: ${x.meaning ?? x.status ?? "untested"}${x.p !== undefined ? ` (p=${fmtP(x.p)})` : ""}`,
    }));
  }, [d]);

  const readout = d ? Object.entries(d.yearly.columns).map(([k, v]) => {
    const c = [...d.cards, ...d.derived].find((x) => `${x.key}:${x.aggregation}` === k);
    return { k, label: c?.role ?? k, unit: c?.unit ?? "", v: v[d.yearly.years.indexOf(year)] };
  }) : [];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Trend Dashboards"
        subtitle="Is the Banni grassland getting greener than its rainfall can explain? Three dashboards on one map and one year slider, computed only from stored satellite series."
        badges={<span className="badge font-mono text-[11px]">{span.a}–{span.b}</span>}
      />

      <div role="tablist" aria-label="Dashboards" className="flex flex-wrap gap-2">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={t.id === id}
            className={`btn text-xs ${t.id === id ? "btn-primary" : ""}`}
            onClick={() => { setParams({ d: t.id }); setLayerKey(""); setMapMode("layer"); }}
          >
            <span className="font-mono opacity-70">{t.n}</span> {t.label}
          </button>
        ))}
      </div>

      <RequireData keys={["ndvi"]} what="MODIS NDVI">
        <Q q={q} h={520}>
          {(w) => {
            const dd = w.result;
            return (
              <>
                <SectionHeader title={`${TABS.find((t) => t.id === dd.id)?.n}. ${dd.title}`} description={dd.question} />

                <div className="grid gap-5 xl:grid-cols-[1fr_320px]">
                  <MapPanel
                    title={dd.id === "where_changed" && mapMode === "trend" ? "Significant NDVI trend (monsoon, FDR-corrected)" : layer ? `${layer.label} · ${layer.season} · ${layerYear ?? "no data for this year"}` : "Banni map"}
                    subtitle={dd.id === "rain_green" ? "Rain falls harder in wetter monsoons; the ground colour is that year's NDVI." : dd.id === "water_heat" ? "One layer at a time. Wells: amber = deepening, blue = shallowing, grey = no significant change." : "Green = significant greening, amber = significant browning; other pixels are not coloured."}
                  >
                    <div className="relative">
                      <MapView boundary={region?.boundary} overlays={overlays} basemap={basemap} height={460} points={dd.id === "water_heat" ? wells : undefined} />
                      {dd.id === "rain_green" && <RainOverlay intensity={intensity} />}
                    </div>
                  </MapPanel>

                  <div className="space-y-4">
                    <YearControl years={years} year={year} setYear={setYear} />
                    {dd.id === "where_changed" && (
                      <Select label="Map shows" value={mapMode} onChange={setMapMode}
                        options={[{ value: "layer", label: "Selected year" }, { value: "trend", label: "Pixel trend (significant only)" }]} />
                    )}
                    {dd.layers.length > 0 && !(dd.id === "where_changed" && mapMode === "trend") && (
                      <Select label="Map layer" value={layer ? `${layer.variable}:${layer.season}` : ""} onChange={setLayerKey}
                        options={dd.layers.map((l) => ({ value: `${l.variable}:${l.season}`, label: `${l.label} · ${l.season}` }))} />
                    )}
                    <label className="flex flex-col gap-1.5 text-xs text-[var(--muted)] font-medium">
                      <div className="flex justify-between"><span>Layer opacity</span><span className="font-mono text-[var(--text)]">{Math.round(opacity * 100)}%</span></div>
                      <input type="range" min={0.1} max={1} step={0.05} value={opacity} onChange={(e) => setOpacity(Number(e.target.value))} aria-label="Dashboard layer opacity" className="w-full accent-[var(--accent)]" />
                    </label>
                    <Select label="Basemap" value={basemap} onChange={setBasemap}
                      options={[{ value: "satellite", label: "Satellite Imagery (Esri)" }, { value: "streets", label: "Street Map (OSM)" }, { value: "none", label: "None" }]} />
                    {layer && layer.vmin !== null && layer.vmax !== null && !(dd.id === "where_changed" && mapMode === "trend") && (
                      <Legend title={layer.label} unit={layer.unit} vmin={layer.vmin} vmax={layer.vmax} cmap={layer.cmap} />
                    )}
                    {readout.length > 0 && (
                      <div className="p-3 rounded-lg bg-[var(--bg-soft)] border border-[var(--border)] text-xs space-y-1" data-testid="year-readout">
                        <div className="font-semibold text-[var(--text)] mb-1">Values in {year}</div>
                        {readout.map((r) => (
                          <div key={r.k} className="flex justify-between gap-3">
                            <span className="muted truncate">{r.label}</span>
                            <span className="font-mono text-[var(--text)] whitespace-nowrap">{r.v === null || r.v === undefined ? "–" : fmt(r.v, 3)}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>

                <SectionHeader title="Result per factor" description="Hamed-Rao corrected Mann-Kendall test and Sen's slope on yearly values; derived rows remove the rainfall effect by OLS residuals." />
                <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
                  {[...dd.cards, ...dd.derived].map((c) => <ResultCard key={`${c.key}:${c.aggregation}`} c={c} />)}
                </div>

                {dd.id === "rain_green" && (
                  <>
                    <RainGreenPanels d={dd} year={year} meta={w.meta} />
                    <SensorIndexChecksPanel checks={dd.checks} />
                  </>
                )}
                {dd.id === "water_heat" && (
                  <>
                    <SectionHeader title="Time series with trend lines" description="One small chart per factor; the amber dot marks the selected year." />
                    <SmallMultiples cards={dd.cards} year={year} meta={w.meta} />
                  </>
                )}
                {dd.id === "where_changed" && <WhereChangedPanels d={dd} year={year} meta={w.meta} />}

                <TrustBox limits={dd.limits} />
                <Sources items={dd.sources} />
              </>
            );
          }}
        </Q>
      </RequireData>
    </div>
  );
}
