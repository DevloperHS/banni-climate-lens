import { test, expect, Page } from "@playwright/test";

const PAGES: [string, string][] = [
  ["Overview", "Banni Grasslands"], ["Regions", "Regions"], ["Satellite Explorer", "Satellite Explorer"], ["Vegetation", "Vegetation"],
  ["Climate", "Climate"], ["Water Resources", "Water Resources"], ["Spatial Analysis", "Spatial Analysis"], ["Statistical Analysis", "Statistical Analysis"],
  ["Research Reports", "Research Reports"], ["Methodology", "Methodology"], ["Settings", "Settings"],
];

async function nav(page: Page, label: string) {
  await page.getByRole("navigation", { name: "Main navigation" }).getByRole("link", { name: label, exact: true }).click();
}

test.describe.configure({ mode: "serial" });

// Each test gets a fresh browser context; tests after sample generation view the sample source.
test.beforeEach(async ({ page }, info) => {
  if (/^(empty state|settings:|generate synthetic)/.test(info.title)) return;
  await page.addInitScript(() => { localStorage.setItem("gcl.demo", "1"); localStorage.setItem("gcl.source", "sample"); });
});

test("empty state: no data is reported honestly, nothing is faked", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Banni Grasslands" })).toBeVisible();
  await expect(page.getByText("No findings yet")).toBeVisible();
  await expect(page.getByText("Earth Engine is not configured")).toBeVisible();
  await expect(page.getByLabel("Data source")).toHaveCount(0);                                // sample mode is not part of the default UX
  await expect(page.getByTestId("pending-geometry")).toBeVisible();
  await expect(page.getByText("Analysis rectangle area")).toBeVisible();
  await nav(page, "Vegetation");
  await expect(page.getByTestId("empty-state")).toBeVisible();
  await expect(page.getByTestId("empty-state")).toContainText("MODIS NDVI has not been processed");
  await expect(page.getByTestId("chart")).toHaveCount(0);
});

test("settings: Earth Engine status explains setup; job start fails clearly", async ({ page }) => {
  await page.goto("/settings");
  await expect(page.getByText("Project configured:")).toBeVisible();
  await expect(page.getByText(/GCL_EE_PROJECT/).first()).toBeVisible();
  await page.getByRole("button", { name: "Start processing job" }).click();
  await expect(page.getByRole("status")).toContainText(/Earth Engine|not configured|GCL_EE_PROJECT/);
});

test("generate synthetic sample and explore every page", async ({ page }) => {
  await page.goto("/settings");
  await expect(page.getByRole("button", { name: "Generate sample" })).toHaveCount(0);        // hidden until demo mode is enabled
  await page.getByLabel("Enable demonstration mode").check();
  await page.getByRole("button", { name: "Generate sample" }).click();
  await expect(page.getByRole("status")).toContainText("Generated");
  await page.getByRole("button", { name: "Show synthetic sample" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "SYNTHETIC SAMPLE DATA" })).toBeVisible();

  for (const [label, heading] of PAGES) {
    await nav(page, label);
    await expect(page.getByRole("heading", { name: heading, level: label === "Overview" ? 1 : 1 }).first()).toBeVisible();
    await expect(page.getByText("Request failed")).toHaveCount(0);
  }
});

test("overview shows findings computed from data, labelled synthetic", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("Vegetation greenness trend")).toBeVisible();
  await expect(page.getByText(/SYNTHETIC sample data and have no scientific meaning/)).toBeVisible();
});

test("vegetation: charts, trend result block, rainfall-adjusted verdict", async ({ page }) => {
  await page.goto("/vegetation");
  await expect(page.getByTestId("chart").first()).toBeVisible();
  await expect(page.getByTestId("result-block").first()).toContainText("Mann-Kendall");
  await expect(page.getByTestId("adjusted-verdict").first()).toContainText("does not identify the cause");
  await expect(page.getByRole("table", { name: "Regression coefficients" }).first()).toBeVisible();
  // chart download button exists and triggers a download
  const dl = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download chart ndvi_monthly_banni" }).click();
  expect((await dl).suggestedFilename()).toBe("ndvi_monthly_banni.png");
});

test("region/period selection changes analysis scope", async ({ page }) => {
  await page.goto("/regions");
  await page.getByLabel("From", { exact: true }).selectOption("2010");
  await page.getByLabel("To", { exact: true }).selectOption("2020");
  await nav(page, "Vegetation");
  await expect(page.getByTestId("result-block").first()).toContainText("2010-2020");
});

