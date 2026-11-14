import { useEffect, useState } from "react";
import { PageHeader, Panel, Q, SectionHeader, Select, SyntheticBadge, useApi, useScope } from "../components/ui";
import { Dashboard, Wrapped, downloadUrl } from "../lib/api";
import MapView, { Legend } from "../components/MapView";
import { useApp } from "../state/AppState";

const BANNI_BBOX = { west: 68.8, south: 23.2, east: 69.95, north: 23.95 };
const BANNI_BOUNDARY: GeoJSON.Feature = {
  type: "Feature",
  properties: { kind: "analysis rectangle" },
  geometry: { type: "Polygon", coordinates: [[
    [BANNI_BBOX.west, BANNI_BBOX.south], [BANNI_BBOX.east, BANNI_BBOX.south],
    [BANNI_BBOX.east, BANNI_BBOX.north], [BANNI_BBOX.west, BANNI_BBOX.north],
    [BANNI_BBOX.west, BANNI_BBOX.south],
  ]] },
};

type Mode = "researcher" | "student";

const RESEARCH_QUESTION = "What is the major driver of the 2001-2024 greening of the Banni Grasslands, and does satellite evidence show a water deficit associated with it?";
const REFERENCES = [
  ["Tundia, K., Rao, A., Shastri, Y. (2022). Satellite based assessment of groundwater depletion by the invasive tree species Prosopis juliflora in a semi-arid region of Gujarat, India. EGU General Assembly 2022, EGU22-12254 (conference abstract).", "https://meetingorganizer.copernicus.org/EGU22/EGU22-12254.html"],
  ["Shiferaw et al. (2021). Water use of Prosopis juliflora and its impacts on catchment water budget and rural livelihoods in Afar Region, Ethiopia.", "https://pmc.ncbi.nlm.nih.gov/articles/PMC7846740"],
  ["Nerlekar, Misher, Hiremath et al. (2021). Mechanical removal vs lopping of Prosopis juliflora in Banni; news report.", "https://india.mongabay.com/2021/08/large-scale-removal-of-bannis-invasive-mad-tree-prosopis-is-not-the-solution-study/"],
  ["Pasha et al. (2014), cited in reference 1: +42.9% area under Prosopis cover in Kutch, 1977-2011 (secondary citation).", "https://meetingorganizer.copernicus.org/EGU22/EGU22-12254.html"],
  ["Data: MODIS MOD13Q1, MOD16A2GF, MOD11A2, MCD12Q1 v6.1; GPM IMERG V07; GLDAS-2.1 Noah; GRACE JPL mascons (NASA, via Google Earth Engine).", "https://earthengine.google.com/"],
  ["Banni grassland area (about 2,618 sq km, stated as “2,618 km”; secondary source).", "https://www.gktoday.in/banni-grassland"],
] as const;

export default function Reports() {
  const sc = useScope();
  const { theme } = useApp();
  const [mode, setMode] = useState<Mode>(() => {
    try { return localStorage.getItem("research.mode") === "student" ? "student" : "researcher"; } catch { return "researcher"; }
  });
  const [maps, setMaps] = useState(true);
  const [variable, setVariable] = useState("ndvi");
  const [agg, setAgg] = useState("annual");
  const man = useApi<{ sections: { id: string; title: string; available: boolean; needs: string }[]; ready: boolean; synthetic: boolean }>("/reports/manifest", { region: sc.region, source: sc.source });
  const q = useApi("/reports/insights", sc);
  const map = useApi<Wrapped<Dashboard>>("/dashboards/where_changed", sc);

  useEffect(() => { try { localStorage.setItem("research.mode", mode); } catch { /* storage is optional */ } }, [mode]);

  return (
    <>
      <PageHeader title="Research" subtitle="One evidence path from the rainfall relationship to the unexplained residual trend, with methods and sources at the end." />
      <div className="flex flex-wrap gap-2" role="group" aria-label="Research audience mode">
        <button className={`btn ${mode === "researcher" ? "btn-primary" : ""}`} onClick={() => setMode("researcher")}>Researcher / Environmental scientist</button>
        <button className={`btn ${mode === "student" ? "btn-primary" : ""}`} onClick={() => setMode("student")}>Student / Local community</button>
      </div>
      {mode === "student" ? (
        <StudentMode theme={theme} map={map} sc={sc} />
      ) : (
        <ResearcherMode q={q} map={map} sc={sc} man={man} maps={maps} setMaps={setMaps} variable={variable} setVariable={setVariable} agg={agg} setAgg={setAgg} />
      )}
    </>
  );
}

