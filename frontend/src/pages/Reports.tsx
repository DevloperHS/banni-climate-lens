import type { ReactNode } from "react";
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
    <div className="research-page">
      <PageHeader title="Research" subtitle="How rainfall, vegetation and water indicators explain the Banni greening story." />
      <div className="flex flex-wrap gap-2" role="group" aria-label="Research audience mode">
        <button className={`btn ${mode === "researcher" ? "btn-primary" : ""}`} onClick={() => setMode("researcher")}>Researcher / Environmental scientist</button>
        <button className={`btn ${mode === "student" ? "btn-primary" : ""}`} onClick={() => setMode("student")}>Student / Local community</button>
      </div>
      {mode === "student" ? (
        <StudentMode theme={theme} map={map} sc={sc} />
      ) : (
        <ResearcherMode q={q} map={map} sc={sc} man={man} maps={maps} setMaps={setMaps} variable={variable} setVariable={setVariable} agg={agg} setAgg={setAgg} />
      )}
    </div>
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
      <p className="research-lead">{RESEARCH_QUESTION}</p>
      <ResearchSplit />
    </Panel>
    <Panel title="2. Map" subtitle="Live layers appear when the API is available; static fallbacks appear when it is not.">
      <Q q={map} h={440}>{(w) => <ResearchMap dashboard={w.result} region={sc.region} source={sc.source} start={sc.start} end={sc.end} />}</Q>
      {map.error && <StaticMapFallback />}
    </Panel>
    <Panel title="3. Study area and data">
      <p className="text-sm text-[var(--text-2)]">Analysis window 68.80-69.95 E, 23.20-23.95 N: a rectangle of about 9,751 sq km, not the exact Banni polygon. The Banni grassland itself is commonly cited as about 2,618 sq km. n = 24 annual values (2001-2024).</p>
      <DataTable />
    </Panel>
    <Panel title="4. Evidence path" subtitle="Each step narrows what the satellite record can and cannot explain."><ResearchFlow /></Panel>
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
      <p className="mt-3 text-sm text-[var(--text-2)]">These results do not reproduce the Prosopis groundwater claim: the studies use different observables and periods, while our coarse GRACE record is inconclusive. Satellite evidence identifies a residual, not its cause.</p>
    </Panel>
    <RingCharts />
    <Panel title="8. Limitations">
      <div className="research-limits">{["Rectangle, not the Banni polygon.", "24 annual values.", "NDVI measures greenness, not species.", "No ground data.", "ET partly depends on NDVI; GLDAS and GRACE are coarse.", "Residual autocorrelation is suggested by Durbin-Watson.", "One influential year (2023, Cook's D above 4/n)."].map((x, i) => <div className="research-limit" key={x}><b>{i + 1}</b><span>{x}</span></div>)}</div>
      <p className="research-callout"><b>What this work achieves.</b> The study establishes rainfall-independent greening of +0.0017 NDVI/yr, p = 0.006, and makes the cause a testable question.</p>
    </Panel>
    <Panel title="9. What would settle it">
      <ol className="research-timeline">{[["CGWB / India-WRIS well records.", "Shows whether groundwater levels are really falling."], ["A Prosopis-versus-grass map with field training points.", "Separates trees from grass, which greenness alone cannot do."], ["Sap-flow or eddy-covariance measurements in Banni.", "Measures how much water the trees actually use."]].map(([t, d], i) => <li key={t}><span className="research-timeline__dot">{i + 1}</span><h3>{t}</h3><p>{d}</p></li>)}</ol>
    </Panel>
    <Panel title="10. References"><ol className="research-refs list-decimal pl-5 space-y-2">{REFERENCES.map(([text, href]) => <li key={text}><a className="text-[var(--teal)] underline" href={href} target="_blank" rel="noreferrer">{text}</a></li>)}</ol></Panel>
    <ReportDetails man={man} sc={sc} maps={maps} setMaps={setMaps} variable={variable} setVariable={setVariable} agg={agg} setAgg={setAgg} />
  </>;
}

