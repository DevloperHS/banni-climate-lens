import { ReactNode, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, apiGet, apiSend, CompareResult, DatasetItem, downloadUrl, Job, Wrapped } from "../lib/api";
import { useApp } from "../state/AppState";
import { CoefTable, Diagnostics, TrendPanel } from "./analysis";
import { BarsChart, ChartFrame, LinesChart } from "./charts";
import MapView, { Basemap } from "./MapView";
import { Panel, Q, Select, fmt, fmtP, useApi, useScope } from "./ui";

/* ------------------------------------------------------------------ shared: CSV upload control */
export function CsvUpload({ label, path, fields, onDone, accept = ".csv,text/csv", hint }: {
  label: string; path: string; fields: Record<string, string>; onDone?: (r: unknown) => void; accept?: string; hint?: ReactNode;
}) {
  const file = useRef<HTMLInputElement>(null);
  const qc = useQueryClient();
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const go = async () => {
    const f = file.current?.files?.[0];
    if (!f) { setMsg({ ok: false, text: "Choose a CSV file first." }); return; }
    const form = new FormData();
    Object.entries(fields).forEach(([k, v]) => form.set(k, v));
    form.set("file", f);
    setBusy(true); setMsg(null);
    try { const r = await apiSend<unknown>("POST", path, undefined, form); setMsg({ ok: true, text: "Uploaded and validated." }); onDone?.(r); qc.invalidateQueries(); }
    catch (e) { setMsg({ ok: false, text: (e as ApiError).message }); } finally { setBusy(false); }
  };
  return (
    <div className="space-y-1">
      <div className="flex flex-wrap items-end gap-2">
        <label className="text-xs muted flex flex-col gap-1">{label}<input ref={file} type="file" accept={accept} className="field" aria-label={label} /></label>
        <button className="btn btn-primary" onClick={go} disabled={busy}>{busy ? "Uploading…" : "Upload"}</button>
        {msg && <span role="status" className="text-sm" style={{ color: msg.ok ? "var(--green)" : "var(--red)" }}>{msg.text}</span>}
      </div>
      {hint && <p className="muted text-xs">{hint}</p>}
    </div>
  );
}

/* ------------------------------------------------------------------ data availability strip (header) */
const CHIPS: [string, string][] = [["ndvi", "NDVI"], ["precip", "Rain"], ["lst_day", "LST"], ["et", "ET"], ["sm_root", "Soil"], ["water_extent", "Water"], ["salinity_index", "Salinity"], ["groundwater", "Wells"]];
export function AvailabilityStrip() {
  const { regionId, source } = useApp();
  const q = useApi<{ items: DatasetItem[] }>("/datasets", { region: regionId, source, page_size: 100 });
  if (!q.data) return null;
  const by = Object.fromEntries(q.data.items.map((i) => [i.key, i]));
  return (
    <div className="flex flex-wrap gap-1 items-center" aria-label="Data availability" data-testid="availability">
      {CHIPS.map(([k, l]) => {
        const i = by[k]; const ok = !!i?.available;
        return <span key={k} className={`badge ${ok ? (i.kind === "synthetic" ? "badge-warn" : "badge-ok") : ""}`} title={ok ? `${i.kind}, ${i.processing_period ?? ""}` : "not processed"} style={ok ? undefined : { opacity: 0.55 }}>{ok ? "●" : "○"} {l}</span>;
      })}
    </div>
  );
}

/* ------------------------------------------------------------------ environmental comparison */
const VARS: [string, string][] = [["ndvi", "NDVI"], ["precip", "Precipitation"], ["lst_day", "LST day"], ["lst_night", "LST night"], ["et", "ET"], ["sm_root", "Root-zone soil moisture"], ["sm_surface", "Surface soil moisture"], ["water_extent", "Water extent"]];
const AGGS = ["monsoon", "annual", "summer", "winter", "postmonsoon"].map((v) => ({ value: v, label: v }));