function ResearcherMode({ q, map, sc, man, maps, setMaps, variable, setVariable, agg, setAgg }: {
  q: ReturnType<typeof useApi>;
  map: ReturnType<typeof useApi<Wrapped<Dashboard>>>;
  sc: ReturnType<typeof useScope>; man: ReturnType<typeof useApi<{ sections: { id: string; title: string; available: boolean; needs: string }[]; ready: boolean; synthetic: boolean }>>;
  maps: boolean; setMaps: (v: boolean) => void; variable: string; setVariable: (v: string) => void; agg: string; setAgg: (v: string) => void;
}) {
  return <>
    <Panel title="1. Research question">
      <div className="rounded-lg border border-[var(--border-hi)] bg-[var(--bg-soft)] p-4">
        <p className="font-semibold">{RESEARCH_QUESTION}</p>
        <ul className="mt-3 list-disc pl-5 text-sm text-[var(--text-2)] space-y-1">
          <li>Q1. Does monsoon rainfall explain the greening?</li><li>Q2. After rainfall is removed, does a significant residual trend remain?</li>
          <li>Q3. Do independent water variables show a coherent signal of water stress?</li><li>Q4. Can the cause of the residual be identified from satellite data alone?</li>
        </ul>
      </div>
    </Panel>
    <Panel title="2. Map" subtitle="Live layers appear when the API is available; static fallbacks appear when it is not.">
      <Q q={map} h={440}>{(w) => <ResearchMap dashboard={w.result} region={sc.region} source={sc.source} start={sc.start} end={sc.end} />}</Q>
      {map.error && <StaticMapFallback />}
    </Panel>
    <Panel title="3. Study area and data">
      <p className="text-sm text-[var(--text-2)]">Analysis window 68.80-69.95 E, 23.20-23.95 N: a rectangle of about 9,770 sq km, not the exact Banni polygon. The Banni grassland itself is commonly cited as about 2,618 sq km. n = 24 annual values (2001-2024).</p>
      <DataTable />
    </Panel>
    <Panel title="4. Methods"><ol className="list-decimal pl-5 text-sm text-[var(--text-2)] space-y-1">{[
      "Aggregation: monsoon (Jun-Sep) NDVI and rainfall per year; annual and dry-season (Mar-May) cross-checks.",
      "Trend tests: Hamed-Rao correction for NDVI and residual trends; Sen's slope; plain Mann-Kendall for rainfall.",
      "RESTREND: regress monsoon NDVI on rainfall, then test residuals; NDVI ~ rain + year confirms the year term.",
      "Sensitivity: Terra vs Aqua, NDVI vs EVI, rainfall formulation, analysis window, and Cook's D.",
      "Dry-season test on Mar-May NDVI, when annual grasses are senescent.",
      "ET, soil moisture, LST and GRACE trend tests; ET re-tested with matched rainfall periods.",
      "Pixel-wise Sen slope with Benjamini-Hochberg FDR correction.",
      "Chance test: 1,000 no-trend replays; 6 were as strong as observed.",
    ].map((x) => <li key={x}>{x}</li>)}</ol></Panel>
    <Results />
    <Panel title="6. Outputs"><div className="flex flex-wrap gap-2">
      <a className="btn btn-primary text-xs" href={downloadUrl("/reports/export/csv", { ...sc, variable: "ndvi", agg: "annual" })} download>Annual NDVI CSV</a>
      <a className="btn btn-primary text-xs" href={downloadUrl("/reports/export/csv", { ...sc, variable: "precip", agg: "annual" })} download>Annual rainfall CSV</a>
      <a className="btn text-xs" href={downloadUrl("/reports/export/csv", { ...sc, variable: "water_extent", agg: "annual" })} download>Annual water CSV</a>
      <a className="btn text-xs" href={downloadUrl("/spatial/pixel-trend.tif", { ...sc, variable: "ndvi", season: "annual" })} download>Pixel-trend GeoTIFF</a>
      <a className="btn text-xs" href={downloadUrl("/reports/pdf", { ...sc, maps })} download>Report PDF</a>
    </div></Panel>
    <Panel title="7. Related published work and why our results differ">
      <div className="overflow-x-auto"><table className="w-full min-w-[700px] text-xs"><thead><tr><th>Study</th><th>Finding</th><th>Relation</th></tr></thead><tbody>
        <tr><td>Tundia, Rao and Shastri (EGU22-12254)</td><td>Groundwater depletion attributed to Prosopis in a shorter record.</td><td>Same direction as the Prosopis hypothesis. Our GRACE p = 0.21 was not significant.</td></tr>
        <tr><td>Shiferaw et al. 2021</td><td>Evergreen Prosopis uses groundwater in Afar.</td><td>Mechanism elsewhere; not proof for Banni.</td></tr>
        <tr><td>Nerlekar et al. 2021 (Mongabay)</td><td>Mechanical removal raised native plant diversity and cover.</td><td>Ecological and livelihood context.</td></tr>
      </tbody></table></div>
      <h3 className="mt-3 font-semibold">Why our satellite results differ from a 'Prosopis is depleting groundwater' finding</h3>
      <ol className="mt-3 list-decimal pl-5 text-sm text-[var(--text-2)] space-y-1">{["Different observable: greening is not drying.", "Different time window: 2002-2017 versus 2001-2024.", "Different data: no combined water balance or well records here.", "GRACE is 3 degrees and can dilute a local signal.", "Attribution by elimination is not direct measurement."].map((x) => <li key={x}>{x}</li>)}</ol>
    </Panel>
    <Panel title="8. Limitations"><ol className="list-decimal pl-5 text-sm text-[var(--text-2)] space-y-1">{["Rectangle, not the Banni polygon.", "24 annual values.", "NDVI measures greenness, not species.", "No ground data.", "ET partly depends on NDVI; GLDAS and GRACE are coarse.", "Residual autocorrelation is suggested by Durbin-Watson.", "One influential year (2023, Cook's D above 4/n)."].map((x) => <li key={x}>{x}</li>)}</ol><p className="mt-3 text-sm"><b>What this work achieves.</b> The study establishes rainfall-independent greening of +0.0017 NDVI/yr, p = 0.006, and makes the cause a testable question.</p></Panel>
    <Panel title="9. What would settle it"><ul className="list-disc pl-5 text-sm text-[var(--text-2)] space-y-1"><li>CGWB / India-WRIS well records.</li><li>A Prosopis-versus-grass map with field training points.</li><li>Sap-flow or eddy-covariance measurements in Banni.</li></ul></Panel>
    <Panel title="10. References"><ol className="list-decimal pl-5 text-sm space-y-2">{REFERENCES.map(([text, href]) => <li key={text}><a className="text-[var(--teal)] underline" href={href} target="_blank" rel="noreferrer">{text}</a></li>)}</ol></Panel>
    <SectionHeader title="Full research report" description="The long-form paper follows the research page." />
    <iframe title="Research Report" src="/report/index.html" className="block min-h-[clamp(720px,100vh,1200px)] w-full border-0" />
    <ReportDetails man={man} sc={sc} maps={maps} setMaps={setMaps} variable={variable} setVariable={setVariable} agg={agg} setAgg={setAgg} />
  </>;
}

