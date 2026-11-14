import { useState } from "react";
import { Adjusted, Coef, OLS, SeriesResult, TrendResult, Wrapped } from "../lib/api";
import { BarsChart, ChartFrame, LinesChart, PatternChart, ScatterPlot } from "./charts";
import { Field, Panel, Q, ResultBlock, Select, fmt, fmtP, useApi, useScope } from "./ui";

type Agg = "monthly" | "annual" | "summer" | "monsoon" | "postmonsoon" | "winter" | "peak";
const AGG_OPTS: { value: Agg; label: string }[] = [
  { value: "monthly", label: "Monthly" }, { value: "annual", label: "Annual" }, { value: "monsoon", label: "Monsoon (JJAS)" },
  { value: "summer", label: "Summer (MAM)" }, { value: "postmonsoon", label: "Post-monsoon (ON)" }, { value: "winter", label: "Winter (DJF)" },
];
const TREND_OPTS = AGG_OPTS.filter((o) => o.value !== "monthly");

export function SeriesPanel({ group, variable, title, defaultAgg = "monthly" }: { group: string; variable: string; title: string; defaultAgg?: Agg }) {
  const sc = useScope();
  const [agg, setAgg] = useState<Agg>(defaultAgg);
  const q = useApi<Wrapped<SeriesResult>>(`/${group}/timeseries`, { ...sc, variable, agg });
  return (
    <Panel title={title} subtitle={q.data ? `${q.data.result.label} · ${q.data.result.unit}` : undefined}
      actions={<Select label="Aggregation" value={agg} onChange={setAgg} options={AGG_OPTS} />}>
      <Q q={q}>{(d) => (
        <ChartFrame title={`${title} (${agg})`} meta={d.meta} filename={`${variable}_${agg}_${sc.region}`} subtitle={d.meta.dataset?.ee_id ? `Source: ${d.meta.dataset.ee_id}` : d.meta.dataset?.provider ?? undefined}>
          <LinesChart rows={d.result.x.map((x, i) => ({ x, v: d.result.values[i] }))} lines={[{ key: "v", name: d.result.label, dots: d.result.frequency === "annual" }]} unit={d.result.unit} />
        </ChartFrame>
      )}</Q>
    </Panel>
  );
}

export function TrendPanel({ group, variable, title, defaultAgg = "annual" }: { group: string; variable: string; title: string; defaultAgg?: Agg }) {
  const sc = useScope();
  const [agg, setAgg] = useState<Agg>(defaultAgg);
  const [which, setWhich] = useState<"mk" | "hr" | "rec">("rec");
  const q = useApi<Wrapped<TrendResult>>(`/${group}/trend`, { ...sc, variable, agg });
  return (
    <Panel title={`${title}: trend analysis`} actions={<>
      <Select label="Season" value={agg} onChange={setAgg} options={TREND_OPTS} />
      <Select label="Test" value={which} onChange={setWhich} options={[{ value: "rec", label: "Recommended" }, { value: "mk", label: "Mann-Kendall" }, { value: "hr", label: "Hamed-Rao" }]} />
    </>}>
      <Q q={q}>{(d) => {
        const r = d.result;
        const t = which === "rec" ? r[r.recommended] : r[which];
        return (
          <div className="grid gap-4 xl:grid-cols-2">
            <ChartFrame title={`${title} (${agg})`} meta={d.meta} filename={`${variable}_${agg}_trend`} height={260}>
              <LinesChart rows={r.years.map((y, i) => ({ x: y, v: r.values[i], line: r.line[i] }))}
                lines={[{ key: "v", name: "Observed", dots: true }, { key: "line", name: "Sen slope line", dashed: true, color: "var(--c3)" }]} unit={r.unit} />
            </ChartFrame>
            <div>
              <ResultBlock t={t} meta={d.meta} unit={r.unit_short} interpretation={r.interpretation} limitations={r.limitations} label={title} />
              <p className="muted text-xs mt-2">Lag-1 autocorrelation: {fmt(r.lag1_autocorr, 2)} · MK p {fmtP(r.mk.p).startsWith("<") ? fmtP(r.mk.p) : "= " + fmtP(r.mk.p)} · Hamed-Rao p {fmtP(r.hr.p).startsWith("<") ? fmtP(r.hr.p) : "= " + fmtP(r.hr.p)} (variance factor {fmt(r.hr.variance_correction, 2)}).</p>
              {(r.warnings ?? []).map((w) => <p key={w} role="note" className="text-xs mt-1" style={{ color: "var(--amber)" }} data-testid="trend-warning">⚠ {w}</p>)}
            </div>
          </div>
        );
      }}</Q>
    </Panel>
  );
}