function heat(r: number) {
  const a = Math.min(1, Math.abs(r)) * 70;
  return { background: `color-mix(in srgb, ${r >= 0 ? "var(--green)" : "var(--blue)"} ${a}%, transparent)` };
}

export function ComparePanel() {
  const sc = useScope();
  const [sel, setSel] = useState<string[]>(["ndvi", "precip", "lst_day", "et"]);
  const [agg, setAgg] = useState("monsoon");
  const [resp, setResp] = useState("ndvi");
  const [detrend, setDetrend] = useState(false);
  const toggle = (k: string) => setSel((s) => (s.includes(k) ? s.filter((x) => x !== k) : s.length < 6 ? [...s, k] : s));
  const response = sel.includes(resp) ? resp : sel[0];
  const q = useApi<Wrapped<CompareResult>>("/statistics/compare", { region: sc.region, source: sc.source, variables: sel.join(","), agg, response, detrend, start: sc.start, end: sc.end }, sel.length >= 2);
  return (
    <Panel title="Environmental comparison" subtitle="Several variables together: association, prediction and (non-)causation reported separately">
      <fieldset className="mb-3"><legend className="text-xs muted mb-1">Variables (2–6)</legend>
        <div className="flex flex-wrap gap-3">{VARS.map(([k, l]) => <label key={k} className="flex items-center gap-1.5 text-sm"><input type="checkbox" checked={sel.includes(k)} onChange={() => toggle(k)} />{l}</label>)}</div></fieldset>
      <div className="flex flex-wrap gap-3 items-end mb-3">
        <Select label="Season" value={agg} onChange={setAgg} options={AGGS} />
        <Select label="Response" value={response} onChange={setResp} options={sel.map((k) => ({ value: k, label: VARS.find((v) => v[0] === k)?.[1] ?? k }))} />
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={detrend} onChange={(e) => setDetrend(e.target.checked)} /> Remove linear trends first</label>
      </div>
      {sel.length < 2 ? <p role="alert" style={{ color: "var(--amber)" }}>Select at least two variables.</p> : (
        <Q q={q}>{(d) => {
          const r = d.result;
          const rows = r.years.map((y, i) => ({ x: y, ...Object.fromEntries(r.variables.map((v) => [v, r.zscores[v][i]])) }));
          return (
            <div className="space-y-5" data-testid="compare">
              <div className="tbl-wrap"><table className="tbl" aria-label="Correlation matrix"><thead><tr><th>Pearson r</th>{r.variables.map((v) => <th key={v}>{v}</th>)}</tr></thead><tbody>
                {r.variables.map((a, i) => <tr key={a}><td className="font-semibold">{a}</td>{r.variables.map((b, j) => <td key={b} style={heat(r.pearson[i][j])} title={`p=${fmtP(r.pearson_p[i][j])}`}>{fmt(r.pearson[i][j], 2)}</td>)}</tr>)}
              </tbody></table></div>
              <div className="tbl-wrap"><table className="tbl"><thead><tr><th>Pair</th><th>Pearson r</th><th>p</th><th>p (BH-adjusted)</th><th>Spearman ρ</th><th></th></tr></thead><tbody>
                {r.pairs.map((p) => <tr key={p.a + p.b}><td>{p.a} – {p.b}</td><td>{fmt(p.pearson_r, 2)}</td><td>{fmtP(p.pearson_p)}</td><td>{fmtP(p.pearson_p_bh)}</td><td>{fmt(p.spearman_rho, 2)}</td><td>{p.significant_bh && <span className="badge badge-ok">significant after FDR</span>}</td></tr>)}
              </tbody></table></div>
              <p className="muted text-xs">{r.association_note}</p>
              <ChartFrame title="Standardised time series (z-scores)" meta={d.meta as never} filename={`compare_${agg}`} height={260} subtitle={`n=${r.n} years ${r.detrended ? "· linear trends removed" : ""}`}>
                <LinesChart rows={rows} lines={r.variables.map((v) => ({ key: v, name: v }))} />
              </ChartFrame>
              {r.regression && r.prediction && (
                <div className="grid gap-4 xl:grid-cols-2">
                  <div><h3 className="text-sm font-semibold mb-1">Association: {r.regression.response} ~ {r.regression.predictors.join(" + ")}</h3>
                    <CoefTable coefs={r.regression.coefficients} r2={r.regression.r2} n={r.n} />
                    {r.regression.vif && <p className="text-xs mt-1">VIF: {Object.entries(r.regression.vif).map(([k, v]) => `${k} ${fmt(v, 1)}`).join(" · ")} {r.regression.collinearity_warning && <span className="badge badge-warn">collinearity: coefficients unstable</span>}</p>}
                    <div className="mt-2"><Diagnostics d={r.regression.diagnostics} /></div></div>
                  <div className="space-y-3">
                    <div className="panel !p-3 !bg-[var(--bg-soft)]"><h3 className="text-sm font-semibold">Prediction (held-out years)</h3>
                      <p className="text-sm mt-1">In-sample R² <b>{fmt(r.prediction.r2_in_sample, 2)}</b> · leave-one-out R² <b data-testid="loo">{fmt(r.prediction.r2_loo_cv, 2)}</b></p><p className="muted text-xs">{r.prediction.note}</p></div>
                    {r.partial_correlations && <div><h3 className="text-sm font-semibold mb-1">Partial correlations with {r.regression.response}</h3>
                      <table className="tbl"><tbody>{r.partial_correlations.map((p) => <tr key={p.variable}><td>{p.variable}</td><td>r = {fmt(p.r, 2)}</td><td>p = {p.p == null ? "–" : fmtP(p.p)}</td><td className="muted">controlling {p.controls.join(", ") || "nothing"}</td></tr>)}</tbody></table></div>}
                    <p className="text-xs" style={{ color: "var(--amber)" }}>{r.causation_note}</p>
                  </div>
                </div>)}
              {r.anomaly_years.length > 0 && <div><h3 className="text-sm font-semibold mb-1">Anomalous years (|z| &gt; 2)</h3>
                <ul className="text-sm list-disc pl-5">{r.anomaly_years.map((a) => <li key={a.year}>{a.year}: {a.variables.join(", ")} {a.coincident && <span className="badge badge-warn">coincident</span>}</li>)}</ul></div>}
              <p className="muted text-xs">{r.statement}</p>
            </div>);
        }}</Q>)}
    </Panel>
  );
}