function StudentMode({ theme, map, sc }: { theme: string; map: ReturnType<typeof useApi<Wrapped<Dashboard>>>; sc: ReturnType<typeof useScope> }) {
  return <>
    <Panel title="1. Map" subtitle="A simple view of where the analysis looks."><Q q={map} h={440}>{(w) => <ResearchMap dashboard={w.result} region={sc.region} source={sc.source} start={sc.start} end={sc.end} simple />}</Q>{map.error && <StaticMapFallback />}</Panel>
    <SectionHeader title="2-6. How we studied it" description="The visual explanation shows the six steps and what satellites cannot tell us." />
    <iframe title="Methodology" src={`/methodology/index.html?theme=${theme}`} className="block min-h-[clamp(720px,100vh,1200px)] w-full border-0" />
    <Panel title="7. Output: what we found"><ul className="list-disc pl-5 text-sm text-[var(--text-2)] space-y-2"><li><b>Banni is getting greener.</b> Satellite pictures from 2001 to 2024 show the land becoming greener over the years.</li><li><b>Rain explains most of it.</b> In wet years Banni is greener, in dry years less so (the link is strong: 0.91 out of 1).</li><li><b>But rain is not the whole story.</b> About two thirds of the greening is explained by rain. About one third is left over, and that leftover keeps rising year after year. We replayed the 24 years 1,000 times as if nothing but rain were acting; only 6 of those replays showed a rise this strong, so luck is an unlikely explanation.</li><li><b>It shows in the dry season too.</b> Even in March to May, when grass is dry, the land still looks greener over the years.</li><li><b>The map shows where.</b> Coloured patches mark where the greening is clear enough to count.</li><li><b>What we did not find.</b> We did not find proof that the water under the ground is falling. Satellites cannot see that clearly here.</li></ul></Panel>
    <Panel title="8. Impact: what this can change"><ul className="list-disc pl-5 text-sm text-[var(--text-2)] space-y-2"><li><b>For herders and villages.</b> Green on a satellite picture is not always grass for animals. A thicket of Prosopis looks as green as a pasture from space. So “greener” does not automatically mean “better grazing”.</li><li><b>For planners.</b> Rainfall alone does not explain the change, so rainfall-based forecasts of grass may miss something. The map shows where to look first.</li><li><b>For water.</b> Some studies say Prosopis draws a lot of groundwater. Our satellite data could not confirm that. The people who know best are those who use the wells. Your observations (water levels, grass, shrubs) are the missing evidence.</li><li><b>For decisions about Prosopis.</b> Many families also use Prosopis (charcoal, fuel). Any decision should be made with local people, using field checks, not from a satellite picture alone.</li><li><b>What happens next.</b> Check well records, map where Prosopis actually grows, and measure its water use on the ground.</li></ul></Panel>
    <p className="rounded-lg border border-[var(--border-hi)] bg-[var(--bg-soft)] p-4 font-semibold">Banni is greening more than rain can explain. We know how much. We do not yet know why.</p>
  </>;
}

