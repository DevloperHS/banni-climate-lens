import { useState } from "react";
import { AnomalyPanel, PatternPanel, RegressionPanel, SeasonalPanel, SeriesPanel, TrendPanel } from "../components/analysis";
import { PageHeader, RequireData, SectionHeader, Select } from "../components/ui";

export default function Climate() {
  const [t, setT] = useState<"lst_day" | "lst_night">("lst_day");

  return (
    <>
      <PageHeader
        title="Climate Drivers"
        subtitle="Precipitation records from NASA GPM IMERG V07 (mm/month, converted from hourly precipitation rate) and radiometric land surface temperature from MODIS MOD11A2. LST measures radiometric skin temperature, not ambient 2m air temperature."
        badges={
          <div className="flex items-center gap-2">
            <span className="badge font-mono text-[11px] text-[var(--teal)] border-[var(--border-hi)]">
              GPM IMERG · 0.1°
            </span>
            <span className="badge font-mono text-[11px] text-[var(--amber)] border-[var(--border-hi)]">
              MODIS MOD11A2 · 1km
            </span>
          </div>
        }
      />

      <RequireData keys={["precip", "lst_day", "lst_night"]} what="Rainfall and land-surface-temperature data">
        <SectionHeader
          title="Precipitation Regimes"
          description="Monsoon and annual precipitation trends, seasonal concentration metrics, and historical anomaly analysis."
        />
        <SeriesPanel group="rainfall" variable="precip" title="Precipitation" defaultAgg="annual" />
        <TrendPanel group="rainfall" variable="precip" title="Rainfall" defaultAgg="monsoon" />

        <div className="grid gap-5 xl:grid-cols-2">
          <AnomalyPanel group="rainfall" variable="precip" title="Rainfall" />
          <PatternPanel group="rainfall" variable="precip" title="Rainfall" />
        </div>
        <SeasonalPanel group="rainfall" variable="precip" title="Rainfall" seasons={["monsoon", "summer", "postmonsoon", "winter"]} />

        <SectionHeader
          title="Land Surface Temperature (LST)"
          description="Thermal radiation dynamics by sensor overpass time (Daytime ~10:30 AM local solar time, Night-time ~10:30 PM)."
        />
        <div className="flex items-center gap-3 bg-[var(--bg-elev)] p-3 rounded-lg border border-[var(--border)] max-w-sm">
          <Select
            label="Satellite Overpass"
            value={t}
            onChange={setT}
            options={[
              { value: "lst_day", label: "Daytime Radiometric LST (MOD11A2)" },
              { value: "lst_night", label: "Night-time Radiometric LST (MOD11A2)" },
            ]}
          />
        </div>

        <SeriesPanel key={t} group="temperature" variable={t} title={t === "lst_day" ? "Daytime LST" : "Night-time LST"} defaultAgg="annual" />
        <TrendPanel key={`t${t}`} group="temperature" variable={t} title={t === "lst_day" ? "Daytime LST" : "Night-time LST"} />
        <SeasonalPanel key={`s${t}`} group="temperature" variable={t} title="LST" seasons={["summer", "monsoon", "winter"]} />

        <SectionHeader
          title="Empirical Environmental Relationships"
          description="Ordinary Least Squares regression models examining statistical association between climate drivers and vegetation greenness. Regression reflects empirical co-variation, not causal attribution."
        />
        <div className="grid gap-5 xl:grid-cols-2">
          <RegressionPanel y="ndvi" x="precip" agg="monsoon" title="Vegetation vs Monsoon Precipitation" />
          <RegressionPanel y="ndvi" x="lst_day" agg="monsoon" title="Vegetation vs Daytime Surface Temperature" />
        </div>
      </RequireData>
    </>
  );
}
