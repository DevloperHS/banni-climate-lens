import { useState } from "react";
import { AdjustedPanel, AnomalyPanel, SeasonalPanel, SeriesPanel, TrendPanel } from "../components/analysis";
import { ChartFrame, LinesChart } from "../components/charts";
import { PageHeader, Panel, Q, RequireData, SectionHeader, Select, fmt, useApi, useScope } from "../components/ui";
import { GroundwaterPanel, SalinityPanel } from "../components/panels2";
import { Wrapped } from "../lib/api";

interface Inv {
  items: { id: string; title: string; status: string; dataset?: string; note: string }[];
}

interface EventRes {
  event: { name: string; date: string; note: string };
  pre_months: number;
  post_months: number;
  pre_mean_anomaly: number;
  post_mean_anomaly: number;
  delta: number;
  reference_years: number;
  percentile_in_reference: number;
  z_vs_reference: number | null;
  extreme: boolean;
  interpretation: string;
  unit: string;
  series: { x: string[]; values: (number | null)[] };
  reference: Record<string, number | null>;
  rain_adjusted?: {
    raw: { percentile_in_reference: number; z_vs_reference: number | null; delta: number };
    rain_adjusted: { percentile_in_reference: number; z_vs_reference: number | null; delta: number };
    adjustment: { r2_non_event_years: number; slope: number };
    interpretation: string;
  } | null;
}

function Investigations() {
  const sc = useScope();
  const q = useApi<Inv>("/water/investigations", { region: sc.region, source: sc.source });
  return (
    <Panel
      title="Hydro-Ecological Investigations Status"
      subtitle="Explicit documentation of testable hypotheses versus methodological and sensor limitations."
    >
      <Q q={q}>
        {(d) => (
          <div className="grid gap-3.5 md:grid-cols-2">
            {d.items.map((i) => (
              <article
                key={i.id}
                className="p-3.5 rounded-lg bg-[var(--bg-soft)] border border-[var(--border)] flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-center justify-between gap-2">
                    <h3 className="font-semibold text-xs sm:text-sm text-[var(--text)]">{i.title}</h3>
                    <span className={`badge ${i.status === "available" ? "badge-ok" : "badge-warn"}`}>
                      {i.status}
                    </span>
                  </div>
                  <p className="text-xs text-[var(--text-2)] mt-1.5 leading-relaxed">{i.note}</p>
                </div>
                {i.dataset && (
                  <div className="text-[11px] font-mono text-[var(--muted)] mt-2 pt-1.5 border-t border-[var(--border)]">
                    Dataset: {i.dataset}
                  </div>
                )}
              </article>
            ))}
          </div>
        )}
      </Q>
    </Panel>
  );
}

function CyclonePanel() {
  const sc = useScope();
  const [variable, setVariable] = useState("ndvi");
  const [adjust, setAdjust] = useState(true);
  const q = useApi<Wrapped<EventRes>>("/statistics/event", {
    region: sc.region,
    source: sc.source,
    variable,
    event_id: "biparjoy",
    adjust_rain: adjust,
  });

  return (
    <Panel
      title="Severe Weather Event Impact: Cyclone Biparjoy (June 2023)"
      subtitle="Evaluates post-cyclone environmental response against a historical placebo distribution (same calendar window in all reference years)."
      actions={
        <div className="flex items-center gap-2">
          <Select
            label="Response Variable"
            value={variable}
            onChange={setVariable}
            options={[
              { value: "ndvi", label: "NDVI (Canopy Greenness)" },
              { value: "precip", label: "Rainfall (GPM IMERG)" },
              { value: "lst_day", label: "LST Day (MOD11A2)" },
              { value: "water_extent", label: "Surface Water (JRC, through 2022)" },
              { value: "water_extent_mndwi", label: "Surface Water (Landsat MNDWI, 2013+)" },
              { value: "sm_root", label: "Root-Zone Soil Moisture" },
            ]}
          />
        </div>
      }
    >
      <div className="mb-3">
        <label className="flex items-center gap-2 text-xs font-medium text-[var(--text-2)] cursor-pointer select-none">
          <input
            type="checkbox"
            checked={adjust}
            onChange={(e) => setAdjust(e.target.checked)}
            className="rounded accent-[var(--accent)]"
          />
          Residualize pre/post change against precipitation anomaly (isolate non-rainfall effect)
        </label>
      </div>

      <Q q={q}>
        {(d) => {
          const r = d.result;
          const rows = r.series.x
            .filter((x) => x >= `${new Date(r.event.date).getFullYear() - 2}-01`)
            .map((x) => ({ x, v: r.series.values[r.series.x.indexOf(x)] }));

          return (
            <div className="grid gap-5 xl:grid-cols-2">
              <ChartFrame
                title={`${variable} Trajectory Around Landfall`}
                meta={d.meta}
                filename={`biparjoy_${variable}`}
                height={260}
                subtitle={`Cyclone landfall: ${r.event.date}`}
              >
                <LinesChart rows={rows} lines={[{ key: "v", name: variable, dots: true }]} unit={r.unit} />
              </ChartFrame>

              <div className="text-xs sm:text-sm space-y-3">
                <div className="tbl-wrap">
                  <table className="tbl">
                    <tbody>
                      <tr>
                        <td className="muted w-1/2">Mean Anomaly ({r.pre_months} mo prior)</td>
                        <td className="font-mono">{fmt(r.pre_mean_anomaly, 4)}</td>
                      </tr>
                      <tr>
                        <td className="muted">Mean Anomaly ({r.post_months} mo post)</td>
                        <td className="font-mono">{fmt(r.post_mean_anomaly, 4)}</td>
                      </tr>
                      <tr>
                        <td className="muted font-semibold">Change (Post − Pre)</td>
                        <td className="font-mono font-bold text-[var(--text)]">{fmt(r.delta, 4)}</td>
                      </tr>
                      <tr>
                        <td className="muted">Percentile vs Placebo Years (n={r.reference_years})</td>
                        <td>
                          <span className="font-mono font-bold">{r.percentile_in_reference.toFixed(0)}th percentile</span>{" "}
                          {r.extreme && <span className="badge badge-warn ml-1">statistically extreme</span>}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>

                <p className="text-xs leading-relaxed text-[var(--text-2)] bg-[var(--bg-soft)] p-2.5 rounded border border-[var(--border)]">
                  {r.interpretation}
                </p>

                {r.rain_adjusted && (
                  <div className="p-3 rounded-lg bg-[var(--bg-soft)] border border-[var(--border)] text-xs space-y-1" data-testid="event-adjusted">
                    <div className="font-semibold text-[var(--text)]">Rainfall-adjusted Anomaly Evaluation</div>
                    <p className="text-[var(--text-2)]">
                      Uncontrolled z-score: <b className="font-mono">{fmt(r.rain_adjusted.raw.z_vs_reference, 1)}</b> ({r.rain_adjusted.raw.percentile_in_reference.toFixed(0)}th percentile).
                      Controlled z-score: <b className="font-mono">{fmt(r.rain_adjusted.rain_adjusted.z_vs_reference, 1)}</b> ({r.rain_adjusted.rain_adjusted.percentile_in_reference.toFixed(0)}th percentile).
                      Rainfall model R² = <span className="font-mono">{fmt(r.rain_adjusted.adjustment.r2_non_event_years, 2)}</span>.
                    </p>
                    <p className="muted text-[11px]">{r.rain_adjusted.interpretation}</p>
                  </div>
                )}
                <p className="muted text-[11px]">{r.event.note}</p>
              </div>
            </div>
          );
        }}
      </Q>
    </Panel>
  );
}