/* ------------------------------------------------------------------ region (geometry) comparison */
interface RegionCmp { items: { region: string; name?: string; geometry?: { id: string; kind: string; area_km2: number }; status: string; direction?: string; p?: number; slope?: number; ci_low?: number; ci_high?: number; test?: string; n?: number; message?: string }[]; pending_geometries: { region: string; needed: string }[]; note: string }
export function RegionComparePanel() {
  const sc = useScope();
  const { regions } = useApp();
  const ids = Array.from(new Set([...regions.map((r) => r.id), "banni_grassland"])).join(",");
  const q = useApi<Wrapped<RegionCmp>>("/statistics/region-comparison", { regions: ids, variable: "ndvi", agg: "monsoon", source: sc.source });
  return (
    <Panel title="Geometry comparison: rectangle vs grassland" subtitle="Monsoon NDVI trend over each analysis geometry (kept as separate regions)">
      <Q q={q} h={80}>{(d) => (
        <div className="space-y-2">
          <div className="tbl-wrap"><table className="tbl"><thead><tr><th>Geometry</th><th>Area</th><th>Trend</th><th>p</th><th>Sen slope/yr [95% CI]</th></tr></thead><tbody>
            {d.result.items.map((i) => <tr key={i.region}><td>{i.name ?? i.region}<div className="muted text-xs">{i.geometry?.id}</div></td><td>{i.geometry ? `${Math.round(i.geometry.area_km2).toLocaleString()} km²` : "–"}</td>
              {i.status === "ok" ? <><td>{i.direction}</td><td>{fmtP(i.p!)}</td><td>{fmt(i.slope, 4)} [{fmt(i.ci_low, 4)}, {fmt(i.ci_high, 4)}]</td></> : <td colSpan={3} className="muted">{i.status === "unknown region" ? "not available (no polygon supplied)" : i.message ?? i.status}</td>}</tr>)}
          </tbody></table></div>
          {d.result.pending_geometries.map((p) => <p key={p.region} className="text-xs" style={{ color: "var(--amber)" }}>{p.needed}</p>)}
          <p className="muted text-xs">{d.result.note}</p>
        </div>)}</Q>
    </Panel>
  );
}