interface Anom { x: (string | number)[]; anomaly: number[]; z: number[]; flag: boolean[]; unit: string; note: string }
export function AnomalyPanel({ group, variable, title, defaultAgg = "annual" }: { group: string; variable: string; title: string; defaultAgg?: Agg }) {
  const sc = useScope();
  const [agg, setAgg] = useState<Agg>(defaultAgg);
  const q = useApi<Wrapped<Anom>>(`/${group}/anomalies`, { ...sc, variable, agg });
  return (
    <Panel title={`${title}: anomalies`} actions={<Select label="Aggregation" value={agg} onChange={setAgg} options={AGG_OPTS} />}>
      <Q q={q}>{(d) => {
        const flagged = d.result.x.filter((_, i) => d.result.flag[i]);
        return (
          <>
            <ChartFrame title={`Anomaly (${agg})`} meta={d.meta} filename={`${variable}_${agg}_anomaly`} height={240}
              subtitle={`Amber bars: |z| > 2 (${flagged.length} flagged). ${d.result.note}`}>
              <BarsChart rows={d.result.x.map((x, i) => ({ x, v: d.result.anomaly[i], flag: d.result.flag[i] }))} unit={d.result.unit} flagKey />
            </ChartFrame>
            {flagged.length > 0 && <p className="text-xs muted mt-2">Flagged periods: {flagged.slice(0, 20).join(", ")}{flagged.length > 20 ? "…" : ""}. A flag marks a statistical outlier, not an explanation.</p>}
          </>
        );
      }}</Q>
    </Panel>
  );
}

interface Pat { month: number[]; mean: (number | null)[]; sd: (number | null)[]; unit: string }
export function PatternPanel({ group, variable, title }: { group: string; variable: string; title: string }) {
  const sc = useScope();
  const q = useApi<Wrapped<Pat>>(`/${group}/monthly-pattern`, { ...sc, variable });
  return (
    <Panel title={`${title}: monthly pattern`}>
      <Q q={q}>{(d) => (
        <ChartFrame title="Mean by calendar month (± 1 SD across years)" meta={d.meta} filename={`${variable}_monthly_pattern`} height={240}>
          <PatternChart {...d.result} />
        </ChartFrame>
      )}</Q>
    </Panel>
  );
}

interface Seasonal { seasons: Record<string, { years: number[]; values: number[]; mean: number; trend?: { direction: string; p: number; slope: number; test: string } }>; unit: string }
export function SeasonalPanel({ group, variable, title, seasons = ["summer", "monsoon"] }: { group: string; variable: string; title: string; seasons?: string[] }) {
  const sc = useScope();
  const q = useApi<Wrapped<Seasonal>>(`/${group}/seasonal-comparison`, { ...sc, variable });
  return (
    <Panel title={`${title}: seasonal comparison`}>
      <Q q={q}>{(d) => {
        const keys = seasons.filter((s) => d.result.seasons[s]);
        const years = Array.from(new Set(keys.flatMap((k) => d.result.seasons[k].years))).sort();
        const rows = years.map((y) => Object.fromEntries([["x", y], ...keys.map((k) => [k, d.result.seasons[k].values[d.result.seasons[k].years.indexOf(y)] ?? null])]));
        return (
          <div className="grid gap-4 xl:grid-cols-2">
            <ChartFrame title="Seasonal means by year" meta={d.meta} filename={`${variable}_seasonal`} height={240}>
              <LinesChart rows={rows} lines={keys.map((k) => ({ key: k, name: k, dots: true }))} unit={d.result.unit} />
            </ChartFrame>
            <div className="tbl-wrap">
              <table className="tbl"><thead><tr><th>Season</th><th>Mean</th><th>Trend</th><th>p</th><th>Sen slope/yr</th></tr></thead>
                <tbody>{Object.entries(d.result.seasons).map(([k, s]) => (
                  <tr key={k}><td>{k}</td><td>{fmt(s.mean, 3)}</td><td>{s.trend?.direction ?? "–"}</td><td>{s.trend ? fmtP(s.trend.p) : "–"}</td><td>{s.trend ? fmt(s.trend.slope, 4) : "–"}</td></tr>
                ))}</tbody></table>
              <p className="muted text-xs mt-2">Trend per season uses the recommended test (Mann-Kendall, or Hamed-Rao when autocorrelation is evident). {d.result.unit}.</p>
            </div>
          </div>
        );
      }}</Q>
    </Panel>
  );
}

