import { describe, it, expect, beforeEach, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { mockApi, renderApp, trendBody, REGION } from "./helpers";
import { NAV } from "../components/Layout";
import { qs, ApiError, apiGet } from "../lib/api";
import { ErrorState, ResultBlock, fmtP } from "../components/ui";
import { TrendPanel } from "../components/analysis";

vi.mock("../components/MapView", () => ({
  default: ({ overlays, basemap }: { overlays: { id: string; visible: boolean }[]; basemap: string }) => (
    <div data-testid="map" data-overlays={overlays.filter((o) => o.visible).length} data-basemap={basemap} />
  ),
  Legend: ({ title }: { title: string }) => <div aria-label="Map legend">{title}</div>,
}));

beforeEach(() => { localStorage.clear(); document.documentElement.setAttribute("data-theme", "dark"); });

describe("navigation", () => {
  it("lists every required section and routes between them", async () => {
    mockApi({});
    renderApp("/");
    const nav = await screen.findByRole("navigation", { name: "Main navigation" });
    const labels = within(nav).getAllByRole("link").map((a) => a.textContent);
    expect(labels).toEqual(["Overview", "Research"]);
    expect(NAV).toHaveLength(2);
    await userEvent.click(within(nav).getByRole("link", { name: "Research" }));
    expect(await screen.findByRole("heading", { name: "Research" })).toBeInTheDocument();
    expect(screen.getByLabelText("Research evidence flow")).toBeInTheDocument();
  });
});

describe("overview", () => {
  it("renders the embedded overview without loading dashboard APIs", async () => {
    mockApi({});
    renderApp("/");
    const iframe = await screen.findByTitle("Banni Overview");
    expect(iframe).toHaveAttribute("src", "/overview/index.html");
    expect(iframe).toHaveAttribute("style", expect.stringContaining("border: 0"));
  });
});

describe("geometry honesty", () => {
  it("keeps the Overview route limited to the embedded document", async () => {
    mockApi({});
    renderApp("/");
    expect(await screen.findByTitle("Banni Overview")).toBeInTheDocument();
  });
});

describe("handover reproduction and data quality", () => {
  const rep = {
    result: {
      counts: { reproduced: 1, consistent: 1, "not reproduced": 1, "not available": 0 }, notes: ["Results are never adjusted to match."],
      reference_source: "Handover", reference_geometry: "rect", engine_cross_check: { agree: true, p_engine: 0.1, p_pymannkendall: 0.1 },
      protocol_differences: [{ item: "NDVI quality filtering", handover: "none", platform_default: "same", status: "aligned" }],
      colab: { n_years: 24, regression: { r2: 0.41, rain_coef: 0.0004, rain_p: 0.0004 }, verdict_rule: "CONFIRMED", verdict_note: "does not identify the cause" },
      rows: [
        { id: "a", label: "NDVI trend", page: 9, unit: "", reported: { direction: "increasing", p: 0.0001, slope: 0.00495 }, computed: { direction: "increasing", p: 0.0002, slope: 0.0049, z: 3.9 }, status: "reproduced", checks: {} },
        { id: "b", label: "Rain trend", page: 9, unit: "", reported: { direction: "no significant trend", p: 0.0561, slope: 15.7 }, computed: { direction: "no significant trend", p: 0.2, slope: 9, z: 1.2 }, status: "consistent", checks: {} },
        { id: "c", label: "Residual", page: 9, unit: "", reported: { direction: "increasing", p: 0.0059, slope: 0.0017, z: 2.753 }, computed: { direction: "no significant trend", p: 0.4, slope: 0.0003, z: 0.8 }, status: "not reproduced", checks: {} },
      ],
    }, meta: { region: "banni", kind: "observed", synthetic: false },
  };
  it("shows reported vs computed with an honest status for each row", async () => {
    mockApi({ "/api/statistics/handover-reproduction": { body: rep } });
    renderApp("/statistics");
    const t = await screen.findByRole("table", { name: "Handover comparison" });
    expect(within(t).getByText("reproduced")).toBeInTheDocument();
    expect(within(t).getByText("consistent")).toBeInTheDocument();
    expect(within(t).getByText("not reproduced")).toBeInTheDocument();
    expect(screen.getByText(/platform engine agrees/)).toBeInTheDocument();
    expect(screen.getAllByText(/never adjusted to match/).length).toBeGreaterThan(0);
  });
  it("tells the user when there is nothing to reproduce yet", async () => {
    mockApi({});
    renderApp("/statistics");
    expect((await screen.findAllByText("No data available"))[0]).toBeInTheDocument();
  });
  it("surfaces unit-plausibility flags and missing months", async () => {
    mockApi({ "/api/datasets/quality": { body: { result: { key: "precip", expected_months: 36, valid_months: 35, missing_months: 1, missing_list: ["2002-05"], completeness_pct: 97.2, valid_by_year: {}, stats: { min: 0.02, max: 0.02, mean: 0.02, sd: 0 }, plausible_range: [0, 1500], out_of_range: 0, flags: ["Mean annual rainfall 7 mm is outside 50-2000 mm: possible unit/conversion error"], raw_files: [], unit: "mm", ee_id: "NASA/GPM_L3/IMERG_MONTHLY_V07", retrieval_date: "2026-11-07", geometry: { id: "handover_bbox", kind: "bbox", area_km2: 9751, source: "h" } }, meta: { region: "banni", kind: "observed", synthetic: false } } } });
    renderApp("/statistics");
    const q = await screen.findByTestId("quality");
    expect(q).toHaveTextContent("2002-05");
    expect(q).toHaveTextContent("possible unit/conversion error");
    expect(q).toHaveTextContent("handover_bbox");
  });
});

describe("region and period selection", () => {
  it("changes the analysis period used by API requests", async () => {
    const f = mockApi({ "/api/vegetation/trend": { body: trendBody }, "/api/datasets": { body: { items: [{ key: "ndvi", available: true }], total: 1 } } });
    renderApp("/regions");
    expect(await screen.findByRole("button", { name: /Banni Grasslands/ })).toHaveAttribute("aria-pressed", "true");
    await userEvent.selectOptions(screen.getByLabelText("From", { exact: true }), "2010");
    await userEvent.selectOptions(screen.getByLabelText("To", { exact: true }), "2020");
    expect(screen.getByLabelText("From", { exact: true })).toHaveValue("2010");
    expect(screen.getByLabelText("To", { exact: true })).toHaveValue("2020");
    expect(f.mock.calls.some(([u]) => String(u).includes("/regions"))).toBe(true);
  });
  it("hides the synthetic sample from the default experience", async () => {
    mockApi({});
    renderApp("/");
    await screen.findByTitle("Banni Overview");
    expect(screen.queryByLabelText("Data source")).not.toBeInTheDocument();
    expect(screen.queryByText(/SYNTHETIC SAMPLE DATA/)).not.toBeInTheDocument();
  });
  it("ignores a stale 'sample' source unless demonstration mode is on", async () => {
    localStorage.setItem("gcl.source", "sample");
    const f = mockApi({});
    renderApp("/");
    await screen.findByTitle("Banni Overview");
    expect(f.mock.calls.filter(([u]) => String(u).includes("source=sample"))).toHaveLength(0);
  });
  it("swaps the data source and shows the synthetic banner in demonstration mode", async () => {
    localStorage.setItem("gcl.demo", "1");
    mockApi({});
    renderApp("/");
    await userEvent.selectOptions(await screen.findByLabelText("Data source"), "sample");
    expect(screen.getAllByRole("alert").some((a) => /SYNTHETIC SAMPLE DATA/.test(a.textContent ?? ""))).toBe(true);
    expect(localStorage.getItem("gcl.source")).toBe("sample");
  });
  it("toggles the theme", async () => {
    mockApi({});
    renderApp("/");
    await userEvent.click(await screen.findByRole("button", { name: "Toggle theme" }));
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
  });
});

describe("trend panel / result presentation", () => {
  it("shows method, dataset, period, direction, p-value, slope, interpretation and limitations", async () => {
    mockApi({ "/api/vegetation/trend": { body: trendBody } });
    renderApp("/", <TrendPanel group="vegetation" variable="ndvi" title="NDVI" />);
    const block = await screen.findByTestId("result-block");
    expect(block).toHaveTextContent("Hamed-Rao modified Mann-Kendall");
    expect(block).toHaveTextContent("MODIS/061/MOD13Q1");
    expect(block).toHaveTextContent("2001-2024");
    expect(block).toHaveTextContent("increasing");
    expect(block).toHaveTextContent("0.030");
    expect(block).toHaveTextContent("0.0021 NDVI/yr");
    expect(block).toHaveTextContent("Interpretation.");
    expect(block).toHaveTextContent("Limitations.");
    expect(screen.getByTestId("chart")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Test"), "mk");
    expect(screen.getByTestId("result-block")).toHaveTextContent("Mann-Kendall");
  });
  it("labels synthetic results", async () => {
    mockApi({ "/api/vegetation/trend": { body: { ...trendBody, meta: { ...trendBody.meta, synthetic: true } } } });
    renderApp("/", <TrendPanel group="vegetation" variable="ndvi" title="NDVI" />);
    expect((await screen.findAllByText("SYNTHETIC SAMPLE")).length).toBeGreaterThan(0);
  });
  it("shows an empty-state error with a Settings link when no data exists", async () => {
    mockApi({});
    renderApp("/", <TrendPanel group="vegetation" variable="ndvi" title="NDVI" />);
    expect(await screen.findByText("No data available")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open Settings" })).toHaveAttribute("href", "/settings");
  });
  it("renders a non-significant result without claiming a trend", () => {
    const t = { ...trendBody.result.mk, significant: false, direction: "no significant trend", p: 0.4 };
    renderApp("/", <ResultBlock t={t} meta={trendBody.meta as never} unit="NDVI" />);
    expect(screen.getByText(/no significant trend/)).toBeInTheDocument();
    expect(screen.getByText(/not significant/)).toBeInTheDocument();
  });
});

describe("satellite explorer map controls", () => {
  const layer = { variable: "ndvi", season: "annual", label: "NDVI", unit: "", cmap: "YlGn", years: [2001, 2002, 2003], bounds: REGION.bbox, vmin: 0.1, vmax: 0.5, crs: "EPSG:4326", kind: "observed" };
  it("exposes layer, year, opacity, visibility and basemap controls", async () => {
    mockApi({ "/api/spatial/layers": { body: { items: [layer, { ...layer, variable: "precip", label: "Precipitation", unit: "mm" }], total: 2 } } });
    renderApp("/satellite");
    const map = await screen.findByTestId("map");
    await waitFor(() => expect(map).toHaveAttribute("data-overlays", "1"));
    await userEvent.click(screen.getByLabelText("Show data layer"));
    expect(screen.getByTestId("map")).toHaveAttribute("data-overlays", "0");
    await userEvent.selectOptions(screen.getByLabelText("Basemap"), "streets");
    expect(screen.getByTestId("map")).toHaveAttribute("data-basemap", "streets");
    await userEvent.selectOptions(screen.getByLabelText("Variable"), "precip");
    expect(screen.getByLabelText("Map legend")).toHaveTextContent("Precipitation");
    expect(screen.getByLabelText("Year")).toHaveValue("2003");
  });
  it("explains what to do when there are no raster layers", async () => {
    mockApi({ "/api/spatial/layers": { body: { items: [], total: 0 } } });
    renderApp("/satellite");
    expect(await screen.findByText("No raster layers")).toBeInTheDocument();
  });
});

describe("api helpers & states", () => {
  it("qs drops empty params", () => { expect(qs({ a: 1, b: undefined, c: "", d: "x" })).toBe("?a=1&d=x"); });
  it("fmtP formats small p-values", () => { expect(fmtP(0.00001)).toBe("<0.001"); expect(fmtP(0.0345)).toBe("0.035"); });
  it("apiGet maps error envelope to ApiError", async () => {
    mockApi({ "/api/x": { status: 422, body: { error: { code: "validation_error", message: "bad" } } } });
    await expect(apiGet("/x")).rejects.toMatchObject({ code: "validation_error", message: "bad", status: 422 });
  });
  it("apiGet reports an unreachable backend", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("fail"); }));
    await expect(apiGet("/x")).rejects.toMatchObject({ code: "network" });
  });
  it("ErrorState explains Earth Engine problems", () => {
    renderApp("/", <ErrorState error={new ApiError(503, "earth_engine_unavailable", "EE down")} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Earth Engine unavailable");
  });
});