/* ------------------------------------------------------------------ groundwater (measured) */
interface Wells { wells: Record<string, { dates: string[]; values: number[] }>; validation: { rows_in: number; rows_valid: number; n_wells: number; date_range: string[] | null; rejected_by_reason: Record<string, number>; duplicates_removed: number; warnings: string[]; unit_assumption: string; wells_with_large_jumps: { well_id: string }[] };
  trends: { well_id: string; status: string; n_years: number; direction?: string; p?: number; p_fdr?: number; slope_m_per_yr?: number; ci_low?: number; ci_high?: number; meaning?: string; significant_fdr?: boolean }[]; note: string }

export function GroundwaterPanel() {
  const sc = useScope();
  const q = useApi<Wrapped<Wells>>("/water/groundwater/wells", { region: sc.region, source: sc.source });
  return (
    <Panel title="Groundwater: measured well levels" subtitle="CGWB / India-WRIS readings (depth to water, m below ground). Nothing is inferred from ET or modelled soil moisture.">
      <CsvUpload label="Well readings CSV (date,value[,well_id])" path="/datasets/upload" fields={{ region: sc.region, key: "groundwater", source: sc.source }}
        hint="Rows are validated (dates, 0–300 m depth, duplicates, step changes). Multiple wells are combined as the mean of per-well anomalies." />
      <div className="mt-4"><Q q={q} h={120}>{(d) => {
        const r = d.result, v = r.validation;
        const dates = Array.from(new Set(Object.values(r.wells).flatMap((w) => w.dates))).sort();
        const rows = dates.map((x) => ({ x, ...Object.fromEntries(Object.entries(r.wells).map(([id, w]) => [id, w.values[w.dates.indexOf(x)] ?? null])) }));
        return (
          <div className="space-y-4" data-testid="wells">
            <div className="text-sm"><b>Validation:</b> {v.rows_valid} of {v.rows_in} rows valid · {v.n_wells} well(s) · {v.date_range?.join(" → ")} · {v.duplicates_removed} duplicates removed
              {Object.keys(v.rejected_by_reason).length > 0 && <> · rejected: {Object.entries(v.rejected_by_reason).map(([k, n]) => `${n}× ${k}`).join("; ")}</>}
              {v.warnings.map((w) => <p key={w} className="text-xs" style={{ color: "var(--amber)" }}>⚠ {w}</p>)}<p className="muted text-xs">{v.unit_assumption}</p></div>
            <ChartFrame title="Depth to water by well (larger = deeper)" meta={d.meta as never} filename="groundwater_wells" height={260}>
              <LinesChart rows={rows} lines={Object.keys(r.wells).slice(0, 8).map((id) => ({ key: id, name: id }))} unit="m b.g.l." />
            </ChartFrame>
            <div className="tbl-wrap"><table className="tbl" aria-label="Per-well trends"><thead><tr><th>Well</th><th>Years</th><th>Trend</th><th>p</th><th>p (FDR)</th><th>Sen slope m/yr [95% CI]</th><th>Meaning</th></tr></thead><tbody>
              {r.trends.map((t) => <tr key={t.well_id}><td>{t.well_id}</td><td>{t.n_years}</td>{t.status === "tested" ? <><td>{t.direction}</td><td>{fmtP(t.p!)}</td><td>{fmtP(t.p_fdr!)}</td><td>{fmt(t.slope_m_per_yr, 3)} [{fmt(t.ci_low, 3)}, {fmt(t.ci_high, 3)}]</td><td>{t.meaning}</td></> : <td colSpan={5} className="muted">{t.status}</td>}</tr>)}
            </tbody></table></div>
            <p className="muted text-xs">{r.note}</p>
          </div>);
      }}</Q></div>
      <div className="mt-4"><TrendPanel group="water" variable="groundwater" title="Groundwater depth (aggregate of wells)" /></div>
    </Panel>
  );
}