function DataTable() {
  const rows = [["Vegetation greenness (NDVI, EVI)", "MODIS MOD13Q1 v6.1; Aqua cross-check", "250 m, 16-day", "Response"], ["Rainfall", "GPM IMERG Monthly V07", "~11 km", "Explanatory"], ["Evapotranspiration", "MODIS MOD16A2GF", "500 m, 8-day", "Water use"], ["Soil moisture", "GLDAS-2.1 Noah", "~28 km model", "Water context"], ["Land surface temperature", "MODIS MOD11A2", "1 km", "Observation"], ["Terrestrial water storage", "GRACE JPL mascons", "3 degrees", "Groundwater context"], ["Land cover", "MODIS MCD12Q1 v6.1", "500 m", "Shares"]];
  return <div className="mt-3 overflow-x-auto"><table className="w-full min-w-[650px] text-xs"><thead><tr><th>Variable</th><th>Product</th><th>Resolution</th><th>Role</th></tr></thead><tbody>{rows.map((r) => <tr key={r[0]}>{r.map((v) => <td key={v}>{v}</td>)}</tr>)}</tbody></table></div>;
}

function Results() {
  const r2 = 0.83;
  return <Panel title="5. Results"><p className="mb-3 text-xs text-[var(--muted)]">Values are for the full record, 2001-2024, and do not change with the period selector.</p><div className="overflow-x-auto"><table className="w-full min-w-[700px] text-xs"><thead><tr><th>Test</th><th>Result</th><th>Reading</th></tr></thead><tbody>{[
    ["Annual NDVI trend", "+0.0047/yr; Hamed-Rao p = 2.8e-05", "Greening is real"],
    ["Monsoon rainfall trend", "+15.7 mm/yr; p = 0.056 (Mann-Kendall)", "Not significant at 5%"],
    ["NDVI vs rain", `r = +0.91, R-squared = ${r2.toFixed(2)}`, "Rain explains year-to-year variance"],
    ["Residual trend (monsoon)", "+0.0017 NDVI/yr; p = 0.0059", "Greening not explained by rain"],
    ["Residual trend (dry season)", "Rising; p = approx 0.002", "Consistent, not proof"],
    ["ET / soil moisture / LST / GRACE", "ET p = 0.19; soil moisture no trend; GRACE p = 0.21", "Context and inconclusive tests"],
  ].map((r) => <tr key={r[0]}>{r.map((v) => <td key={v}>{v}</td>)}</tr>)}</tbody></table></div><p className="mt-3 text-sm text-[var(--text-2)]">Rain accounts for about 66% of the observed greening trend; about 34% remains. This differs from R-squared = {r2.toFixed(2)}, which is year-to-year variance.</p></Panel>;
}