function ResearchFlow() {
  const steps = [
    ["01", "Measure", "Aggregate monsoon NDVI and rainfall for 2001-2024; cross-check the dry season."],
    ["02", "Explain", "Fit rainfall against greenness and test the relationship with robust trend statistics."],
    ["03", "Remove", "Subtract the rainfall signal, then test whether the residual still rises."],
    ["04", "Challenge", "Compare sensors, water indicators, pixels and 1,000 no-trend replays."],
  ];
  return <div className="research-flow" aria-label="Research evidence flow">
    {steps.map(([number, title, text], index) => <div className="research-flow__step" key={number}>
      <div className="research-flow__circle">{number}</div>
      <div><h3>{title}</h3><p>{text}</p></div>
      {index < steps.length - 1 && <span className="research-flow__arrow" aria-hidden="true">→</span>}
    </div>)}
  </div>;
}

function ResearchQuestions() {
  const questions = [
    ["Q1", "Does monsoon rain explain the greening?", "Yes, for most of it."],
    ["Q2", "Is anything left after removing rain?", "Yes, a small rising trend."],
    ["Q3", "Do water data show stress?", "Not clearly; tests are inconclusive."],
    ["Q4", "Can satellites name the cause?", "No; they show the residual, not its cause."],
  ];
  return <div className="research-questions" aria-label="Research questions">
    {questions.map(([tag, question, answer], index) => <div className={`research-question ${index % 2 ? "research-question--reverse" : ""}`} key={tag}>
      <div className="research-question__copy"><span>{tag}</span><h3>{question}</h3><p>{answer}</p></div>
      <div className="research-question__circle" aria-hidden="true">{tag}</div>
    </div>)}
  </div>;
}

function StudentMode({ theme, map, sc }: { theme: string; map: ReturnType<typeof useApi<Wrapped<Dashboard>>>; sc: ReturnType<typeof useScope> }) {
  return <>
    <Panel title="1. Map" subtitle="A simple view of where the analysis looks."><Q q={map} h={440}>{(w) => <ResearchMap dashboard={w.result} region={sc.region} source={sc.source} start={sc.start} end={sc.end} simple />}</Q>{map.error && <StaticMapFallback />}</Panel>
    <SectionHeader title="Steps 2 to 6: How we studied it" description="The visual explanation shows the six steps and what satellites cannot tell us." />
    <iframe title="Methodology" src={`/methodology/index.html?theme=${theme}`} className="block min-h-[clamp(720px,100vh,1200px)] w-full border-0" />
    <StudentFindings />
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
  return <Panel title="Report details" subtitle="Pick a file, read what is inside, then download it.">
    <div className="research-dl">
      <div className="research-dl__card">
        <span className="research-dl__tag">PDF</span>
        <h3>Research report</h3>
        <p>The full written report: findings, trend tests, data sources and limits. Best for reading or sharing.</p>
        <div className="research-dl__controls">
          <label><input type="checkbox" checked={maps} onChange={(e) => setMaps(e.target.checked)} /> Include maps</label>
        </div>
        <a className="btn btn-primary" href={downloadUrl("/reports/pdf", { ...sc, maps })} download>Download PDF</a>
      </div>
      <div className="research-dl__card">
        <span className="research-dl__tag">CSV</span>
        <h3>Data table</h3>
        <p>One variable as a table of values by year or season. Opens in Excel or Google Sheets.</p>
        <div className="research-dl__controls">
          <Select label="Variable" value={variable} onChange={setVariable} options={[{ value: "ndvi", label: "NDVI (greenness)" }, { value: "precip", label: "Rainfall" }, { value: "water_extent", label: "Surface water" }]} />
          <Select label="Period" value={agg} onChange={setAgg} options={["monthly", "annual", "monsoon", "summer"].map((v) => ({ value: v, label: v }))} />
        </div>
        <a className="btn btn-primary" href={downloadUrl("/reports/export/csv", { ...sc, variable, agg })} download>Download CSV</a>
      </div>
      <div className="research-dl__card">
        <span className="research-dl__tag">GeoJSON</span>
        <h3>Map outline</h3>
        <p>The study-area shape for mapping tools such as QGIS or Google Earth. Not needed for reading the results.</p>
        <div className="research-dl__controls" />
        <a className="btn" href={downloadUrl("/reports/export/geojson", sc)} download>Download GeoJSON</a>
      </div>
    </div>
    <details className="research-inside">
      <summary>What is inside the PDF report</summary>
      <Q q={man} h={60}>{(m) => <ul className="research-inside__list">{m.sections.map((x) => <li key={x.id}><span className={`badge ${x.available ? "badge-ok" : ""}`}>{x.available ? "included" : "omitted"}</span>{x.title}</li>)}</ul>}</Q>
    </details>
  </Panel>;
}