export default function Water() {
  const [sm, setSm] = useState<"sm_root" | "sm_surface">("sm_root");

  return (
    <>
      <PageHeader
        title="Water Resources & Hydrology"
        subtitle="Evapotranspiration (MOD16A2, Penman-Monteith energy balance), soil moisture (NASA GLDAS Noah, 0.25°), surface-water persistence (JRC Global Surface Water), and measured groundwater well records. Satellite soil moisture and ET models do not determine aquifer changes."
        badges={
          <div className="flex items-center gap-2">
            <span className="badge font-mono text-[11px] text-[var(--teal)] border-[var(--border-hi)]">
              MOD16A2 · 500m
            </span>
            <span className="badge font-mono text-[11px] text-[var(--blue)] border-[var(--border-hi)]">
              GLDAS · 0.25°
            </span>
            <span className="badge font-mono text-[11px]">JRC GSW · 30m</span>
          </div>
        }
      />

      <Investigations />

      <RequireData keys={["et", "sm_root", "sm_surface", "water_extent"]} what="Evapotranspiration, soil-moisture and surface-water data">
        <SectionHeader
          title="Evapotranspiration (ET)"
          description="MODIS 8-day satellite ET composites converted to daily and annual totals (mm/year)."
        />
        <SeriesPanel group="water" variable="et" title="Evapotranspiration" defaultAgg="annual" />
        <TrendPanel group="water" variable="et" title="Evapotranspiration" />
        <AdjustedPanel response="et" season="annual" title="Rainfall-adjusted ET" />

        <SectionHeader
          title="Soil Moisture Dynamics (GLDAS Noah)"
          description="Modelled volumetric soil moisture across root-zone (0–100 cm) and surface (0–10 cm) layers."
        />
        <div className="flex items-center gap-3 bg-[var(--bg-elev)] p-3 rounded-lg border border-[var(--border)] max-w-sm">
          <Select
            label="Soil Depth Layer"
            value={sm}
            onChange={setSm}
            options={[
              { value: "sm_root", label: "Root Zone Soil Moisture (0–100 cm depth)" },
              { value: "sm_surface", label: "Surface Soil Moisture (0–10 cm depth)" },
            ]}
          />
        </div>

        <SeriesPanel key={sm} group="water" variable={sm} title="Soil moisture" defaultAgg="annual" />
        <TrendPanel key={`t${sm}`} group="water" variable={sm} title="Soil moisture" defaultAgg="summer" />
        <SeasonalPanel key={`s${sm}`} group="water" variable={sm} title="Soil moisture" seasons={["summer", "monsoon", "winter"]} />

        <SectionHeader
          title="Surface Water Inundation (JRC GSW)"
          description="Long-term Landsat surface water history (1984–2021) recording inundation occurrence and anomaly fluctuations."
        />
        <SeriesPanel group="water" variable="water_extent" title="Surface-water extent" />
        <AnomalyPanel group="water" variable="water_extent" title="Surface-water extent" />
      </RequireData>

      <SectionHeader
        title="Soil Salinity Proxy"
        description="SI1 spectral index proxy unvalidated without measured ground electrical conductivity (EC)."
      />
      <SalinityPanel />

      <SectionHeader
        title="In-Situ Groundwater & Extreme Events"
        description="Empirical piezometer water table levels (CGWB/WRIS) and extreme meteorological perturbation analysis."
      />
      <GroundwaterPanel />
      <CyclonePanel />
    </>
  );
}