describe("statistics calculator", () => {
  it("validates input before calling the API", async () => {
    mockApi({});
    renderApp("/statistics");
    await userEvent.type(await screen.findByLabelText("Series values"), "1, 2, x");
    await userEvent.click(screen.getByRole("button", { name: "Run tests" }));
    expect(screen.getAllByRole("alert").some((a) => /Enter numbers/.test(a.textContent ?? ""))).toBe(true);
  });
});

describe("responsive layout", () => {
  it("has a toggle for the collapsed navigation", async () => {
    mockApi({});
    renderApp("/");
    const btn = await screen.findByRole("button", { name: "Toggle navigation" });
    expect(btn).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(btn);
    expect(btn).toHaveAttribute("aria-expanded", "true");
  });
});


describe("trend dashboards", () => {
  const card = (key: string, aggregation: string, role: string, extra = {}) => ({
    key, aggregation, role, label: key, dataset: "MODIS/061/MOD13Q1", unit: "NDVI", available: true, test: "Hamed-Rao modified Mann-Kendall",
    direction: "increasing", slope: 0.0049, slope_unit: "NDVI per year", ci: [0.003, 0.006], p: 0.0001, significant: true, n: 3, period: "2001-2003",
    synthetic: false, series: { years: [2001, 2002, 2003], values: [0.2, 0.25, 0.3], line: [0.2, 0.25, 0.3] }, ...extra,
  });
  const body = (id: string) => ({
    result: {
      id, title: id === "rain_green" ? "Rain and Green" : "Water and Heat", question: "Is Banni greener than its rain explains?",
      cards: id === "rain_green"
        ? [card("precip", "monsoon", "Monsoon rainfall total", { direction: "no significant trend", p: 0.056, series: { years: [2001, 2002, 2003], values: [100, 400, 250] } }), card("ndvi", "monsoon", "Monsoon greenness")]
        : [{ key: "groundwater", aggregation: "annual", role: "Groundwater depth in wells", label: "gw", dataset: "CGWB", unit: "m", available: false, reason: "No measured well levels uploaded." }],
      derived: id === "rain_green" ? [card("ndvi_rain_removed", "monsoon", "Monsoon greenness with the rain effect removed", {
        derived: true, p: 0.0059, slope: 0.0017, year_term: { coef: 0.0022, p: 0.0004, hac_p: 0.0001 }, verdict: "Residuals increase.", r2_rain: 0.83,
        series: { years: [2001, 2002, 2003], observed: [0.2, 0.25, 0.3], predicted: [0.21, 0.24, 0.27], rainfall: [100, 400, 250] } })] : [],
      yearly: { years: [2001, 2002, 2003], columns: { "precip:monsoon": [100, 400, 250], "ndvi:monsoon": [0.2, 0.25, 0.3] } },
      layers: [], limits: ["NDVI measures green cover. It cannot tell grass from shrub."],
      sources: [{ key: "ndvi", label: "NDVI (MODIS MOD13Q1)", dataset: "MODIS/061/MOD13Q1", provider: "NASA LP DAAC", url: "https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MOD13Q1", resolution: "250 m" }],
    },
    meta: { region: "banni", kind: "observed", synthetic: false },
  });
  const datasets = { body: { items: [{ key: "ndvi", label: "NDVI", available: true }], total: 1, earth_engine: {} } };

  it("shows concise result cards, the trust box and sources; the shared slider drives the readout", async () => {
    mockApi({ "/api/datasets": datasets, "/api/dashboards/rain_green": { body: body("rain_green") } });
    renderApp("/dashboards");
    expect(await screen.findByRole("heading", { name: "Trend Dashboards", level: 1 })).toBeInTheDocument();
    expect(await screen.findAllByTestId("result-card")).toHaveLength(3);
    expect(screen.getByText("Monsoon greenness with the rain effect removed", { selector: "div" })).toBeInTheDocument();
    expect(screen.getByText("Residuals increase.", { exact: false })).toBeInTheDocument();
    expect(screen.getByRole("note", { name: "Before you trust this" })).toHaveTextContent("cannot tell grass from shrub");
    expect(screen.getByRole("link", { name: "MODIS/061/MOD13Q1" })).toHaveAttribute("href", expect.stringContaining("MODIS_061_MOD13Q1"));
    const slider = screen.getByRole("slider", { name: "Dashboard year" });
    fireEvent.change(slider, { target: { value: "2002" } });
    expect(screen.getByTestId("dash-year")).toHaveTextContent("2002");
    fireEvent.change(slider, { target: { value: "2001" } });
    expect(screen.getByTestId("year-readout")).toHaveTextContent("100.000");
    expect(screen.queryByTestId("rain")).not.toBeInTheDocument();
  });

  it("shows the Aqua and EVI checks with their agreement, and names a check that is not yet available", async () => {
    const tr = (p: number, sig = true) => ({ direction: sig ? "increasing" : "no trend", slope: 0.0017, p, significant: sig, ci: [0.001, 0.003] as [number, number] });
    const row = (key: string, label: string, extra = {}) => ({
      key, label, role: "r", dataset: "MODIS", available: true, synthetic: false, period: "2002-2024", n: 23,
      raw_trend: tr(0.0001), residual_trend: tr(0.006), r2_rain: 0.8, year_term: { coef: 0.0021, p: 0.0005, hac_p: 0.0001 }, slope_unit: "NDVI per year", ...extra,
    });
    const b = body("rain_green");
    (b.result as Record<string, unknown>).checks = {
      period: "2002-2024", method: "Hamed-Rao", note: "Aqua starts 4 Jul 2002.", terra_aqua_monsoon: { n: 23, pearson_r: 0.987, mean_difference_aqua_minus_terra: -0.003 },
      seasons: [
        { season: "monsoon", label: "Monsoon (Jun-Sep)", rain_control: "same monsoon's rainfall",
          rows: [row("ndvi", "Terra NDVI (MOD13Q1)"), row("ndvi_aqua", "Aqua NDVI (MYD13Q1)"), row("evi", "Terra EVI (MOD13Q1)")],
          agreement: { status: "agree", text: "Aqua NDVI (MYD13Q1) and Terra EVI (MOD13Q1) agree with Terra NDVI after rainfall is removed." } },
        { season: "summer", label: "Dry season (Mar-May)", rain_control: "previous monsoon's rainfall",
          rows: [row("ndvi", "Terra NDVI (MOD13Q1)"), row("ndvi_aqua", "Aqua NDVI (MYD13Q1)", { residual_trend: tr(0.4, false) }),
            { key: "evi", label: "Terra EVI (MOD13Q1)", role: "r", dataset: "MODIS", available: false, reason: "No 'evi' series (test)." }],
          agreement: { status: "disagree", text: "Aqua NDVI (MYD13Q1) differs: no significant trend (p = 0.4)." } },
      ],
    };
    mockApi({ "/api/datasets": datasets, "/api/dashboards/rain_green": { body: b } });
    renderApp("/dashboards");
    const panel = await screen.findByTestId("sensor-checks");
    expect(screen.getByTestId("agreement-monsoon")).toHaveTextContent("Checks agree");
    expect(screen.getByTestId("agreement-summer")).toHaveTextContent("Checks disagree");
    expect(panel).toHaveTextContent("No 'evi' series (test).");                 // missing check is named, never filled in
    expect(panel).toHaveTextContent("no significant trend");
    expect(panel).toHaveTextContent("r = 0.987");
  });

  it("switches dashboards with the tabs and reports missing factors instead of inventing them", async () => {
    mockApi({ "/api/datasets": datasets, "/api/dashboards/rain_green": { body: body("rain_green") }, "/api/dashboards/water_heat": { body: body("water_heat") } });
    renderApp("/dashboards");
    await screen.findAllByTestId("result-card");
    await userEvent.click(screen.getByRole("tab", { name: /Water and Heat/ }));
    expect(await screen.findByText("No measured well levels uploaded.")).toBeInTheDocument();
    expect(screen.getByText("Not available")).toBeInTheDocument();
    expect(screen.queryByTestId("rain")).not.toBeInTheDocument();
  });
});
