export class ApiError extends Error {
  code: string;
  status: number;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

export type Source = "processed" | "sample";
type Params = Record<string, string | number | boolean | null | undefined>;

export function qs(params?: Params): string {
  const u = new URLSearchParams();
  Object.entries(params ?? {}).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") u.set(k, String(v));
  });
  const s = u.toString();
  return s ? `?${s}` : "";
}

async function parse(res: Response) {
  if (res.ok) return res;
  let code = "http_error";
  let message = `Request failed (${res.status})`;
  try {
    const j = await res.json();
    if (j?.error) {
      code = j.error.code;
      message = j.error.message;
    }
  } catch {
    /* non-JSON error body */
  }
  throw new ApiError(res.status, code, message);
}

export async function apiGet<T>(path: string, params?: Params): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api${path}${qs(params)}`);
  } catch {
    throw new ApiError(0, "network", "Cannot reach the GlobalClimateLens API. Is the backend running on port 8000?");
  }
  return (await parse(res)).json();
}

const TOKEN_KEY = "gcl.token";
/** Optional API token for state-changing calls. Kept in sessionStorage only (cleared when the tab closes). */
export const getToken = (): string => { try { return sessionStorage.getItem(TOKEN_KEY) ?? ""; } catch { return ""; } };
export const setToken = (t: string) => { try { t ? sessionStorage.setItem(TOKEN_KEY, t) : sessionStorage.removeItem(TOKEN_KEY); } catch { /* storage unavailable */ } };

export async function apiSend<T>(method: string, path: string, body?: unknown, form?: FormData): Promise<T> {
  let res: Response;
  try {
    const headers: Record<string, string> = {};
    if (body) headers["Content-Type"] = "application/json";
    if (getToken()) headers["Authorization"] = `Bearer ${getToken()}`;
    res = await fetch(`/api${path}`, {
      method,
      headers,
      body: form ?? (body ? JSON.stringify(body) : undefined),
    });
  } catch {
    throw new ApiError(0, "network", "Cannot reach the GlobalClimateLens API. Is the backend running on port 8000?");
  }
  return (await parse(res)).json();
}

export const downloadUrl = (path: string, params?: Params) => `/api${path}${qs(params)}`;

// ---- response types
export interface Meta {
  region: string; variable?: string; kind: string; synthetic: boolean; disclaimer?: string | null;
  dataset?: Record<string, string | null>; aggregation?: string; period?: string; method?: string;
}
export interface Wrapped<T> { result: T; meta: Meta }
export interface Region {
  id: string; name: string; description: string; country: string; state: string;
  bbox: { south: number; north: number; west: number; east: number };
  study_period: { start: number; end: number }; reference_area_km2: number; reference_area_note: string;
  computed_bbox_area_km2: number;
  geometry: { id: string; kind: string; source: string; area_km2: number };
  pending_geometry?: { id: string; needed: string } | null;
  published_area_figures?: { km2: number; source: string; verified: string }[];
  events: { id: string; name: string; date: string; note: string }[];
  boundary: GeoJSON.Feature;
}
export interface DatasetItem {
  key: string; label: string; group: string; ee_id: string | null; provider: string; variable: string;
  spatial_resolution: string; temporal_resolution: string; unit: string; scale_factor: string; quality_filter: string;
  limitations: string; available: boolean; kind: string | null; retrieval_date: string | null;
  processing_period: string | null; n_months: number; rasters: string[];
}
export interface EEStatus { project_configured: boolean; auth_mode: string | null; initialised: boolean; verified: boolean; error: string | null; setup_help: string | null }
export interface SeriesResult { x: (string | number)[]; values: (number | null)[]; frequency: string; unit: string; label: string }
export interface TrendTest {
  test: string; n: number; s: number; z: number; p: number; tau: number; alpha: number; significant: boolean; direction: string;
  slope: number; slope_ci_low: number; slope_ci_high: number; intercept: number; variance_correction: number;
}
export interface TrendResult {
  mk: TrendTest; hr: TrendTest; recommended: "mk" | "hr"; lag1_autocorr: number | null; warnings?: string[];
  years: number[]; values: number[]; line: number[]; unit: string; unit_short: string; slope_unit: string; aggregation: string;
  interpretation: string; limitations: string;
}
export interface Coef { name: string; coef: number; se: number; t: number; p: number; ci_low: number; ci_high: number; hac_p: number }
export interface OLS {
  n: number; r2: number; adj_r2: number; f_p: number; coefficients: Coef[]; residuals: number[]; fitted: number[];
  diagnostics: { durbin_watson: number; ljung_box_p: number | null; shapiro_p: number | null; breusch_pagan_p: number | null; outlier_indices: number[] };
}
export interface Adjusted {
  n: number; years: number[]; ndvi: number[]; rainfall: number[]; predicted: number[]; residuals: number[];
  regression: OLS; ndvi_trend: { mk: TrendTest; hr: TrendTest; recommended: "mk" | "hr" };
  rainfall_trend: { mk: TrendTest; hr: TrendTest; recommended: "mk" | "hr" };
  residual_trend: { mk: TrendTest; hr: TrendTest; recommended: "mk" | "hr"; lag1_autocorr: number | null };
  sensitivity: { name: string; n: number; direction: string; [k: string]: unknown }[];
  caveats: string[]; verdict: { text: string; residual_direction: string; sensitivity_agreeing: number; sensitivity_total: number };
  response_label: string; unit: string; rain_unit: string; rain_season?: string;
}

export interface RepRow {
  id: string; label: string; page: number; unit: string; note?: string | null;
  reported: { value?: number; direction?: string; p?: number; slope?: number; z?: number };
  computed: number | { direction: string; p: number; slope: number; z: number } | null;
  status: "reproduced" | "consistent" | "not reproduced" | "not available";
  checks: Record<string, boolean | number>;
}
export interface Reproduction {
  rows: RepRow[]; counts: Record<string, number>; notes: string[]; reference_source: string; reference_geometry: string;
  engine_cross_check: { agree: boolean; p_engine: number; p_pymannkendall: number };
  protocol_differences: { item: string; handover: string; platform_default: string; status: string }[];
  colab: { n_years: number; regression: { r2: number; rain_coef: number; rain_p: number }; verdict_rule: string; verdict_note: string };
}
export interface Quality {
  key: string; expected_months: number; valid_months: number; missing_months: number; missing_list: string[]; completeness_pct: number;
  valid_by_year: Record<string, number>; stats: { min: number | null; max: number | null; mean: number | null; sd: number | null };
  plausible_range: number[]; out_of_range: number; flags: string[]; raw_files: string[]; unit: string; ee_id: string | null; retrieval_date: string | null;
  geometry?: { id: string; kind: string; area_km2: number; source: string };
}

export interface Job {
  id: string; status: string; created: string; error: string | null; cancel_requested?: boolean;
  spec: { region: string; start: number; end: number; tasks: unknown[] };
  progress: { done: number; total: number; percent: number };
  tasks: { id: number; label: string; status: string; attempts: number; error: string | null; detail?: unknown }[];
}
export interface CompareResult {
  n: number; years: number[]; variables: string[]; detrended: boolean; labels: Record<string, string>; units: Record<string, string>; aggregation: string;
  pearson: number[][]; pearson_p: number[][]; spearman: number[][];
  pairs: { a: string; b: string; pearson_r: number; pearson_p: number; pearson_p_bh: number; significant_bh: boolean; spearman_rho: number }[];
  zscores: Record<string, number[]>; anomaly_years: { year: number; variables: string[]; coincident: boolean }[];
  association_note: string; statement: string; causation_note?: string; lag_note?: string;
  regression?: { response: string; predictors: string[]; r2: number; adj_r2: number; coefficients: Coef[]; vif?: Record<string, number>; collinearity_warning?: boolean;
    diagnostics: OLS["diagnostics"]; residuals: number[] };
  prediction?: { r2_in_sample: number; r2_loo_cv: number; note: string };
  partial_correlations?: { variable: string; r: number; p: number | null; controls: string[] }[];
  lagged?: { variable: string; lag_years: number; r: number; p: number }[];
}

export interface DashCard {
  key: string; aggregation: string; role: string; label: string; dataset: string; unit: string; available: boolean; reason?: string | null;
  derived?: boolean; test?: string; direction?: string | null; slope?: number; slope_unit?: string; ci?: [number, number]; p?: number;
  significant?: boolean; n?: number; period?: string; synthetic?: boolean; r2_rain?: number; verdict?: string;
  year_term?: { coef: number; p: number; hac_p: number } | null;
  series?: { years: number[]; values?: number[]; line?: number[]; observed?: number[]; predicted?: number[]; rainfall?: number[] };
  wells?: { well_id: string; lat: number | null; lon: number | null; status?: string; direction?: string; p?: number; meaning?: string }[];
}
export interface DashLayer {
  variable: string; season: string; label: string; unit: string; cmap: string; years: number[];
  bounds: { south: number; north: number; west: number; east: number }; vmin: number | null; vmax: number | null; kind: string;
}
export interface Dashboard {
  id: "rain_green" | "water_heat" | "where_changed"; title: string; question: string; cards: DashCard[]; derived: DashCard[];
  yearly: { years: number[]; columns: Record<string, (number | null)[]> }; layers: DashLayer[]; limits: string[];
  sources: { key: string; label: string; dataset: string; provider: string; url: string; resolution: string }[];
  landcover?: { key: string; label: string; years: number[]; values: number[] }[];
  checks?: SensorIndexChecks | { available: false; reason: string };
}
export interface CheckTrend { direction: string; slope: number; p: number; significant: boolean; ci: [number, number]; n?: number }
export interface CheckRow {
  key: string; label: string; role: string; dataset: string; available: boolean; reason?: string;
  synthetic?: boolean; period?: string; n?: number; raw_trend?: CheckTrend; residual_trend?: CheckTrend; r2_rain?: number;
  year_term?: { coef: number; p: number; hac_p: number } | null; slope_unit?: string;
}
export interface SensorIndexChecks {
  period: string; method: string; note: string;
  seasons: { season: string; label: string; rain_control: string; rows: CheckRow[];
    agreement: { status: "agree" | "partial" | "disagree" | "unavailable"; headline?: string; text: string; agree?: string[]; differ?: string[]; missing?: string[] } }[];
  terra_aqua_monsoon: { n: number; pearson_r: number | null; mean_difference_aqua_minus_terra: number | null } | null;
}