test("satellite explorer: layer controls and pixel inspector", async ({ page }) => {
  await page.goto("/satellite");
  const map = page.getByTestId("map");
  await expect(map).toBeVisible();
  await expect(page.locator(".leaflet-image-layer")).toHaveCount(1);
  await page.getByLabel("Show data layer").uncheck();
  await expect(page.locator(".leaflet-image-layer")).toHaveCount(0);
  await page.getByLabel("Show data layer").check();
  await page.getByLabel("Variable").selectOption("precip");
  await expect(page.getByLabel("Map legend")).toContainText("Precipitation");
  await map.click({ position: { x: 300, y: 200 } });
  await expect(page.getByText("Pixel inspector")).toBeVisible();
  await expect(page.getByText(/Single-pixel trend|outside the raster/).first()).toBeVisible({ timeout: 15_000 });
});

test("spatial analysis: FDR correction summary and downloads", async ({ page }) => {
  await page.goto("/spatial");
  await expect(page.getByText("Pixels tested")).toBeVisible();
  await expect(page.getByText(/Without correction/)).toContainText("after FDR control");
  const href = await page.getByRole("link", { name: /GeoTIFF/ }).getAttribute("href");
  const r = await page.request.get(href!);
  expect(r.status()).toBe(200);
  expect(r.headers()["content-type"]).toContain("image/tiff");
});

test("reports: audience switch and exports", async ({ page }) => {
  await page.goto("/reports");
  const before = await page.getByTestId("finding-text").first().innerText();
  await page.getByLabel("Explain for").selectOption("community");
  await expect(page.getByTestId("finding-text").first()).not.toHaveText(before);
  const pdf = await page.request.get((await page.getByRole("link", { name: /PDF research report/ }).getAttribute("href"))!);
  expect(pdf.status()).toBe(200);
  expect((await pdf.body()).subarray(0, 4).toString()).toBe("%PDF");
});

test("statistics: trend calculator validates and computes", async ({ page }) => {
  await page.goto("/statistics");
  await page.getByLabel("Series values").fill("1, 2, x");
  await page.getByRole("button", { name: "Run tests" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "Enter numbers" })).toBeVisible();
  await page.getByLabel("Series values").fill("1 2 3 4 5 6 7 8 9 10");
  await page.getByRole("button", { name: "Run tests" }).click();
  await expect(page.getByText("▲ increasing").first()).toBeVisible();
});

test("API outage shows a clear error", async ({ page }) => {
  await page.route("**/api/reports/insights**", (r) => r.abort());
  await page.goto("/reports");
  await expect(page.getByText("Backend unreachable")).toBeVisible();
});

test("mobile layout: navigation collapses, no horizontal scroll", async ({ browser }) => {
  const ctx = await browser.newContext({ viewport: { width: 390, height: 800 } });
  const page = await ctx.newPage();
  await page.goto("/vegetation");
  await expect(page.getByRole("navigation", { name: "Main navigation" })).toBeHidden();
  await page.getByRole("button", { name: "Toggle navigation" }).click();
  await expect(page.getByRole("navigation", { name: "Main navigation" })).toBeVisible();
  await page.getByRole("navigation", { name: "Main navigation" }).getByRole("link", { name: "Overview" }).click();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  await ctx.close();
});

test("theme toggle", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Toggle theme" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", /light|dark/);
});

test("statistics: handover reproduction table with honest statuses (synthetic demo data)", async ({ page }) => {
  await page.goto("/statistics");
  const t = page.getByRole("table", { name: "Handover comparison" });
  await expect(t).toBeVisible();
  await expect(page.getByText(/never adjusted to match/).first()).toBeVisible();
  await expect(page.getByText(/platform engine agrees/)).toBeVisible();
  await expect(page.getByTestId("quality")).toContainText("Valid months");
});


// ---------------------------------------------------------------- final-phase features (synthetic demo data)
test("header: availability strip and global period selector", async ({ page }) => {
  await page.goto("/");
  const strip = page.getByTestId("availability");
  await expect(strip).toContainText("NDVI");
  await expect(strip).toContainText("Wells");
  await page.getByLabel("Period start").selectOption("2005");
  await page.getByLabel("Period end").selectOption("2015");
  await page.goto("/vegetation");     // selection is app state; a hard navigation resets it, so re-select after navigation
  await page.getByLabel("Period start").selectOption("2005");
  await page.getByLabel("Period end").selectOption("2015");
  await expect(page.getByTestId("result-block").first()).toContainText("2005-2015");
});

test("vegetation: dry-season analysis and honest Prosopis investigation", async ({ page }) => {
  await page.goto("/vegetation");
  await expect(page.getByText("Dry-season NDVI vs previous-monsoon rainfall").first()).toBeVisible();
  await expect(page.getByText(/previous-monsoon rainfall|prev_monsoon|previous monsoon/i).first()).toBeVisible();
  const st = page.getByTestId("evergreen-status");
  await expect(st).toContainText("EXPLORATORY");
  await expect(st).toContainText("not a species classification");
  await expect(page.getByTestId("ground-truth")).toContainText("No ground-truth labels exist");
  await expect(page.getByTestId("agreement")).toContainText("sign agreement");
  await page.getByLabel("Rann-water mask").selectOption("rann_water");
  await expect(page.getByText(/pixels removed at/)).toBeVisible();
});

