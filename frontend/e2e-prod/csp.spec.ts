import { test, expect } from "@playwright/test";

const TOKEN = "prod-test-token";

test("built app runs under the strict CSP with no violations (maps, charts, downloads, uploads)", async ({ page }) => {
  const violations: string[] = [];
  page.on("console", (m) => { if (/Content Security Policy|Refused to/i.test(m.text())) violations.push(m.text()); });
  await page.addInitScript(() => {
    document.addEventListener("securitypolicyviolation", (e) => console.error("CSPV " + e.violatedDirective + " " + e.blockedURI));
    localStorage.setItem("gcl.demo", "1"); localStorage.setItem("gcl.source", "sample");
  });
  const r = await page.request.post("/api/datasets/sample?region=banni", { headers: { Authorization: `Bearer ${TOKEN}` } });
  expect(r.status()).toBe(200);

  const resp = await page.goto("/");
  const csp = resp!.headers()["content-security-policy"];
  expect(csp).toContain("script-src 'self'");
  expect(csp).not.toMatch(/script-src[^;]*unsafe-(inline|eval)/);
  expect(csp).toContain("frame-ancestors 'none'");

  for (const p of ["/vegetation", "/satellite", "/spatial", "/statistics", "/water", "/reports", "/settings"]) {
    await page.goto(p);
    await page.waitForTimeout(1500);
  }
  await page.goto("/satellite");
  await expect(page.locator(".leaflet-image-layer")).toHaveCount(1);                       // API raster overlay (self)
  await expect(page.locator(".leaflet-tile-pane img").first()).toBeVisible({ timeout: 15000 }).catch(() => {});  // tiles need internet; not required to pass
  await page.goto("/vegetation");
  const dl = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download chart ndvi_monthly_banni" }).click();     // SVG -> canvas -> PNG under the CSP
  expect((await dl).suggestedFilename()).toBe("ndvi_monthly_banni.png");
  expect(violations.filter((v) => !/tile\.openstreetmap|arcgisonline/.test(v))).toEqual([]);
});

test("token is required for writes and nothing leaks into the page", async ({ page, request }) => {
  expect((await request.post("/api/datasets/sample?region=banni")).status()).toBe(401);
  await page.goto("/settings");
  await expect(page.getByLabel("API token")).toHaveAttribute("type", "password");
  expect(await page.content()).not.toContain(TOKEN);
});

test("health endpoint answers (the limiter is disabled in this config; its 429 behaviour is covered by backend unit tests)", async ({ request }) => {
  // limiter is disabled in this config (GCL_RATE_LIMIT_PER_MIN=0): behaviour is unit-tested in the backend suite
  expect((await request.get("/api/health")).status()).toBe(200);
});
