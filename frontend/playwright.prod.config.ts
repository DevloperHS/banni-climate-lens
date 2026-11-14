import { defineConfig, devices } from "@playwright/test";
import path from "node:path";
import os from "node:os";
import fs from "node:fs";
import { fileURLToPath } from "node:url";

// Production-mode check: the API serves the BUILT frontend (no Vite), exactly as deployed, with a token and the CSP.
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "gcl_prod_"));
const py = path.resolve(__dirname, "../.venv/Scripts/python.exe");

export default defineConfig({
  testDir: "./e2e-prod",
  workers: 1,
  timeout: 60_000,
  reporter: [["list"]],
  use: { baseURL: "http://127.0.0.1:8002" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: `"${py}" -m uvicorn app.main:app --port 8002`,
    cwd: path.resolve(__dirname, "../backend"),
    url: "http://127.0.0.1:8002/api/health",
    env: { GCL_DATA_DIR: dataDir, GCL_STATIC_DIR: path.resolve(__dirname, "dist"), GCL_EE_PROJECT: "", GCL_API_TOKEN: "prod-test-token", GCL_RATE_LIMIT_PER_MIN: "0" },
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