export function CoefTable({ coefs, r2, n }: { coefs: Coef[]; r2: number; n: number }) {
  return (
    <div className="tbl-wrap">
      <table className="tbl" aria-label="Regression coefficients">
        <thead><tr><th>Term</th><th>Coefficient</th><th>95% CI</th><th>p</th><th>p (HAC)</th></tr></thead>
        <tbody>{coefs.map((c) => (
          <tr key={c.name}><td>{c.name}</td><td>{fmt(c.coef, 5)}</td><td>[{fmt(c.ci_low, 4)}, {fmt(c.ci_high, 4)}]</td><td>{fmtP(c.p)}</td><td>{fmtP(c.hac_p)}</td></tr>
        ))}</tbody>
      </table>
      <p className="muted text-xs mt-1">R² = {fmt(r2, 3)} · n = {n}. HAC = Newey-West errors (robust to autocorrelation).</p>
    </div>
  );
}

export function Diagnostics({ d }: { d: OLS["diagnostics"] }) {
  const row = (name: string, v: number | null | undefined, ok: (v: number) => boolean, help: string) => (
    <tr key={name}><td>{name}</td><td>{v == null ? "–" : fmt(v, 3)}</td>
      <td>{v == null ? "" : ok(v) ? <span className="badge badge-ok">OK</span> : <span className="badge badge-warn">check</span>}</td><td className="muted">{help}</td></tr>
  );
  return (
    <div className="tbl-wrap"><table className="tbl" aria-label="Residual diagnostics"><thead><tr><th>Diagnostic</th><th>Value</th><th></th><th>Meaning</th></tr></thead><tbody>
      {row("Durbin-Watson", d.durbin_watson, (v) => v > 1.5 && v < 2.5, "≈2 means no first-order autocorrelation")}
      {row("Ljung-Box p", d.ljung_box_p, (v) => v >= 0.05, "p<0.05: residuals are serially correlated")}
      {row("Shapiro-Wilk p", d.shapiro_p, (v) => v >= 0.05, "p<0.05: residuals non-normal")}
      {row("Breusch-Pagan p", d.breusch_pagan_p, (v) => v >= 0.05, "p<0.05: unequal variance")}
      <tr><td>Influential points</td><td>{d.outlier_indices.length}</td><td></td><td className="muted">Cook's D &gt; 4/n</td></tr>
    </tbody></table></div>
  );
}