/* ------------------------------------------------------------------ salinity */
interface SalVal { status: string; message: string; n?: number; spearman_rho?: number; p?: number; ci_low?: number; ci_high?: number; limitations?: string }
export function SalinityPanel() {
  const sc = useScope();
  const q = useApi<Wrapped<SalVal>>("/salinity/validation", { region: sc.region, source: sc.source });
  return (
    <Panel title="Salinity (spectral proxy; unvalidated without field data)" subtitle="No satellite product measures soil salinity directly. SI1 = √(Green×Red) on a Landsat dry-season composite is a literature proxy.">
      <TrendPanel group="salinity" variable="salinity_index" title="Salinity proxy SI1" />
      <div className="mt-4 space-y-3">
        <h3 className="text-sm font-semibold">Validation against measured soil/water EC</h3>
        <CsvUpload label="Field EC CSV (lat,lon,ec in dS/m)" path="/salinity/field-ec" fields={{ region: sc.region, source: sc.source }} hint="At least 10 paired points are needed before any statistic is reported." />
        <Q q={q} h={60}>{(d) => (
          <div className="text-sm" data-testid="salinity-validation">
            <span className={`badge ${d.result.status === "computed" ? "badge-ok" : "badge-warn"}`}>{d.result.status}</span> {d.result.message}
            {d.result.status === "computed" && <p>Spearman ρ = <b>{fmt(d.result.spearman_rho, 2)}</b> (95% CI {fmt(d.result.ci_low, 2)} to {fmt(d.result.ci_high, 2)}, p = {fmtP(d.result.p!)}, n = {d.result.n})</p>}
            {d.result.limitations && <p className="muted text-xs mt-1">{d.result.limitations}</p>}
          </div>)}</Q>
      </div>
    </Panel>
  );
}

/* ------------------------------------------------------------------ Prosopis investigation (exploratory) */
interface Evergreen { pixels_tested: number; significant_increase_fdr: number; significant_decrease_fdr: number; significant_increase_uncorrected: number; significant_decrease_uncorrected: number;
  mean_index: number; years: number[]; status: string; interpretation: string; mask: { pixels_masked: number; threshold_pct: number } | null; bounds: { south: number; north: number; west: number; east: number };
  ground_truth: { available: boolean; message?: string; required?: string; class_counts?: Record<string, number> } }
interface Sep { n_valid: number; classes: Record<string, { n: number; mean: number; enough: boolean }>; pairs: { a: string; b: string; auc: number | null; higher_class?: string; auc_ci_low?: number; auc_ci_high?: number; reason?: string }[]; caveats: string[] }