test("ground-truth upload validates and reports separability with caveats", async ({ page }) => {
  await page.goto("/vegetation");
  const rows = ["lat,lon,class"];
  for (let i = 0; i < 40; i++) rows.push(`${23.70 + (i % 5) * 0.004},${69.12 + (i % 7) * 0.004},woody`);
  for (let i = 0; i < 40; i++) rows.push(`${23.30 + (i % 5) * 0.004},${69.55 + (i % 7) * 0.004},grass`);
  await page.getByLabel("Labelled points CSV (lat,lon,class)").setInputFiles({ name: "gt.csv", mimeType: "text/csv", buffer: Buffer.from(rows.join("\n")) });
  await page.getByRole("button", { name: "Upload" }).last().click();
  await expect(page.getByTestId("separability")).toContainText("AUC", { timeout: 15000 });
  await expect(page.getByTestId("separability")).toContainText("not a validated species map");
});

test("spatial: water mask, change map and map export", async ({ page }) => {
  await page.goto("/spatial");
  await page.getByLabel("Rann-water mask (JRC)").selectOption("rann_water");
  await expect(page.getByTestId("mask-summary")).toContainText("pixels removed");
  await expect(page.getByTestId("difference")).toContainText("Blue = increase");
  const href = await page.getByRole("link", { name: /Map image/ }).getAttribute("href");
  const r = await page.request.get(href!);
  expect(r.status()).toBe(200);
  expect(r.headers()["content-type"]).toContain("image/png");
});

test("statistics: environmental comparison separates association, prediction and causation", async ({ page }) => {
  await page.goto("/statistics");
  const c = page.getByTestId("compare");
  await expect(c).toBeVisible();
  await expect(page.getByRole("table", { name: "Correlation matrix" })).toBeVisible();
  await expect(page.getByTestId("loo")).toBeVisible();
  await expect(c).toContainText("cannot establish causation");
  await expect(c).toContainText("ASSOCIATION");
  await page.getByLabel("Precipitation").uncheck();
  await page.getByLabel("LST day").uncheck();
  await page.getByLabel("ET", { exact: true }).uncheck();
  await expect(page.getByText("Select at least two variables.")).toBeVisible();
});

test("water: groundwater upload with validation, per-well trends; salinity stays unvalidated; rain-adjusted cyclone", async ({ page }) => {
  await page.goto("/water");
  const rows = ["date,value,well_id"];
  for (const w of ["A", "B"]) for (let y = 2006; y < 2024; y++) for (const m of [1, 5, 8, 11]) rows.push(`${y}-${String(m).padStart(2, "0")}-10,${8 + 0.25 * (y - 2006) + (w === "B" ? 3 : 0) + ((y * m) % 5) * 0.05},${w}`);
  await page.getByLabel("Well readings CSV (date,value[,well_id])").setInputFiles({ name: "gw.csv", mimeType: "text/csv", buffer: Buffer.from(rows.join("\n")) });
  await page.getByRole("button", { name: "Upload" }).last().click();      // the groundwater panel is below the salinity panel
  const wells = page.getByTestId("wells");
  await expect(wells).toContainText("Validation:", { timeout: 15000 });
  await expect(wells).toContainText("2 well(s)");
  await expect(page.getByRole("table", { name: "Per-well trends" })).toContainText("water table deepening");
  await expect(page.getByTestId("salinity-validation")).toContainText("UNVALIDATED");
  await expect(page.getByTestId("event-adjusted")).toContainText("Rainfall-adjusted");
});

test("reports: manifest and PDF with maps from stored data", async ({ page }) => {
  await page.goto("/reports");
  await expect(page.getByTestId("manifest")).toContainText("Reproduction of the research handover");
  const href = await page.getByRole("link", { name: /PDF research report/ }).getAttribute("href");
  const r = await page.request.get(href!);
  expect(r.status()).toBe(200);
  expect(r.headers()["content-type"]).toContain("application/pdf");
  expect((await r.body()).length).toBeGreaterThan(100000);
});

test("settings: token field, pipeline jobs fail clearly, regions page shows geometry honesty", async ({ page }) => {
  await page.goto("/settings");
  await page.getByLabel("API token").fill("abc");
  await page.getByRole("button", { name: "Save for this session" }).click();
  await expect(page.getByText("Token set for this tab.")).toBeVisible();
  await page.getByLabel("API token").fill("");
  await page.getByRole("button", { name: "Save for this session" }).click();
  await page.getByRole("button", { name: "Start processing job" }).click();
  await expect(page.getByRole("status").last()).toContainText(/Earth Engine|GCL_EE_PROJECT/);
  await page.goto("/regions");
  await expect(page.getByTestId("geometry-id")).toContainText("handover_bbox");
  await expect(page.getByText(/Grassland polygon pending/).first()).toBeVisible();
});
