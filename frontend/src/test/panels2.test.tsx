import { describe, it, expect, beforeEach, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { mockApi, renderApp } from "./helpers";
import { AvailabilityStrip, ComparePanel, EvergreenPanel, GroundwaterPanel, JobsPanel, SalinityPanel, CsvUpload } from "../components/panels2";
import { getToken, setToken } from "../lib/api";

vi.mock("../components/MapView", () => ({
  default: () => <div data-testid="map" />,
  Legend: () => <div />,
}));

beforeEach(() => { localStorage.clear(); sessionStorage.clear(); });

const meta = { region: "banni", kind: "observed", synthetic: false };

describe("availability strip & global period", () => {
  it("shows which datasets exist, distinguishing synthetic from processed", async () => {
    mockApi({ "/api/datasets": { body: { items: [
      { key: "ndvi", available: true, kind: "observed", processing_period: "2001-2024" }, { key: "precip", available: false }, { key: "et", available: true, kind: "synthetic" }], total: 3 } } });
    renderApp("/", <AvailabilityStrip />);
    const s = await screen.findByTestId("availability");
    await waitFor(() => expect(s).toHaveTextContent("● NDVI"));
    expect(s).toHaveTextContent("○ Rain");
    expect(within(s).getByText(/● ET/)).toHaveClass("badge-warn");
    expect(within(s).getByText(/● NDVI/)).toHaveClass("badge-ok");
  });

  it("header period selector feeds every request", async () => {
    const f = mockApi({ "/api/datasets": { body: { items: [], total: 0, earth_engine: {} } }, "/api/reports/insights": { body: { findings: [], notes: [], synthetic: false, question: "q" } } });
    renderApp("/");
    await waitFor(() => expect(screen.getByLabelText("Period start")).toHaveValue("2001"));      // options exist once the region has loaded
    await userEvent.selectOptions(screen.getByLabelText("Period start"), "2010");
    await userEvent.selectOptions(screen.getByLabelText("Period end"), "2020");
    await waitFor(() => expect(f.mock.calls.some(([u]) => String(u).includes("/reports/insights") && String(u).includes("start=2010") && String(u).includes("end=2020"))).toBe(true));
  });
});

describe("environmental comparison", () => {
  const body = { result: {
    n: 24, years: [2001, 2002, 2003], variables: ["ndvi", "precip"], detrended: false, labels: {}, units: {}, aggregation: "monsoon",
    pearson: [[1, 0.8], [0.8, 1]], pearson_p: [[0, 0.0001], [0.0001, 0]], spearman: [[1, 0.7], [0.7, 1]],
    pairs: [{ a: "ndvi", b: "precip", pearson_r: 0.8, pearson_p: 0.0001, pearson_p_bh: 0.0001, significant_bh: true, spearman_rho: 0.7 }],
    zscores: { ndvi: [0, 1, -1], precip: [0.1, 0.9, -1] }, anomaly_years: [{ year: 2002, variables: ["ndvi", "precip"], coincident: true }],
    association_note: "Correlation describes co-variation.", statement: "ASSOCIATION, PREDICTION and CAUSATION are reported separately.", causation_note: "This analysis cannot establish causation.",
    regression: { response: "ndvi", predictors: ["precip"], r2: 0.64, adj_r2: 0.62, coefficients: [{ name: "intercept", coef: 0.1, se: 0.01, t: 5, p: 0.001, ci_low: 0.08, ci_high: 0.12, hac_p: 0.002 }, { name: "precip", coef: 0.0004, se: 0.0001, t: 6, p: 0.0001, ci_low: 0.0002, ci_high: 0.0006, hac_p: 0.001 }],
      diagnostics: { durbin_watson: 2, ljung_box_p: 0.4, shapiro_p: 0.5, breusch_pagan_p: 0.6, outlier_indices: [] }, residuals: [0, 0, 0] },
    prediction: { r2_in_sample: 0.64, r2_loo_cv: 0.55, note: "Leave-one-out R2 measures prediction of held-out years." },
    partial_correlations: [{ variable: "precip", r: 0.8, p: 0.0001, controls: [] }],
  }, meta: { ...meta, synthetic: false } };

  it("reports association, prediction and the causation limit separately", async () => {
    const f = mockApi({ "/api/statistics/compare": { body } });
    renderApp("/", <ComparePanel />);
    const c = await screen.findByTestId("compare");
    expect(within(c).getByRole("table", { name: "Correlation matrix" })).toBeInTheDocument();
    expect(c).toHaveTextContent("significant after FDR");
    expect(screen.getByTestId("loo")).toHaveTextContent("0.55");
    expect(c).toHaveTextContent("cannot establish causation");
    expect(c).toHaveTextContent("coincident");
    expect(f.mock.calls.some(([u]) => String(u).includes("variables=ndvi%2Cprecip%2Clst_day%2Cet"))).toBe(true);
  });

  it("refuses to run with fewer than two variables", async () => {
    mockApi({ "/api/statistics/compare": { body } });
    renderApp("/", <ComparePanel />);
    await screen.findByTestId("compare");
    for (const l of ["Precipitation", "LST day", "ET"]) await userEvent.click(screen.getByLabelText(l, { exact: true }));
    expect(screen.getByRole("alert")).toHaveTextContent("Select at least two variables");
  });
});

describe("groundwater and salinity honesty", () => {
  it("asks for measured data when none is uploaded", async () => {
    mockApi({});
    renderApp("/", <GroundwaterPanel />);
    expect(await screen.findByLabelText("Well readings CSV (date,value[,well_id])")).toBeInTheDocument();
    expect((await screen.findAllByText("No data available"))[0]).toBeInTheDocument();
  });

  it("shows the validation report and per-well trends", async () => {
    mockApi({ "/api/water/groundwater/wells": { body: { result: {
      wells: { W0: { dates: ["2010-01-01", "2011-01-01"], values: [10, 10.5] } }, unit: "m below ground level", note: "Only measured levels can support a groundwater claim.",
      validation: { rows_in: 12, rows_valid: 10, n_wells: 1, date_range: ["2010-01-01", "2020-01-01"], rejected_by_reason: { "unparseable date": 2 }, duplicates_removed: 0, warnings: ["Large step changes detected"], unit_assumption: "metres below ground level", wells_with_large_jumps: [] },
      trends: [{ well_id: "W0", status: "tested", n_years: 10, direction: "increasing", p: 0.001, p_fdr: 0.001, slope_m_per_yr: 0.3, ci_low: 0.2, ci_high: 0.4, meaning: "water table deepening", significant_fdr: true }] }, meta: { ...meta, kind: "user-supplied" } } } });
    renderApp("/", <GroundwaterPanel />);
    const w = await screen.findByTestId("wells");
    expect(w).toHaveTextContent("10 of 12 rows valid");
    expect(w).toHaveTextContent("2× unparseable date");
    expect(w).toHaveTextContent("Large step changes");
    expect(within(w).getByRole("table", { name: "Per-well trends" })).toHaveTextContent("water table deepening");
  });

  it("keeps the salinity proxy UNVALIDATED without field data", async () => {
    mockApi({ "/api/salinity/validation": { body: { result: { status: "no_field_data", message: "No field EC measurements uploaded. The salinity index is UNVALIDATED." }, meta } } });
    renderApp("/", <SalinityPanel />);
    const v = await screen.findByTestId("salinity-validation");
    expect(v).toHaveTextContent("UNVALIDATED");
    expect(v).not.toHaveTextContent("Spearman");
  });
});

describe("Prosopis investigation", () => {
  it("is labelled exploratory and states that no ground truth exists", async () => {
    mockApi({ "/api/spatial/evergreen": { body: { result: {
      pixels_tested: 5400, significant_increase_fdr: 10, significant_decrease_fdr: 1, significant_increase_uncorrected: 50, significant_decrease_uncorrected: 5, mean_index: 0.6, years: [2001, 2024],
      status: "EXPLORATORY - hypothesis generating, not validated, not a species classification", interpretation: "Without field labels the index cannot tell them apart.", mask: null,
      bounds: { south: 23.2, north: 23.95, west: 68.8, east: 69.95 }, ground_truth: { available: false, message: "No ground-truth labels exist for this project.", required: "At least 10 per class." } }, meta } } });
    renderApp("/", <EvergreenPanel />);
    const st = await screen.findByTestId("evergreen-status");
    expect(st).toHaveTextContent("not a species classification");
    expect(screen.getByTestId("ground-truth")).toHaveTextContent("No ground-truth labels exist");
    expect(screen.queryByTestId("separability")).not.toBeInTheDocument();
  });
});

describe("pipeline job control", () => {
  const job = (o: Record<string, unknown>) => ({ id: "j1", status: "running", created: "2026-11-07T10:00:00+00:00", error: null, spec: { region: "banni", start: 2001, end: 2024, tasks: [] },
    progress: { done: 1, total: 2, percent: 50 }, tasks: [{ id: 0, label: "series:ndvi", status: "done", attempts: 1, error: null }, { id: 1, label: "series:precip", status: "running", attempts: 1, error: null }], ...o });

  it("shows progress, lets the user cancel, and sends the API token", async () => {
    setToken("tok123");
    const f = mockApi({ "/api/datasets/jobs": { body: { items: [job({})], total: 1 } }, "/api/datasets/jobs/j1/cancel": { body: job({ status: "cancelled" }) } });
    renderApp("/", <JobsPanel />);
    const bar = await screen.findByRole("progressbar", { name: /Job j1 progress/ });
    expect(bar).toHaveAttribute("aria-valuenow", "50");
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(f.mock.calls.some(([u]) => String(u).endsWith("/jobs/j1/cancel"))).toBe(true));
    const call = f.mock.calls.find(([u]) => String(u).endsWith("/jobs/j1/cancel"))!;
    expect((call[1] as RequestInit).method).toBe("POST");
    expect(((call[1] as RequestInit).headers as Record<string, string>)["Authorization"]).toBe("Bearer tok123");
  });

  it("offers retry for failed jobs, shows task errors and the log", async () => {
    mockApi({ "/api/datasets/jobs": { body: { items: [job({ status: "failed", tasks: [{ id: 0, label: "series:ndvi", status: "failed", attempts: 2, error: "RuntimeError: quota" }], progress: { done: 1, total: 1, percent: 100 } })], total: 1 } },
      "/api/datasets/jobs/j1/log": { body: { id: "j1", log: "FAILED series:ndvi: RuntimeError: quota\nTraceback..." } } });
    renderApp("/", <JobsPanel />);
    expect(await screen.findByRole("button", { name: "Retry unfinished" })).toBeInTheDocument();
    expect(screen.getByText(/RuntimeError: quota/)).toBeInTheDocument();
    expect(screen.getByText(/attempt 2/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Log" }));
    expect(await screen.findByText(/Traceback/)).toBeInTheDocument();
  });

  it("surfaces an API error from cancel instead of swallowing it", async () => {
    mockApi({ "/api/datasets/jobs": { body: { items: [job({})], total: 1 } }, "/api/datasets/jobs/j1/cancel": { status: 401, body: { error: { code: "unauthorized", message: "A valid API token is required." } } } });
    renderApp("/", <JobsPanel />);
    await userEvent.click(await screen.findByRole("button", { name: "Cancel" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("A valid API token is required");
  });
});

describe("token handling and uploads", () => {
  it("keeps the token in sessionStorage only", () => {
    setToken("abc");
    expect(getToken()).toBe("abc");
    expect(sessionStorage.getItem("gcl.token")).toBe("abc");
    expect(localStorage.getItem("gcl.token")).toBeNull();
    setToken("");
    expect(getToken()).toBe("");
  });

  it("CsvUpload requires a file and reports server validation errors", async () => {
    mockApi({ "/api/datasets/upload": { status: 422, body: { error: { code: "bad_csv", message: "CSV needs columns 'date' and 'value'" } } } });
    renderApp("/", <CsvUpload label="CSV" path="/datasets/upload" fields={{ region: "banni" }} />);
    await userEvent.click(screen.getByRole("button", { name: "Upload" }));
    expect(screen.getByRole("status")).toHaveTextContent("Choose a CSV file first");
    const file = new File(["a,b\n1,2"], "x.csv", { type: "text/csv" });
    await userEvent.upload(screen.getByLabelText("CSV"), file);
    await userEvent.click(screen.getByRole("button", { name: "Upload" }));
    expect(await screen.findByText(/CSV needs columns/)).toBeInTheDocument();
  });
});