function ResearchMap({ dashboard, region, source, start, end, simple = false }: { dashboard: Dashboard; region: string; source: string; start: number; end: number; simple?: boolean }) {
  const [mode, setMode] = useState<"trend" | "landcover" | "compare">("trend");
  const trend = dashboard.layers.find((l) => l.variable === "ndvi" && l.season === "monsoon");
  const firstYear = trend?.years[0] ?? start; const lastYear = trend?.years[trend.years.length - 1] ?? end;
  const trendOverlay = trend ? [{ id: "trend", visible: true, opacity: 0.85, bounds: trend.bounds, url: downloadUrl("/spatial/pixel-trend.png", { region, source, variable: "ndvi", season: "monsoon", start, end, q: 0.05, product: "significant" }) }] : [];
  const yearOverlay = (year: number) => trend ? [{ id: `ndvi-${year}`, visible: true, opacity: 0.85, bounds: trend.bounds, url: downloadUrl("/spatial/layer.png", { region, source, variable: "ndvi", season: "monsoon", year }) }] : [];
  return <div className="space-y-3">{!simple && <div role="tablist" className="flex flex-wrap gap-2">{([["trend", "Pixel NDVI trend"], ["landcover", "Land cover"], ["compare", "2001 vs 2024"]] as const).map(([v, l]) => <button key={v} role="tab" aria-selected={mode === v} className={`btn text-xs ${mode === v ? "btn-primary" : ""}`} onClick={() => setMode(v)}>{l}</button>)}</div>}{mode === "trend" && <MapView boundary={BANNI_BOUNDARY} overlays={trendOverlay} basemap="satellite" height="clamp(280px, 55vw, 560px)" />}{!simple && mode === "compare" && <div className="grid gap-3 md:grid-cols-2"><MapView boundary={BANNI_BOUNDARY} overlays={yearOverlay(firstYear)} basemap="satellite" height="clamp(260px, 34vw, 420px)" /><MapView boundary={BANNI_BOUNDARY} overlays={yearOverlay(lastYear)} basemap="satellite" height="clamp(260px, 34vw, 420px)" /></div>}{!simple && mode === "landcover" && <><StaticMapFallback only="land-cover.png" /><div className="flex flex-wrap gap-3 text-xs"><span>■ shrubland</span><span>■ savanna</span><span>■ grassland</span><span>■ barren</span><span>■ water</span></div></>}{!simple && <p className="muted text-xs">Analysis rectangle 68.80-69.95 E, 23.20-23.95 N, about 9,751 sq km; not the exact Banni polygon. Source: MODIS MOD13Q1 / MCD12Q1; Landsat.</p>}</div>;
}

function StaticMapFallback({ only }: { only?: string }) {
  const assets = only ? [[`/img/${only}`, only]] : [["/img/trend-map.png", "trend-map.png"], ["/img/land-cover.png", "land-cover.png"], ["/img/before-2001.png", "before-2001.png"], ["/img/after-2024.png", "after-2024.png"]];
  return <div className="grid gap-3 sm:grid-cols-2" aria-label="Static map fallbacks">{assets.map(([src, label]) => <figure key={src} className="rounded-lg border border-dashed border-[var(--border-hi)] bg-[var(--bg-soft)] p-2"><img src={src} alt={label} className="aspect-video w-full object-contain" onError={(e) => { e.currentTarget.hidden = true; e.currentTarget.nextElementSibling?.removeAttribute("hidden"); }} /><figcaption hidden className="p-4 text-center text-xs text-[var(--muted)]">This map image is not available right now.</figcaption><figcaption className="mt-1 text-xs text-[var(--muted)]">{label} · analysis rectangle 68.80-69.95 E, 23.20-23.95 N · MODIS/Landsat</figcaption></figure>)}</div>;
}

