import { ReactElement } from "react";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi } from "vitest";
import { AppStateProvider } from "../state/AppState";
import App from "../App";

export const REGION = {
  id: "banni", name: "Banni Grasslands", description: "Test region", country: "India", state: "Gujarat",
  bbox: { south: 23.2, north: 23.95, west: 68.8, east: 69.95 }, study_period: { start: 2001, end: 2024 },
  reference_area_km2: 2618, reference_area_note: "ref note", computed_bbox_area_km2: 9751.3,
  geometry: { id: "handover_bbox", kind: "bbox", source: "handover", area_km2: 9751.3 },
  pending_geometry: { id: "grassland", needed: "A verified polygon is needed." }, published_area_figures: [],
  events: [], boundary: { type: "Feature", geometry: { type: "Polygon", coordinates: [[[68.8, 23.2], [69.95, 23.2], [69.95, 23.95], [68.8, 23.2]]] }, properties: {} },
};
export const EE = { project_configured: false, auth_mode: null, initialised: false, verified: false, error: null, setup_help: "Set GCL_EE_PROJECT" };

type Handler = (url: URL) => { status?: number; body: unknown } | undefined;

/** Install a fetch mock: first matching handler wins; unmatched calls return a 404 no_data error. */
export function mockApi(handlers: Record<string, Handler | { status?: number; body: unknown }>) {
  const fn = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
    const url = new URL(String(input), "http://localhost");
    const base: Record<string, { status?: number; body: unknown }> = {
      "/api/regions": { body: { items: [REGION], total: 1 } },
      "/api/health/earthengine": { body: EE },
      "/api/datasets/jobs": { body: { items: [], total: 0 } },
    };
    let hit: { status?: number; body: unknown } | undefined;
    for (const [path, h] of [...Object.entries(handlers), ...Object.entries(base)]) {
      if (url.pathname === path) { hit = typeof h === "function" ? h(url) : h; if (hit) break; }
    }
    hit ??= { status: 404, body: { error: { code: "no_data", message: "No series (test)" } } };
    return new Response(JSON.stringify(hit.body), { status: hit.status ?? 200, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

export function renderApp(route = "/", ui?: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 0 } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[route]}>
        <AppStateProvider>{ui ?? <App />}</AppStateProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

export const trendBody = {
  result: {
    mk: { test: "Mann-Kendall", n: 24, s: 100, var_s: 1, tau: 0.36, z: 2.9, p: 0.0037, alpha: 0.05, significant: true, direction: "increasing", slope: 0.0021, slope_ci_low: 0.001, slope_ci_high: 0.003, intercept: 0.2, variance_correction: 1 },
    hr: { test: "Hamed-Rao modified Mann-Kendall", n: 24, s: 100, var_s: 1, tau: 0.36, z: 2.1, p: 0.03, alpha: 0.05, significant: true, direction: "increasing", slope: 0.0021, slope_ci_low: 0.001, slope_ci_high: 0.003, intercept: 0.2, variance_correction: 1.4 },
    recommended: "hr", lag1_autocorr: 0.45, years: [2001, 2002, 2003, 2004], values: [0.2, 0.21, 0.22, 0.23], line: [0.2, 0.21, 0.22, 0.23],
    unit: "dimensionless", unit_short: "NDVI", slope_unit: "NDVI per year", aggregation: "annual", interpretation: "NDVI shows increasing (test).", limitations: "Mixed-pixel index.",
  },
  meta: { region: "banni", variable: "ndvi", kind: "observed", synthetic: false, aggregation: "annual", period: "2001-2024", dataset: { ee_id: "MODIS/061/MOD13Q1", spatial_resolution: "250 m", provider: "NASA" } },
};