function ReportDetails({ man, sc, maps, setMaps, variable, setVariable, agg, setAgg }: { man: ReturnType<typeof useApi<{ sections: { id: string; title: string; available: boolean; needs: string }[]; ready: boolean; synthetic: boolean }>>; sc: ReturnType<typeof useScope>; maps: boolean; setMaps: (v: boolean) => void; variable: string; setVariable: (v: string) => void; agg: string; setAgg: (v: string) => void }) {
  return <Panel title="Report details" subtitle="Data availability and export controls"><details><summary className="cursor-pointer text-sm font-semibold">Show report manifest and downloads</summary><Q q={man} h={60}>{(m) => <ul className="mt-3 grid gap-2 sm:grid-cols-2 text-xs">{m.sections.map((x) => <li key={x.id} className="p-2.5 rounded-md bg-[var(--bg-soft)] border border-[var(--border)]"><span className={`badge ${x.available ? "badge-ok" : ""}`}>{x.available ? "included" : "omitted"}</span> {x.title}</li>)}</ul>}</Q><div className="mt-4 flex flex-wrap gap-3 items-center"><a className="btn btn-primary text-xs" href={downloadUrl("/reports/pdf", { ...sc, maps })} download>⬇ PDF research report</a><label className="text-xs"><input type="checkbox" checked={maps} onChange={(e) => setMaps(e.target.checked)} /> Include maps</label><a className="btn text-xs" href={downloadUrl("/reports/export/geojson", sc)} download>⬇ GeoJSON</a></div><div className="mt-4 flex flex-wrap gap-3 items-end"><Select label="CSV Variable" value={variable} onChange={setVariable} options={[{ value: "ndvi", label: "NDVI" }, { value: "precip", label: "Rainfall" }, { value: "water_extent", label: "Surface water" }]} /><Select label="Temporal Aggregation" value={agg} onChange={setAgg} options={["monthly", "annual", "monsoon", "summer"].map((v) => ({ value: v, label: v }))} /><a className="btn btn-primary text-xs" href={downloadUrl("/reports/export/csv", { ...sc, variable, agg })} download>⬇ Download CSV</a></div></details></Panel>;
}