function ResearchSplit() {
  const { theme } = useApp();
  const [open, setOpen] = useState(true);
  const [full, setFull] = useState(false);
  useEffect(() => {
    if (!full) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setFull(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [full]);
  return <div className={`research-split ${open ? "" : "research-split--closed"}`}>
    <div className="research-split__left"><ResearchQuestions /></div>
    <div className={`research-split__right ${full ? "research-split__right--full" : ""}`}>
      <div className="research-split__bar">
        {!full && <button className="btn btn-primary text-sm" onClick={() => setOpen(!open)} aria-expanded={open}>{open ? "Hide research paper" : "Show research paper"}</button>}
        {(open || full) && <button className="btn text-sm" onClick={() => { setOpen(true); setFull(!full); }}>{full ? "Exit full screen (Esc)" : "⛶ Full screen"}</button>}
      </div>
      {(open || full) && <iframe title="Research paper" src={`/report/index.html?theme=${theme}`} className="research-split__frame" />}
    </div>
  </div>;
}

function Ring({ percent, label, note }: { percent: number; label: string; note: string }) {
  return <div className="research-ring-card">
    <div className="research-ring-wrap">
      <div className="research-ring" style={{ background: `conic-gradient(var(--teal) ${percent * 3.6}deg, color-mix(in srgb, var(--teal) 15%, transparent) 0deg)` }} />
      <b>{percent}%</b>
    </div>
    <div><h3>{label}</h3><p>{note}</p></div>
  </div>;
}

function RingCharts() {
  return <Panel title="At a glance">
    <div className="research-rings">
      <Ring percent={66} label="Explained by rain" note="Share of the greening trend that rainfall accounts for. About 34% remains." />
      <Ring percent={83} label="Year-to-year match" note="R-squared = 0.83: how closely greenness follows rain from one year to the next." />
    </div>
  </Panel>;
}


function StudentFindings() {
  const found = [
    ["trend", "Banni is getting greener", "Satellite pictures from 2001 to 2024 show the land becoming greener over the years.", "Think of auto-brightness. Sunlight (rain) lifts the screen. Banni keeps brightening even after rain, so something else is turning it up."],
    ["rain", "Rain explains most of it", "In wet years Banni is greener, in dry years less so (the link is strong: 0.91 out of 1).", "Think of a video's views. A trending topic (rain) brings most of the views."],
    ["question", "But rain is not the whole story", "About two thirds of the greening is explained by rain. About one third is left over, and that leftover keeps rising year after year. We replayed the 24 years 1,000 times as if nothing but rain were acting; only 6 of those replays showed a rise this strong, so luck is an unlikely explanation.", "Like asking if pure luck could explain a video's sudden jump. We tried luck 1,000 times. Only 6 tries matched."],
    ["sun", "It shows in the dry season too", "Even in March to May, when grass is dry, the land still looks greener over the years.", "Think of a student who scrolls social media daily but still does well in studies. Banni is like that: even in the dry months (March to May), it keeps getting greener."],
    ["map", "The map shows where", "Coloured patches mark where the greening is clear enough to count.", "Think of a traffic map. Only the busy roads are coloured. Banni's map colours only the patches where greening is clear enough to count."],
    ["search", "What we did not find", "We did not find proof that the water under the ground is falling. Satellites cannot see that clearly here.", "Like an Instagram story: you see “300 views” but not who watched. The satellite sees how green, not which plant or what is underground."],
  ];
  return <>
    <Panel title="7. Output: what we found">
      <div className="student-grid">{found.map(([icon, title, text, eg]) => <div className="student-card" key={title}>
        <span className="student-card__icon"><StudentIcon name={icon} /></span>
        <h3>{title}</h3><p>{text}</p>
        {title === "Banni is getting greener" && <PhoneVisual />}
        {title === "Rain explains most of it" && <ViewsVisual />}
        {title === "But rain is not the whole story" && <LuckVisual />}
        {title === "It shows in the dry season too" && <StudyVisual />}
        {title === "The map shows where" && <MapVisual />}
        {title === "What we did not find" && <UnseenVisual />}
        {eg && <p className="student-eg"><b>Example:</b> {eg}</p>}
      </div>)}</div>
    </Panel>
    <Panel title="8. Impact: what this can change">
      <div className="student-impact">
        <div className="student-card">
          <Illustration name="herders" alt="Illustration of a herder with a stick next to a buffalo on grassland" />
          <h3>For herders and villages</h3>
          <p>Green on a satellite picture is not always grass for animals. A thicket of Prosopis looks as green as a pasture from space. So “greener” does not automatically mean “better grazing”.</p>
          <p className="student-eg"><b>Example:</b> The Hulk is green too, but you would not feed him to a buffalo. Green is not the same as grass.</p>
        </div>
        <div className="student-card">
          <Illustration name="planners" alt="Illustration of a map grid with a few coloured patches and a pin" />
          <h3>For planners</h3>
          <p>Rainfall alone does not explain the change, so rainfall-based forecasts of grass may miss something. The map shows where to look first.</p>
          <p className="student-eg"><b>Example:</b> Guessing a gathering's size only from the weather will miss people who came for other reasons.</p>
        </div>
        <div className="student-card">
          <Illustration name="water" alt="Illustration of a well with groundwater below the ground" />
          <h3>For water</h3>
          <p>Some studies say Prosopis draws a lot of groundwater. Our satellite data could not confirm that. The people who know best are those who use the wells. Your observations (water levels, grass, shrubs) are the missing evidence.</p>
          <p className="student-eg"><b>Example:</b> A satellite is a drone photo of a gathering. The people standing there see far more.</p>
        </div>
        <div className="student-card">
          <Illustration name="prosopis" alt="Illustration of grass and a Prosopis shrub that look the same green" />
          <h3>For decisions about Prosopis</h3>
          <p>Many families also use Prosopis (charcoal, fuel). Any decision should be made with local people, using field checks, not from a satellite picture alone.</p>
          <p className="student-eg"><b>Example:</b> From a drone, a crowd at a gathering looks like one crowd. You cannot tell friends from strangers. Prosopis and grass look the same green.</p>
        </div>
      </div>
      <h3 className="student-next-title">What happens next</h3>
      <ol className="student-next">
        <li><span>1</span>Check well records</li>
        <li><span>2</span>Map where Prosopis actually grows</li>
        <li><span>3</span>Measure its water use on the ground</li>
      </ol>
    </Panel>
    <div className="student-final">
      <p>Banni is greening more than rain can explain.</p>
      <p>We know how much. We do not yet know why.</p>
    </div>
  </>;
}

function StudentIcon({ name }: { name: string }) {
  const shape = (() => {
    switch (name) {
      case "trend": return <><path d="M3 17l6-6 4 4 8-8" /><path d="M15 7h6v6" /></>;
      case "rain": return <><path d="M4 14.9A7 7 0 1 1 15.7 8h1.8a4.5 4.5 0 0 1 2.5 8.2" /><path d="M8 14v6M12 16v6M16 14v6" /></>;
      case "question": return <><circle cx="12" cy="12" r="9" /><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.7" /><path d="M12 17h.01" /></>;
      case "sun": return <><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></>;
      case "map": return <><path d="M9 3 3 5v16l6-2 6 2 6-2V3l-6 2-6-2z" /><path d="M9 3v16M15 5v16" /></>;
      default: return <><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></>;
    }
  })();
  return <svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{shape}</svg>;
}

function PhoneVisual() {
  const items: [string, string, number, string][] = [
    ["Dark room", "Screen dims", 15, "moon"],
    ["Bright sun", "Screen brightens", 55, "sun"],
    ["Banni", "Still rising", 95, "shrub"],
  ];
  const icon = (k: string) => k === "moon"
    ? <path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z" />
    : k === "sun"
      ? <><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></>
      : <><path d="M12 21v-9" /><path d="M12 12c0-4 3-6 7-6 0 4-3 6-7 6z" /><path d="M12 15c0-3-2-5-6-5 0 3 2 5 6 5z" /></>;
  return <div className="student-phones" role="img" aria-label="Three phones. In a dark room the screen is dim, in bright sun it is brighter, and Banni keeps getting brighter even after rain.">
    {items.map(([name, note, level, k]) => <div className="student-phone" key={name}>
      <div className="student-phone__body">
        <div className="student-phone__screen" style={{ background: `color-mix(in srgb, var(--teal) ${level}%, transparent)` }}>
          <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{icon(k)}</svg>
        </div>
      </div>
      <b>{name}</b><span>{note}</span>
    </div>)}
  </div>;
}

function ViewsVisual() {
  const items: [string, string, number, string][] = [
    ["Quiet topic", "Few views", 20, "play"],
    ["Trending topic", "Many views", 85, "play"],
    ["Rain year", "Banni greener", 85, "rain"],
  ];
  const icon = (k: string) => k === "play"
    ? <path d="M8 5v14l11-7z" />
    : <><path d="M4 14.9A7 7 0 1 1 15.7 8h1.8a4.5 4.5 0 0 1 2.5 8.2" /><path d="M8 14v6M12 16v6M16 14v6" /></>;
  return <ClipRow items={items} label="Three video thumbnails. A quiet topic gets few views, a trending topic gets many views, and a rainy year makes Banni greener." icon={icon} />;
}

function LuckVisual() {
  const hits = [37, 212, 389, 574, 731, 905];
  return <div className="student-luck" role="img" aria-label="1,000 small dots, one for each luck-only replay. Only 6 are highlighted: those matched the rise seen in Banni.">
    <div className="student-luck__head">
      <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <rect x="3" y="3" width="18" height="18" rx="3" />
        <circle cx="8.5" cy="8.5" r="1" fill="currentColor" stroke="none" />
        <circle cx="15.5" cy="8.5" r="1" fill="currentColor" stroke="none" />
        <circle cx="12" cy="12" r="1" fill="currentColor" stroke="none" />
        <circle cx="8.5" cy="15.5" r="1" fill="currentColor" stroke="none" />
        <circle cx="15.5" cy="15.5" r="1" fill="currentColor" stroke="none" />
      </svg>
      <b>Luck, tried 1,000 times</b>
    </div>
    <svg viewBox="0 0 255 105" className="student-luck__dots" aria-hidden="true">
      {Array.from({ length: 1000 }, (_, i) => {
        const hit = hits.includes(i);
        return <circle key={i} className={hit ? "hit" : ""} cx={5 + (i % 50) * 5} cy={5 + Math.floor(i / 50) * 5} r={hit ? 3 : 1.6} />;
      })}
    </svg>
    <div className="student-luck__legend">
      <span><i />One replay</span>
      <span><i className="hit" />Matched Banni: 6</span>
    </div>
  </div>;
}

function StudyVisual() {
  const items: [string, string, number, string][] = [
    ["Social media", "Busy, every day", 70, "chat"],
    ["Studies", "Still doing well", 85, "book"],
    ["Banni, Mar–May", "Still greener", 85, "sun"],
  ];
  const icon = (k: string) => k === "chat"
    ? <path d="M21 12a8 8 0 0 1-11.6 7.1L3 21l1.9-5.4A8 8 0 1 1 21 12z" />
    : k === "book"
      ? <><path d="M3 5h7a2 2 0 0 1 2 2v13a2 2 0 0 0-2-2H3z" /><path d="M21 5h-7a2 2 0 0 0-2 2v13a2 2 0 0 1 2-2h7z" /></>
      : <><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></>;
  return <ClipRow items={items} label="Three tiles. A student is busy on social media but still does well in studies. In the same way, Banni is still getting greener in the dry months, March to May." icon={icon} />;
}

function MapVisual() {
  const on = [2, 3, 12, 13, 14, 23, 24, 33, 34, 35, 44];
  return <div className="student-map" role="img" aria-label="A grid like a map. Only a few patches are coloured, the ones where greening is clear enough to count.">
    <svg viewBox="0 0 200 100" className="student-map__grid" aria-hidden="true">
      {Array.from({ length: 50 }, (_, i) => <rect key={i} className={on.includes(i) ? "on" : ""} x={(i % 10) * 20 + 1} y={Math.floor(i / 10) * 20 + 1} width="18" height="18" rx="3" />)}
    </svg>
    <div className="student-luck__legend">
      <span><i className="hit" />Clear greening</span>
      <span><i />Not clear enough</span>
    </div>
  </div>;
}

function UnseenVisual() {
  const items: [string, string, string][] = [
    ["You see", "300 views", "eye"],
    ["You can't see", "Who watched", "user"],
    ["Satellite sees", "How green", "leaf"],
  ];
  const icon = (k: string) => k === "eye"
    ? <><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z" /><circle cx="12" cy="12" r="3" /></>
    : k === "user"
      ? <><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></>
      : <><path d="M12 21v-9" /><path d="M12 12c0-4 3-6 7-6 0 4-3 6-7 6z" /><path d="M12 15c0-3-2-5-6-5 0 3 2 5 6 5z" /></>;
  return <div className="student-clips" role="img" aria-label="Three tiles. In a story you see the number of views but not who watched. A satellite sees how green the land is, but not which plant it is.">
    {items.map(([name, note, k]) => <div className="student-clip" key={name}>
      <div className={`student-clip__thumb ${k === "user" ? "student-clip__thumb--unknown" : ""}`}>
        <svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{icon(k)}</svg>
      </div>
      <b>{name}</b><span>{note}</span>
    </div>)}
  </div>;
}

function Illustration({ name, alt }: { name: string; alt: string }) {
  const scene = (() => {
    switch (name) {
      case "herders": return <>
        <rect className="ill-sky" width="300" height="150" />
        <circle className="ill-water" cx="255" cy="30" r="14" />
        <rect className="ill-ground" y="128" width="300" height="22" />
        <path className="ill-tealline" d="M20 128l-3-12M24 128v-14M28 128l3-12M240 128l-3-12M244 128v-14M248 128l3-12M118 128l-3-10M122 128v-12M126 128l3-10" />
        <circle className="ill-line ill-paper" cx="70" cy="70" r="8" />
        <path className="ill-line" d="M70 78v32M70 110l-8 18M70 110l8 18M70 88l22 6M92 58v70" />
        <ellipse className="ill-line ill-body" cx="175" cy="96" rx="40" ry="20" />
        <path className="ill-line" d="M150 112v16M162 114v14M190 114v14M202 112v16M135 90c-8 4-10 12-8 22" />
        <ellipse className="ill-line ill-body" cx="218" cy="92" rx="14" ry="11" />
        <path className="ill-line" d="M212 84c-8-8-6-16 2-18M226 84c8-8 6-16-2-18" />
        <circle className="ill-solid" cx="222" cy="90" r="1.8" />
      </>;
      case "planners": return <>
        <rect className="ill-sky" width="300" height="150" />
        <rect className="ill-line ill-paper" x="50" y="18" width="200" height="114" rx="8" />
        {Array.from({ length: 21 }, (_, i) => <rect key={i} className={[2, 3, 9, 10, 11, 17].includes(i) ? "ill-teal" : "ill-soft"} x={62 + (i % 7) * 26} y={30 + Math.floor(i / 7) * 30} width="24" height="24" rx="4" />)}
        <path className="ill-line ill-solid" d="M152 86l-9-14a10 10 0 1 1 18 0z" />
        <circle className="ill-paper" cx="152" cy="66" r="3.5" />
      </>;
      case "water": return <>
        <rect className="ill-sky" width="300" height="150" />
        <circle className="ill-water" cx="40" cy="30" r="14" />
        <rect className="ill-ground" y="70" width="300" height="80" />
        <path className="ill-water" d="M0 122q25-8 50 0t50 0 50 0 50 0 50 0 50 0V150H0z" />
        <rect className="ill-line ill-paper" x="130" y="70" width="40" height="56" />
        <rect className="ill-water" x="131" y="112" width="38" height="14" />
        <rect className="ill-line ill-paper" x="122" y="58" width="56" height="14" rx="3" />
        <path className="ill-line" d="M128 58V32M172 58V32M122 32h56M150 32v50" />
        <path className="ill-line ill-body" d="M143 82h14l-2 12h-10z" />
        <path className="ill-line" strokeDasharray="4 4" d="M50 112h70" />
      </>;
      default: return <>
        <rect className="ill-sky" width="300" height="150" />
        <rect className="ill-ground" y="128" width="300" height="22" />
        <path className="ill-tealline" d="M34 128l-6-26M42 128l-2-32M50 128v-34M58 128l3-32M66 128l8-26M78 128l-4-20M86 128l6-22M96 128l-2-18" />
        <path className="ill-line" d="M222 128v-30M222 110l-14-14M222 104l16-14M200 98l-4 4M244 96l4 4" />
        <circle className="ill-teal" cx="208" cy="82" r="16" />
        <circle className="ill-teal" cx="236" cy="82" r="16" />
        <circle className="ill-teal" cx="222" cy="64" r="18" />
        <path className="ill-line" d="M140 76h20M140 88h20" />
      </>;
    }
  })();
  return <svg viewBox="0 0 300 150" preserveAspectRatio="xMidYMid slice" className="student-illus" role="img" aria-label={alt}>{scene}</svg>;
}

type Clip = [name: string, note: string, level: number, key: string];

function ClipRow({ items, label, icon }: { items: Clip[]; label: string; icon: (k: string) => ReactNode }) {
  return <div className="student-clips" role="img" aria-label={label}>
    {items.map(([name, note, level, k]) => <div className="student-clip" key={name}>
      <div className="student-clip__thumb">
        <svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{icon(k)}</svg>
      </div>
      <div className="student-clip__track"><i style={{ width: `${level}%` }} /></div>
      <b>{name}</b><span>{note}</span>
    </div>)}
  </div>;
}
