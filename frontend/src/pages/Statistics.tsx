import { useState } from "react";
import { AdjustedPanel, RegressionPanel } from "../components/analysis";
import { ComparePanel, RegionComparePanel } from "../components/panels2";
import { ResultBlock, PageHeader, Panel, Q, SectionHeader, Select, fmt, fmtP, useApi, useScope } from "../components/ui";
import { ApiError, apiSend, Quality, RepRow, Reproduction, TrendResult, Wrapped } from "../lib/api";

function TrendCalculator() {
  const [text, setText] = useState("");
  const [res, setRes] = useState<Wrapped<TrendResult> | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const run = async () => {
    setErr(null);
    setRes(null);
    const values = text.split(/[\s,;]+/).filter(Boolean).map(Number);
    if (values.some((v) => !Number.isFinite(v))) {
      setErr("Enter numbers separated by commas, spaces or new lines.");
      return;
    }
    if (values.length < 4) {
      setErr("At least 4 values are required.");
      return;
    }
    try {
      setRes(await apiSend<Wrapped<TrendResult>>("POST", "/statistics/trend", { values }));
    } catch (e) {
      setErr((e as ApiError).message);
    }
  };

  return (
    <Panel
      title="In-Browser Trend Test Calculator"
      subtitle="Evaluates custom numerical sequences with Mann-Kendall, Hamed-Rao variance correction, Sen's slope, and lag-1 autocorrelation check."
    >
      <div className="space-y-3">
        <textarea
          className="field w-full h-24 font-mono text-xs"
          placeholder="e.g. 0.21, 0.23, 0.22, 0.27, 0.29, 0.28, 0.33"
          value={text}
          onChange={(e) => setText(e.target.value)}
          aria-label="Series values"
        />
        <div className="flex items-center gap-3">
          <button className="btn btn-primary text-xs" onClick={run}>
            Run tests
          </button>
          {err && (
            <span role="alert" style={{ color: "var(--red)" }} className="text-xs font-medium">
              {err}
            </span>
          )}
        </div>
      </div>

      {res && (
        <div className="grid gap-4 xl:grid-cols-2 mt-4 pt-3 border-t border-[var(--border)]">
          <ResultBlock
            t={res.result.mk}
            meta={{ ...res.meta, region: "-", kind: "user", synthetic: false, aggregation: "user series" }}
            unit="per step"
            label="Your series"
          />
          <ResultBlock
            t={res.result.hr}
            meta={{ ...res.meta, region: "-", kind: "user", synthetic: false, aggregation: "user series" }}
            unit="per step"
            label="Your series"
          />
          <p className="muted text-xs xl:col-span-2">
            Lag-1 autocorrelation: <b className="font-mono">{fmt(res.result.lag1_autocorr, 2)}</b> → Recommended test:{" "}
            <span className="badge badge-ok">{res.result.recommended === "hr" ? "Hamed-Rao" : "Mann-Kendall"}</span>
          </p>
        </div>
      )}
    </Panel>
  );
}

const STATUS_CLASS: Record<string, string> = {
  reproduced: "badge-ok",
  consistent: "badge-warn",
  "not reproduced": "badge-bad",
  "not available": "",
};

function cell(c: RepRow["computed"]) {
  if (c === null) return "–";
  if (typeof c === "number") return fmt(c, 5);
  return `${c.direction}; p=${fmtP(c.p)}; slope ${fmt(c.slope, 4)}; Z=${fmt(c.z, 2)}`;
}

function reportedCell(r: RepRow["reported"]) {
  if (r.value !== undefined) return fmt(r.value, 5);
  return `${r.direction}; p=${r.p}${r.slope != null ? `; slope ${r.slope}` : ""}${r.z != null ? `; Z=${r.z}` : ""}`;
}