export function EvergreenPanel() {
  const sc = useScope();
  const { region } = useApp();
  const [mask, setMask] = useState<"none" | "rann_water">("none");
  const [layer, setLayer] = useState<"mean" | "trend">("mean");
  const [basemap, setBasemap] = useState<Basemap>("satellite");
  const p = { region: sc.region, source: sc.source, start: sc.start, end: sc.end, mask };
  const q = useApi<Wrapped<Evergreen>>("/spatial/evergreen", p);
  const val = useApi<Wrapped<Sep>>("/spatial/indicator-validation", { region: sc.region, source: sc.source }, !!q.data?.result.ground_truth.available);
  const overlays = useMemo(() => q.data ? [{ id: "ev", visible: true, opacity: 0.8, bounds: q.data.result.bounds, url: downloadUrl("/spatial/evergreen.png", { ...p, product: layer }) }] : [],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [q.data, layer, mask, sc.region, sc.source, sc.start, sc.end]);
  return (
    <Panel title="Prosopis vs native grassland: exploratory investigation" subtitle="Dry-season persistence = summer NDVI ÷ monsoon NDVI. A hypothesis-generating indicator, NOT a species classification."
      actions={<><Select label="Rann-water mask" value={mask} onChange={setMask} options={[{ value: "none", label: "none" }, { value: "rann_water", label: "mask water ≥10% occurrence" }]} />
        <Select label="Map" value={layer} onChange={setLayer} options={[{ value: "mean", label: "mean index" }, { value: "trend", label: "index trend (FDR)" }]} /></>}>
      <Q q={q}>{(d) => {
        const r = d.result;
        return (
          <div className="space-y-4">
            <p role="note" className="rounded-md p-3 border text-sm" style={{ borderColor: "var(--amber)" }} data-testid="evergreen-status"><b>{r.status}.</b> {r.interpretation}</p>
            <div className="grid gap-4 xl:grid-cols-2">
              <MapView boundary={region?.boundary} overlays={overlays} basemap={basemap} height={360} />
              <div className="text-sm space-y-2">
                <p>Mean index <b>{fmt(r.mean_index, 2)}</b> over {r.years[0]}–{r.years[1]}; {r.pixels_tested.toLocaleString()} pixels tested.</p>
                <p>Index trend after FDR: <b>{r.significant_increase_fdr.toLocaleString()}</b> increasing, <b>{r.significant_decrease_fdr.toLocaleString()}</b> decreasing (uncorrected would be {(r.significant_increase_uncorrected + r.significant_decrease_uncorrected).toLocaleString()}).</p>
                {r.mask && <p className="muted">Rann-water mask: {r.mask.pixels_masked.toLocaleString()} pixels removed at ≥{r.mask.threshold_pct}% occurrence.</p>}
                <Select label="Basemap" value={basemap} onChange={setBasemap} options={[{ value: "satellite", label: "Satellite" }, { value: "streets", label: "Streets" }, { value: "none", label: "None" }]} />
                <p className="muted text-xs">Green = increasing persistence; orange = decreasing; grey = not significant (trend map).</p>
              </div>
            </div>
            <div className="panel !p-3 !bg-[var(--bg-soft)]" data-testid="ground-truth">
              <h3 className="text-sm font-semibold mb-1">Ground truth</h3>
              {r.ground_truth.available ? <p className="text-sm">Labels uploaded: {Object.entries(r.ground_truth.class_counts ?? {}).map(([k, n]) => `${n} ${k}`).join(", ")}.</p> :
                <><p className="text-sm">{r.ground_truth.message}</p><p className="muted text-xs mt-1">Needed: {r.ground_truth.required}</p></>}
              <div className="mt-2"><CsvUpload label="Labelled points CSV (lat,lon,class)" path="/spatial/ground-truth" fields={{ region: sc.region, source: sc.source }} /></div>
              {r.ground_truth.available && val.data && (
                <div className="mt-3 text-sm space-y-1" data-testid="separability">
                  {val.data.result.pairs.map((x) => <p key={x.a + x.b}>{x.a} vs {x.b}: {x.auc == null ? <span className="muted">{x.reason}</span> : <>AUC <b>{fmt(x.auc, 2)}</b> (95% CI {fmt(x.auc_ci_low, 2)}–{fmt(x.auc_ci_high, 2)}; higher in {x.higher_class})</>}</p>)}
                  <ul className="list-disc pl-5 text-xs muted">{val.data.result.caveats.map((c) => <li key={c}>{c}</li>)}</ul></div>)}
            </div>
          </div>);
      }}</Q>
    </Panel>
  );
}