function ResearchMap({ dashboard, region, source, start, end, simple = false }: { dashboard: Dashboard; region: string; source: string; start: number; end: number; simple?: boolean }) {
  const [mode, setMode] = useState<"trend" | "landcover" | "compare">("trend");
  const trend = dashboard.layers.find((l) => l.variable === "ndvi" && l.season === "monsoon");
  const firstYear = trend?.years[0] ?? start; const lastYear = trend?.years[trend.years.length - 1] ?? end;
  const trendOverlay = trend ? [{ id: "trend", visible: true, opacity: 0.85, bounds: trend.bounds, url: downloadUrl("/spatial/pixel-trend.png", { region, source, variable: "ndvi", season: "monsoon", start, end, q: 0.05, product: "significant" }) }] : [];
  const yearOverlay = (year: number) => trend ? [{ id: `ndvi-${year}`, visible: true, opacity: 0.85, bounds: trend.bounds, url: downloadUrl("/spatial/layer.png", { region, source, variable: "ndvi", season: "monsoon", year }) }] : [];
  return <div className="space-y-3">{!simple && <div role="tablist" className="flex flex-wrap gap-2">{([["trend", "Pixel NDVI trend"], ["landcover", "Land cover"], ["compare", "2001 vs 2024"]] as const).map(([v, l]) => <button key={v} role="tab" aria-selected={mode === v} className={`btn text-xs ${mode === v ? "btn-primary" : ""}`} onClick={() => setMode(v)}>{l}</button>)}</div>}{mode === "trend" && <MapView boundary={BANNI_BOUNDARY} overlays={trendOverlay} basemap="satellite" height="clamp(280px, 55vw, 560px)" />}{!simple && mode === "compare" && <div className="grid gap-3 md:grid-cols-2"><MapView boundary={BANNI_BOUNDARY} overlays={yearOverlay(firstYear)} basemap="satellite" height="clamp(260px, 34vw, 420px)" /><MapView boundary={BANNI_BOUNDARY} overlays={yearOverlay(lastYear)} basemap="satellite" height="clamp(260px, 34vw, 420px)" /></div>}{!simple && mode === "landcover" && <><StaticMapFallback only="land-cover.png" /><div className="flex flex-wrap gap-3 text-xs"><span>■ shrubland</span><span>■ savanna</span><span>■ grassland</span><span>■ barren</span><span>■ water</span></div></>}{!simple && <p className="muted text-xs">Analysis rectangle 68.80-69.95 E, 23.20-23.95 N, about 9,770 sq km; not the exact Banni polygon. Source: MODIS MOD13Q1 / MCD12Q1; Landsat.</p>}</div>;
}

function StaticMapFallback({ only }: { only?: string }) {
  const assets = only ? [[`/img/${only}`, only]] : [["/img/trend-map.png", "trend-map.png"], ["/img/land-cover.png", "land-cover.png"], ["/img/before-2001.png", "before-2001.png"], ["/img/after-2024.png", "after-2024.png"]];
  return <div className="grid gap-3 sm:grid-cols-2" aria-label="Static map fallbacks">{assets.map(([src, label]) => <figure key={src} className="rounded-lg border border-dashed border-[var(--border-hi)] bg-[var(--bg-soft)] p-2"><img src={src} alt={label} className="aspect-video w-full object-contain" onError={(e) => { e.currentTarget.hidden = true; e.currentTarget.nextElementSibling?.removeAttribute("hidden"); }} /><figcaption hidden className="p-4 text-center text-xs text-[var(--muted)]">image to be added: {label}</figcaption><figcaption className="mt-1 text-xs text-[var(--muted)]">{label} · analysis rectangle 68.80-69.95 E, 23.20-23.95 N · MODIS/Landsat</figcaption></figure>)}</div>;
}