function ReproductionPanel() {
  const sc = useScope();
  const q = useApi<Wrapped<Reproduction>>("/statistics/handover-reproduction", { region: sc.region, source: sc.source });

  return (
    <Panel
      title="Reproduction of the Research Handover"
      subtitle="The handover's exact analytical protocol (Hamed-Rao + Sen slope, OLS NDVI ~ monsoon rainfall, residual trend) re-executed on verified pipeline data. Platform results are never modified to artificially match reference numbers."
    >
      <Q q={q}>
        {(d) => {
          const r = d.result;
          return (
            <div className="space-y-4" data-testid="reproduction">
              <div className="flex flex-wrap items-center gap-2 text-xs">
                {Object.entries(r.counts).map(([k, v]) => (
                  <span key={k} className={`badge ${STATUS_CLASS[k]}`}>
                    {v} {k}
                  </span>
                ))}
                <span className={`badge ${r.engine_cross_check.agree ? "badge-ok" : "badge-bad"}`}>
                  platform engine {r.engine_cross_check.agree ? "agrees" : "DISAGREES"} with pymannkendall
                </span>
              </div>

              <div className="tbl-wrap">
                <table className="tbl" aria-label="Handover comparison">
                  <thead>
                    <tr>
                      <th>Quantity</th>
                      <th>Handover Reference (page)</th>
                      <th>Computed By Platform</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {r.rows.map((row) => (
                      <tr key={row.id}>
                        <td>
                          <div className="font-medium text-[var(--text)]">{row.label}</div>
                          {row.note && <div className="muted text-[11px]">{row.note}</div>}
                        </td>
                        <td className="font-mono text-xs">
                          {reportedCell(row.reported)} <span className="muted font-sans">(p.{row.page})</span>
                        </td>
                        <td className="font-mono text-xs">{cell(row.computed)}</td>
                        <td>
                          <span className={`badge ${STATUS_CLASS[row.status]}`}>{row.status}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="p-3.5 rounded-lg bg-[var(--bg-soft)] border border-[var(--border)] text-xs sm:text-sm text-[var(--text-2)]">
                Regression R² of NDVI ~ Rainfall: <b className="font-mono text-[var(--text)]">{fmt(r.colab.regression.r2, 3)}</b> (rain coefficient p={fmtP(r.colab.regression.rain_p)}). Handover rule verdict:{" "}
                <b className="font-mono text-[var(--teal)]">{r.colab.verdict_rule}</b>. <span className="muted">{r.colab.verdict_note}</span>
              </div>

              <ul className="list-disc pl-5 text-xs text-[var(--muted)] space-y-1">
                {r.notes.map((n) => (
                  <li key={n}>{n}</li>
                ))}
              </ul>

              <details className="text-xs bg-[var(--bg-soft)] rounded-lg p-3 border border-[var(--border)]">
                <summary className="cursor-pointer font-semibold text-[var(--text)] select-none">
                  Documented Protocol Differences ({r.protocol_differences.length})
                </summary>
                <div className="tbl-wrap mt-2.5">
                  <table className="tbl">
                    <thead>
                      <tr>
                        <th>Protocol Item</th>
                        <th>Handover Notebook</th>
                        <th>Platform Default</th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {r.protocol_differences.map((x) => (
                        <tr key={x.item}>
                          <td className="font-medium">{x.item}</td>
                          <td className="muted">{x.handover}</td>
                          <td>{x.platform_default}</td>
                          <td>
                            <span className="badge badge-ok">{x.status}</span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </details>

              <div className="flex justify-between items-center text-[11px] text-[var(--muted)] font-mono pt-1">
                <span>Reference Source: {r.reference_source}</span>
                <span>Geometry: {r.reference_geometry}</span>
              </div>
            </div>
          );
        }}
      </Q>
    </Panel>
  );
}

function QualityPanel() {
  const sc = useScope();
  const [v, setV] = useState("ndvi");
  const q = useApi<Wrapped<Quality>>("/datasets/quality", { region: sc.region, source: sc.source, variable: v });

  return (
    <Panel
      title="Data Quality & Completeness Audit"
      subtitle="Automatic audit verifying valid observation frequency, sensor gap detection, and statistical bounds checks."
      actions={
        <Select
          label="Target Series"
          value={v}
          onChange={setV}
          options={[
            { value: "ndvi", label: "NDVI (MOD13Q1)" },
            { value: "ndvi_qa", label: "NDVI (QA-filtered)" },
            { value: "precip", label: "Precipitation (IMERG)" },
            { value: "et", label: "ET (MOD16A2)" },
            { value: "sm_root", label: "Root-Zone Soil Moisture" },
            { value: "sm_surface", label: "Surface Soil Moisture" },
          ]}
        />
      }
    >
      <Q q={q}>
        {(d) => {
          const r = d.result;
          return (
            <div className="space-y-3 text-xs sm:text-sm" data-testid="quality">
              <div className="grid gap-3 sm:grid-cols-3">
                <div className="p-3 rounded-lg bg-[var(--bg-soft)] border border-[var(--border)]">
                  <div className="muted text-[11px]">Valid months</div>
                  <div className="font-mono text-lg font-bold text-[var(--text)] mt-0.5">
                    {r.valid_months} / {r.expected_months}
                  </div>
                  <div className="text-[11px] text-[var(--green)] font-medium mt-0.5">
                    {r.completeness_pct}% complete
                  </div>
                </div>

                <div className="p-3 rounded-lg bg-[var(--bg-soft)] border border-[var(--border)]">
                  <div className="muted text-[11px]">Missing Observations</div>
                  <div className="font-mono text-lg font-bold text-[var(--text)] mt-0.5">{r.missing_months}</div>
                  <div className="text-[11px] muted mt-0.5">
                    {r.missing_list.length > 0 ? r.missing_list.slice(0, 4).join(", ") : "None missing"}
                  </div>
                </div>

                <div className="p-3 rounded-lg bg-[var(--bg-soft)] border border-[var(--border)]">
                  <div className="muted text-[11px]">Observed Range</div>
                  <div className="font-mono text-lg font-bold text-[var(--text)] mt-0.5">
                    {fmt(r.stats.min, 2)} – {fmt(r.stats.max, 2)}
                  </div>
                  <div className="text-[11px] muted mt-0.5">
                    Plausible: [{r.plausible_range.join(", ")}] {r.unit}
                  </div>
                </div>
              </div>

              {r.flags.length === 0 ? (
                <div className="flex items-center gap-2 text-xs text-[var(--green)] font-medium">
                  <span className="badge badge-ok">✓ No plausibility flags</span>
                  <span>All values within expected biophysical constraints.</span>
                </div>
              ) : (
                r.flags.map((f) => (
                  <p key={f} role="alert" className="text-xs font-semibold p-2.5 rounded bg-[var(--bg-soft)] text-[var(--amber)] border border-[var(--amber)]">
                    ⚠ {f}
                  </p>
                ))
              )}

              <div className="text-[11px] text-[var(--muted)] font-mono pt-1 flex flex-wrap gap-x-4 gap-y-1">
                <span>Geometry: {r.geometry ? `${r.geometry.id} (${Math.round(r.geometry.area_km2).toLocaleString()} km²)` : "Not recorded"}</span>
                <span>Retrieved: {r.retrieval_date ?? "n/a"}</span>
                <span>Collection: {r.ee_id ?? "User upload"}</span>
              </div>
            </div>
          );
        }}
      </Q>
    </Panel>
  );
}

export default function Statistics() {
  const [resp, setResp] = useState("ndvi");
  const [season, setSeason] = useState("monsoon");
  const [rainSeason, setRainSeason] = useState("monsoon");
  const [y, setY] = useState("ndvi");
  const [x, setX] = useState("precip");

  const vars = [
    ["ndvi", "NDVI"],
    ["precip", "Precipitation"],
    ["lst_day", "LST day"],
    ["lst_night", "LST night"],
    ["et", "ET"],
    ["sm_root", "Root-zone soil moisture"],
    ["sm_surface", "Surface soil moisture"],
    ["water_extent", "Water extent"],
  ];
  const opts = vars.map(([value, label]) => ({ value, label }));
  const seasons = ["annual", "monsoon", "summer", "postmonsoon", "winter"].map((v) => ({ value: v, label: v }));

  return (
    <>
      <PageHeader
        title="Statistical Analysis"
        subtitle="The reproducible analytical framework underpinning all platform conclusions. All tests are two-sided at α=0.05 unless explicitly stated. Correlation and regression describe empirical association and predictive accuracy, never causal attribution."
        badges={
          <div className="flex items-center gap-2">
            <span className="badge font-mono text-[11px] text-[var(--teal)] border-[var(--border-hi)]">
              Two-sided α=0.05
            </span>
            <span className="badge font-mono text-[11px]">HAC / Newey-West</span>
          </div>
        }
      />

      <SectionHeader
        title="Multi-Variable Comparative Matrix"
        description="Pairwise Pearson and Spearman correlation matrices with Benjamini-Hochberg FDR adjustments, cross-validated predictions, and anomaly tracking."
      />
      <ComparePanel />

      <SectionHeader
        title="Spatial Geometry Sensitivity"
        description="Assessing how trend significance varies between the handover rectangular window and custom grassland boundaries."
      />
      <RegionComparePanel />

      <SectionHeader
        title="Benchmark Reproduction & Quality Controls"
        description="Direct line-by-line comparison against reference research documents and automated data validation audits."
      />
      <ReproductionPanel />
      <QualityPanel />

      <SectionHeader
        title="Rainfall-Adjusted Trend Engine"
        description="Ordinary Least Squares model regressing response indicator against seasonal rainfall totals, followed by residual trend analysis."
      />
      <Panel
        title="Rainfall-Adjusted Configuration"
        subtitle="Specify response variable and seasonal aggregation periods."
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Select
              label="Response"
              value={resp}
              onChange={setResp}
              options={opts.filter((o) => o.value !== "precip")}
            />
            <Select label="Response Season" value={season} onChange={setSeason} options={seasons} />
            <Select label="Rainfall Season" value={rainSeason} onChange={setRainSeason} options={seasons} />
          </div>
        }
      >
        <p className="text-xs text-[var(--muted)] leading-relaxed">
          The pipeline tests response residuals against five pre-specified sensitivity models (S1–S5: lagged rainfall, Theil-Sen line, Newey-West HAC standard errors, Cook's distance outlier filtering, and 3-month cumulative deseasonalized anomalies).
        </p>
      </Panel>

      <AdjustedPanel
        key={`${resp}${season}${rainSeason}`}
        response={resp}
        season={season}
        rainSeason={rainSeason}
        title={`${resp.toUpperCase()} (${season}) ~ ${rainSeason} Rainfall`}
      />

      <SectionHeader
        title="Bivariate Regression Studio"
        description="Explore custom predictor-response relationships with HAC standard errors and residual diagnostics."
      />
      <Panel
        title="Bivariate Model Builder"
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Select label="Response (y)" value={y} onChange={setY} options={opts} />
            <Select label="Predictor (x)" value={x} onChange={setX} options={opts} />
          </div>
        }
      >
        <p className="text-xs text-[var(--muted)]">
          Monsoon seasonal aggregates: cumulative sum for precipitation and ET, arithmetic mean for all other biophysical indices.
        </p>
      </Panel>

      {y === x ? (
        <div role="alert" className="p-3 rounded-lg bg-[var(--bg-soft)] text-xs text-[var(--amber)] border border-[var(--amber)]">
          Predictor and response must be different variables.
        </div>
      ) : (
        <RegressionPanel key={`${y}${x}`} y={y} x={x} agg="monsoon" title={`${y.toUpperCase()} ~ ${x.toUpperCase()}`} />
      )}

      <SectionHeader
        title="Standalone Trend Calculator"
        description="Verify any arbitrary numeric series directly against the platform's statistical engine."
      />
      <TrendCalculator />
    </>
  );
}
