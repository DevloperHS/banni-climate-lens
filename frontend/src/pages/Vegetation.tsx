import { AnomalyPanel, AdjustedPanel, PatternPanel, SeasonalPanel, SeriesPanel, TrendPanel } from "../components/analysis";
import { ChartFrame, LinesChart } from "../components/charts";
import { PageHeader, Panel, Q, RequireData, SectionHeader, fmt, fmtP, useApi, useScope } from "../components/ui";
import { Wrapped } from "../lib/api";
import { AgreementPanel, EvergreenPanel } from "../components/panels2";

interface Landsat {
  years: number[];
  modis: number[];
  landsat: number[];
  note: string;
  correlation: { pearson_r: number; pearson_p: number; n: number; spearman_rho: number };
  trend_modis: { mk: { direction: string; p: number; slope: number } };
  trend_landsat: { mk: { direction: string; p: number; slope: number } };
  species_discrimination: { status: string; reason: string };
}

function LandsatPanel() {
  const sc = useScope();
  const q = useApi<Wrapped<Landsat>>("/vegetation/landsat-comparison", sc);
  return (
    <Panel
      title="MODIS vs Landsat Resolution Cross-Check"
      subtitle="Evaluates whether 250 m MODIS greening patterns are corroborated at 30 m spatial resolution (Sep–Oct composites)."
    >
      <Q q={q}>
        {(d) => (
          <div className="grid gap-5 xl:grid-cols-2">
            <ChartFrame
              title="Peak-Season NDVI (MODIS vs Landsat)"
              meta={d.meta}
              filename="modis_vs_landsat"
              height={250}
            >
              <LinesChart
                rows={d.result.years.map((y, i) => ({
                  x: y,
                  modis: d.result.modis[i],
                  landsat: d.result.landsat[i],
                }))}
                lines={[
                  { key: "modis", name: "MODIS (250 m)", dots: true, color: "var(--teal)" },
                  { key: "landsat", name: "Landsat (30 m)", dots: true, color: "var(--green)" },
                ]}
              />
            </ChartFrame>
            <div className="text-xs sm:text-sm space-y-3">
              <div className="p-3 rounded-lg bg-[var(--bg-soft)] border border-[var(--border)] space-y-1.5">
                <div className="font-semibold text-[var(--text)]">Cross-Sensor Correlation</div>
                <p className="text-[var(--text-2)]">
                  Over {d.result.correlation.n} coincident observation years: Pearson r ={" "}
                  <b className="font-mono text-[var(--text)]">{fmt(d.result.correlation.pearson_r, 2)}</b> (p=
                  {fmtP(d.result.correlation.pearson_p)}), Spearman ρ ={" "}
                  <b className="font-mono text-[var(--text)]">{fmt(d.result.correlation.spearman_rho, 2)}</b>.
                </p>
                <div className="text-xs pt-1 border-t border-[var(--border)] text-[var(--muted)]">
                  <span>MODIS Trend: </span>
                  <b className="text-[var(--text)]">{d.result.trend_modis.mk.direction}</b> (p=
                  {fmtP(d.result.trend_modis.mk.p)}). <span>Landsat Trend: </span>
                  <b className="text-[var(--text)]">{d.result.trend_landsat.mk.direction}</b> (p=
                  {fmtP(d.result.trend_landsat.mk.p)}).
                </div>
              </div>
              <p className="muted text-xs leading-relaxed">{d.result.note}</p>
              <div
                role="note"
                className="rounded-lg p-3 border text-xs"
                style={{
                  borderColor: "var(--amber)",
                  background: "color-mix(in srgb, var(--amber) 8%, transparent)",
                  color: "var(--text-2)",
                }}
              >
                <b className="text-[var(--amber)]">
                  Species Identification Limit: {d.result.species_discrimination.status}.
                </b>{" "}
                {d.result.species_discrimination.reason}
              </div>
            </div>
          </div>
        )}
      </Q>
    </Panel>
  );
}

export default function Vegetation() {
  return (
    <>
      <PageHeader
        title="Vegetation"
        subtitle="MODIS MOD13Q1 NDVI measures aggregate canopy greenness across the Banni basin. A statistically significant upward trend in greenness does not alone substantiate native-grassland regeneration versus woody invasive proliferation."
        badges={
          <div className="flex items-center gap-2">
            <span className="badge font-mono text-[11px] text-[var(--green)] border-[var(--border-hi)]">
              MODIS MOD13Q1 · 250m
            </span>
            <span className="badge font-mono text-[11px]">NDVI [-0.2 – 1.0]</span>
          </div>
        }
      />

      <RequireData keys={["ndvi"]} what="MODIS NDVI">
        <SectionHeader
          title="Temporal Trajectory & Trend Statistics"
          description="Multi-decadal monthly and aggregated time-series with Mann-Kendall and Hamed-Rao trend tests."
        />
        <SeriesPanel group="vegetation" variable="ndvi" title="NDVI time series" />
        <TrendPanel group="vegetation" variable="ndvi" title="NDVI" />

        <SectionHeader
          title="Distributional Patterns & Anomalies"
          description="Mean annual phenological cycles and standard deviation envelope alongside outlier tracking (|z| > 2)."
        />
        <div className="grid gap-5 xl:grid-cols-2">
          <PatternPanel group="vegetation" variable="ndvi" title="NDVI" />
          <AnomalyPanel group="vegetation" variable="ndvi" title="NDVI" />
        </div>
        <SeasonalPanel group="vegetation" variable="ndvi" title="NDVI" />

        <SectionHeader
          title="Precipitation Influence & Residual Analysis"
          description="Separating climate-driven greening from underlying ecological changes via OLS regression against monsoon rainfall."
        />
        <AdjustedPanel response="ndvi" season="monsoon" title="Rainfall-adjusted NDVI (monsoon)" />

        <SectionHeader
          title="Seasonal Persistence: The Dry Season"
          description="Deep-rooted woody taxa (such as Prosopis juliflora) sustain canopy foliage into the hot dry season (MAM), whereas annual and perennial grasses desiccate."
        />
        <AdjustedPanel
          response="ndvi"
          season="summer"
          rainSeason="prev_monsoon"
          title="Dry-season NDVI vs previous-monsoon rainfall"
        />

        <SectionHeader
          title="Cross-Sensor Validation & Species Hypothesis"
          description="Evaluating spatial convergence between MODIS and Landsat sensors, and investigating seasonal greenness retention proxies."
        />
        <LandsatPanel />
        <AgreementPanel />
        <EvergreenPanel />
      </RequireData>
    </>
  );
}