/* ------------------------------------------------------------------ MODIS vs Landsat spatial agreement */
interface Agree { n_pixels: number; spearman_rho: number; sign_agreement_pct: number; n_both_significant: number; significant_sign_agreement_pct: number | null; common_years: number[]; note: string; coarse: string; fine: string; coarse_pixel_size_m: number[]; fine_pixel_size_m: number[] }
export function AgreementPanel() {
  const sc = useScope();
  const q = useApi<Wrapped<Agree>>("/spatial/trend-agreement", { region: sc.region, source: sc.source });
  return (
    <Panel title="MODIS vs Landsat: do trends agree in space?" subtitle="Landsat pixel trends averaged onto the MODIS grid, compared pixel by pixel">
      <Q q={q} h={100}>{(d) => (
        <div className="text-sm space-y-1" data-testid="agreement">
          <p>{d.result.n_pixels.toLocaleString()} pixels, {d.result.common_years[0]}–{d.result.common_years[1]}. Slope rank correlation <b>ρ = {fmt(d.result.spearman_rho, 2)}</b>; sign agreement <b>{fmt(d.result.sign_agreement_pct, 0)}%</b>.</p>
          <p>Where both are FDR-significant ({d.result.n_both_significant.toLocaleString()} pixels): {d.result.significant_sign_agreement_pct == null ? "none" : `${fmt(d.result.significant_sign_agreement_pct, 0)}% agree in sign`}.</p>
          <p className="muted text-xs">{d.result.note}</p>
        </div>)}</Q>
    </Panel>
  );
}

/* ------------------------------------------------------------------ change (difference) map */
interface Diff { mean_change: number; median_change: number; pct_increase: number; pct_decrease: number; p05: number; p95: number; n_pixels: number; unit: string; note: string; bounds: { south: number; north: number; west: number; east: number } }
export function DifferencePanel({ variables }: { variables: { value: string; label: string; season: string }[] }) {
  const sc = useScope();
  const { region } = useApp();
  const [v, setV] = useState(variables[0]?.value ?? "ndvi");
  const [a0, setA0] = useState(String(sc.start)); const [a1, setA1] = useState(String(Math.min(sc.start + 4, sc.end)));
  const [b0, setB0] = useState(String(Math.max(sc.end - 4, sc.start))); const [b1, setB1] = useState(String(sc.end));
  const season = variables.find((x) => x.value === v)?.season ?? "annual";
  const years = Array.from({ length: sc.end - sc.start + 1 }, (_, i) => String(sc.start + i)).map((y) => ({ value: y, label: y }));
  const p = { region: sc.region, source: sc.source, variable: v, season, a_start: a0, a_end: a1, b_start: b0, b_end: b1 };
  const q = useApi<Wrapped<Diff>>("/spatial/difference", p);
  const overlays = useMemo(() => q.data ? [{ id: "diff", visible: true, opacity: 0.85, bounds: q.data.result.bounds, url: downloadUrl("/spatial/difference.png", p) }] : [],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [q.data, v, a0, a1, b0, b1, sc.region, sc.source]);
  return (
    <Panel title="Change map (period B minus period A)" subtitle="Descriptive difference of period means; use pixel trends for significance"
      actions={<><Select label="Variable" value={v} onChange={setV} options={variables.map((x) => ({ value: x.value, label: x.label }))} /></>}>
      <div className="flex flex-wrap gap-3 mb-3"><Select label="A from" value={a0} onChange={setA0} options={years} /><Select label="A to" value={a1} onChange={setA1} options={years} />
        <Select label="B from" value={b0} onChange={setB0} options={years} /><Select label="B to" value={b1} onChange={setB1} options={years} />
        <a className="btn self-end" href={downloadUrl("/spatial/export.png", { ...p, kind: "difference" })} download>⬇ Map PNG</a></div>
      <Q q={q}>{(d) => (
        <div className="grid gap-4 xl:grid-cols-2" data-testid="difference">
          <MapView boundary={region?.boundary} overlays={overlays} basemap="satellite" height={340} />
          <div className="text-sm space-y-1"><p>Mean change <b>{fmt(d.result.mean_change, 4)}</b> {d.result.unit} (median {fmt(d.result.median_change, 4)}; 5–95%: {fmt(d.result.p05, 3)} to {fmt(d.result.p95, 3)}).</p>
            <p>{fmt(d.result.pct_increase, 0)}% of pixels increased, {fmt(d.result.pct_decrease, 0)}% decreased ({d.result.n_pixels.toLocaleString()} pixels). Blue = increase, red = decrease.</p><p className="muted text-xs">{d.result.note}</p></div>
        </div>)}</Q>
    </Panel>
  );
}

