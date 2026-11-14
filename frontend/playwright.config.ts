import { defineConfig, devices } from "@playwright/test";
import path from "node:path";
import os from "node:os";
import fs from "node:fs";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Isolated backend (port 8001) with a throw-away data dir so e2e never touches real data.
const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "gcl_e2e_"));
const py = path.resolve(__dirname, "../.venv/Scripts/python.exe");

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  reporter: [["list"]],
  use: { baseURL: "http://127.0.0.1:5174", trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: `"${py}" -m uvicorn app.main:app --port 8001`,
      cwd: path.resolve(__dirname, "../backend"),
      url: "http://127.0.0.1:8001/api/health",
      env: { GCL_DATA_DIR: dataDir, GCL_EE_PROJECT: "" },
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: "npx vite --host 127.0.0.1 --port 5174 --strictPort",
      env: { API_TARGET: "http://127.0.0.1:8001" },
      url: "http://127.0.0.1:5174",
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
});