export function AdjustedPanel({ response = "ndvi", season = "monsoon", rainSeason = "monsoon", title }: { response?: string; season?: string; rainSeason?: string; title?: string }) {
  const sc = useScope();
  const q = useApi<Wrapped<Adjusted>>("/statistics/rainfall-adjusted", { ...sc, response, season, rain_season: rainSeason });
  return (
    <Panel title={title ?? "Rainfall-adjusted analysis"} subtitle={`${response.toUpperCase()} (${season}) ~ ${rainSeason} rainfall; do residuals still trend?`}>
      <Q q={q}>{(d) => {
        const r = d.result; const rt = r.residual_trend; const pick = rt[rt.recommended];
        const slope = r.regression.coefficients.find((c) => c.name === "rainfall");
        const a = Math.min(...r.rainfall), b = Math.max(...r.rainfall);
        const ic = r.regression.coefficients[0].coef, sl = slope?.coef ?? 0;
        return (
          <div className="space-y-4">
            <p className="text-sm" data-testid="adjusted-verdict"><b>Result.</b> {r.verdict.text}</p>
            <div className="grid gap-4 xl:grid-cols-2">
              <ChartFrame title="Response vs rainfall" meta={d.meta} filename={`${response}_vs_rain`} height={240} subtitle="Each point is one year; line = OLS fit.">
                <ScatterPlot pts={r.rainfall.map((x, i) => ({ x, y: r.ndvi[i] }))} xName={`Rainfall (${r.rain_unit})`} yName={r.response_label} line={[{ x: a, y: ic + sl * a }, { x: b, y: ic + sl * b }]} />
              </ChartFrame>
              <ChartFrame title="Residual time series" meta={d.meta} filename={`${response}_residuals`} height={240} subtitle="Observed minus rainfall-predicted. Positive = greener than rainfall alone predicts.">
                <BarsChart rows={r.years.map((y, i) => ({ x: y, v: r.residuals[i] }))} unit={r.unit} />
              </ChartFrame>
            </div>
            <div className="grid gap-4 xl:grid-cols-2">
              <div><h3 className="text-sm font-semibold mb-1">Regression</h3><CoefTable coefs={r.regression.coefficients} r2={r.regression.r2} n={r.n} /></div>
              <div><h3 className="text-sm font-semibold mb-1">Residual trend</h3>
                <ResultBlock t={pick} meta={d.meta} unit={r.unit} label="Residuals" />
              </div>
            </div>
            <div><h3 className="text-sm font-semibold mb-1">Sensitivity analyses</h3>
              <div className="tbl-wrap"><table className="tbl"><thead><tr><th>Analysis</th><th>n</th><th>Direction</th></tr></thead><tbody>
                {r.sensitivity.map((s) => <tr key={s.name}><td>{s.name}</td><td>{s.n}</td><td>{s.direction}</td></tr>)}
              </tbody></table></div></div>
            <div className="grid gap-4 xl:grid-cols-2">
              <div><h3 className="text-sm font-semibold mb-1">Residual diagnostics</h3><Diagnostics d={r.regression.diagnostics} /></div>
              <div><h3 className="text-sm font-semibold mb-1">Caveats</h3><ul className="list-disc pl-5 text-sm space-y-1">{r.caveats.map((c, i) => <li key={i}>{c}</li>)}</ul></div>
            </div>
          </div>
        );
      }}</Q>
    </Panel>
  );
}

export function RegressionPanel({ y, x, agg = "monsoon", title }: { y: string; x: string; agg?: string; title: string }) {
  const sc = useScope();
  const q = useApi<Wrapped<OLS & { years: number[]; observed: number[]; x: string[]; interpretation: string }>>("/statistics/regression", { ...sc, y, x, agg });
  const c = useApi<Wrapped<{ pearson_r: number; pearson_p: number; pearson_ci_low: number; pearson_ci_high: number; spearman_rho: number; n: number; note: string }>>(
    "/statistics/correlation", { ...sc, a: y, b: x.split(",")[0], agg });
  return (
    <Panel title={title} subtitle={`${y} ~ ${x} (${agg} aggregates)`}>
      <Q q={q}>{(d) => (
        <div className="grid gap-4 xl:grid-cols-2">
          <div className="space-y-3">
            <CoefTable coefs={d.result.coefficients} r2={d.result.r2} n={d.result.n} />
            {c.data && <p className="text-sm">Pearson r = <b>{fmt(c.data.result.pearson_r, 2)}</b> (95% CI {fmt(c.data.result.pearson_ci_low, 2)} to {fmt(c.data.result.pearson_ci_high, 2)}, p={fmtP(c.data.result.pearson_p)}); Spearman ρ = {fmt(c.data.result.spearman_rho, 2)}.</p>}
            <p className="muted text-xs">{d.result.interpretation}</p>
          </div>
          <ChartFrame title="Residuals over time" meta={d.meta} filename={`${y}_${x}_residuals`} height={220}>
            <BarsChart rows={d.result.years.map((yy, i) => ({ x: yy, v: d.result.residuals[i] }))} />
          </ChartFrame>
        </div>
      )}</Q>
    </Panel>
  );
}

export { Field };