/* ------------------------------------------------------------------ pipeline jobs (Settings) */
export function JobsPanel() {
  const qc = useQueryClient();
  const [open, setOpen] = useState<string | null>(null);
  const q = useQuery<{ items: Job[] }, ApiError>({ queryKey: ["jobs-live"], queryFn: () => apiGet<{ items: Job[] }>("/datasets/jobs"),
    refetchInterval: (query) => (query.state.data?.items.some((j) => j.status === "queued" || j.status === "running") ? 2000 : false) });
  const log = useApi<{ log: string }>(`/datasets/jobs/${open}/log`, {}, !!open);
  const [err, setErr] = useState<string | null>(null);
  const act = async (id: string, what: "cancel" | "retry") => { setErr(null); try { await apiSend("POST", `/datasets/jobs/${id}/${what}`); qc.invalidateQueries({ queryKey: ["jobs-live"] }); } catch (e) { setErr((e as ApiError).message); } };
  const tone = (s: string) => (s === "completed" ? "badge-ok" : ["failed", "interrupted", "completed_with_errors"].includes(s) ? "badge-bad" : s === "cancelled" ? "badge-warn" : "");
  return (
    <div>
      {err && <p role="alert" className="text-sm" style={{ color: "var(--red)" }}>{err}</p>}
      <Q q={q} h={60}>{(d) => d.items.length === 0 ? <p className="muted text-sm">No jobs yet.</p> : (
        <div className="space-y-3">{d.items.slice(0, 8).map((j) => (
          <article key={j.id} className="panel !p-3 !bg-[var(--bg-soft)]" data-testid="job">
            <div className="flex flex-wrap items-center gap-2 justify-between">
              <div><span className="font-mono text-xs">{j.id}</span> <span className={`badge ${tone(j.status)}`}>{j.status}</span> <span className="muted text-xs">{new Date(j.created).toLocaleString()}</span></div>
              <div className="flex gap-2">
                {(j.status === "queued" || j.status === "running") && <button className="btn" onClick={() => act(j.id, "cancel")}>Cancel</button>}
                {["failed", "cancelled", "interrupted", "completed_with_errors"].includes(j.status) && <button className="btn" onClick={() => act(j.id, "retry")}>Retry unfinished</button>}
                <button className="btn" onClick={() => setOpen(open === j.id ? null : j.id)}>{open === j.id ? "Hide log" : "Log"}</button>
              </div>
            </div>
            <div className="mt-2" role="progressbar" aria-valuenow={j.progress?.percent ?? 0} aria-valuemin={0} aria-valuemax={100} aria-label={`Job ${j.id} progress`}>
              <div style={{ height: 6, borderRadius: 4, background: "var(--border)" }}><div style={{ width: `${j.progress?.percent ?? 0}%`, height: 6, borderRadius: 4, background: "var(--green)" }} /></div>
              <p className="muted text-xs mt-1">{j.progress?.done ?? 0} / {j.progress?.total ?? 0} tasks</p></div>
            <ul className="text-xs mt-1 space-y-0.5">{j.tasks.map((t) => <li key={t.id}>{t.label}: <b>{t.status}</b>{t.attempts > 1 && ` (attempt ${t.attempts})`}{t.error && <span style={{ color: "var(--red)" }}> – {t.error}</span>}</li>)}</ul>
            {open === j.id && <pre className="text-xs mt-2 p-2 rounded overflow-auto" style={{ background: "var(--bg)", maxHeight: 240 }}>{log.data?.log ?? "loading…"}</pre>}
          </article>))}</div>)}</Q>
    </div>
  );
}

export { BarsChart };
