import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { PageHeader, Panel, Q, SectionHeader, useApi } from "../components/ui";
import { JobsPanel } from "../components/panels2";
import { ApiError, apiSend, DatasetItem, EEStatus, getToken, setToken } from "../lib/api";
import { useApp } from "../state/AppState";

interface Job {
  id: string;
  status: string;
  created: string;
  error: string | null;
  spec: { region: string; start: number; end: number };
  progress: { task: string; status: string; error?: string }[];
}

const SERIES = [
  "ndvi",
  "precip",
  "lst_day",
  "lst_night",
  "et",
  "sm_surface",
  "sm_root",
  "water_extent",
  "ndvi_landsat",
  "ndvi_qa",
  "ndvi_aqua",
  "evi",
  "ndvi_nowater",
  "salinity_index",
  "water_extent_mndwi",
];

const STACKS: [string, string][] = [
  ["ndvi", "annual"],
  ["ndvi", "monsoon"],
  ["ndvi", "summer"],
  ["ndvi", "peak"],
  ["precip", "monsoon"],
  ["lst_day", "summer"],
  ["et", "annual"],
  ["sm_root", "annual"],
  ["ndvi_landsat", "peak"],
  ["salinity_index", "summer"],
  ["water_occurrence", "static"],
];

export default function Settings() {
  const { regionId, region, source, setSource, demo, setDemo, theme, toggleTheme } = useApp();
  const qc = useQueryClient();
  const [probe, setProbe] = useState(false);
  const ee = useApi<EEStatus>("/health/earthengine", { probe });
  const ds = useApi<{ items: DatasetItem[] }>("/datasets", { region: regionId, source });
  const [sel, setSel] = useState<Set<string>>(new Set(["ndvi", "precip"]));
  const [stk, setStk] = useState<Set<string>>(new Set());
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [tok, setTok] = useState(getToken());

  const act = async (fn: () => Promise<string>) => {
    setBusy(true);
    setMsg(null);
    try {
      setMsg({ ok: true, text: await fn() });
      qc.invalidateQueries();
    } catch (e) {
      setMsg({ ok: false, text: (e as ApiError).message });
    } finally {
      setBusy(false);
    }
  };

  const toggle = (s: Set<string>, k: string, set: (n: Set<string>) => void) => {
    const n = new Set(s);
    n.has(k) ? n.delete(k) : n.add(k);
    set(n);
  };

  const run = () =>
    act(async () => {
      const tasks = [
        ...[...sel].map((key) => ({ type: "series", key })),
        ...[...stk].map((k) => {
          const [key, season] = k.split(":");
          return { type: "stack", key, season };
        }),
      ];
      if (!tasks.length) throw new ApiError(0, "x", "Select at least one dataset.");
      const j = await apiSend<Job>("POST", "/datasets/jobs", {
        region: regionId,
        start: region?.study_period.start,
        end: region?.study_period.end,
        tasks,
      });
      return `Job ${j.id} queued with ${tasks.length} task(s).`;
    });

  return (
    <>
      <PageHeader
        title="Settings"
        subtitle="Configure backend connectivity, manage Google Earth Engine authentication, control synthetic demonstration mode, and schedule data extraction jobs."
        badges={
          <div className="flex items-center gap-2">
            <span className="badge font-mono text-[11px] text-[var(--teal)] border-[var(--border-hi)]">
              Pipeline Control
            </span>
            <span className="badge font-mono text-[11px]">{theme.toUpperCase()} THEME</span>
          </div>
        }
      />

      <div className="grid gap-5 xl:grid-cols-2">
        {/* Appearance & Demonstration Mode */}
        <Panel title="Platform Appearance & Demonstration Mode" subtitle="UI theme and mock data controls">
          <div className="space-y-4 text-xs sm:text-sm">
            <div className="flex items-center justify-between p-3 rounded-lg bg-[var(--bg-soft)] border border-[var(--border)]">
              <div>
                <div className="font-semibold text-[var(--text)]">Visual Color Theme</div>
                <div className="text-xs text-[var(--muted)]">Active mode: {theme === "dark" ? "Dark Scientific Navy" : "Light High-Contrast"}</div>
              </div>
              <button className="btn text-xs font-medium" onClick={toggleTheme}>
                {theme === "dark" ? "☀ Switch to Light Mode" : "☾ Switch to Dark Mode"}
              </button>
            </div>

            <div className="p-3.5 rounded-lg bg-[var(--bg-soft)] border border-[var(--border)] space-y-2.5">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-[var(--text)]">Demonstration Mode (Synthetic Toy Data)</span>
                <span className={`badge ${demo ? "badge-warn font-semibold" : ""}`}>
                  {demo ? "ENABLED" : "OFF"}
                </span>
              </div>
              <p className="text-xs text-[var(--muted)] leading-relaxed">
                When enabled, GlobalClimateLens allows generating synthetic mathematical sample series so researchers can evaluate the interface without Earth Engine credentials. Synthetic data are kept strictly segregated and badged everywhere.
              </p>
              <label className="flex items-center gap-2 text-xs font-medium text-[var(--text-2)] cursor-pointer select-none pt-1">
                <input
                  type="checkbox"
                  checked={demo}
                  onChange={(e) => setDemo(e.target.checked)}
                  className="rounded accent-[var(--accent)]"
                />
                Enable demonstration mode
              </label>

              {demo && (
                <div className="pt-2 flex gap-2 flex-wrap border-t border-[var(--border)]">
                  <button
                    className="btn text-xs"
                    disabled={busy}
                    onClick={() =>
                      act(async () => {
                        const r = await apiSend<{ series: number; rasters: number }>(
                          "POST",
                          `/datasets/sample?region=${regionId}`
                        );
                        return `Generated ${r.series} synthetic series and ${r.rasters} rasters.`;
                      })
                    }
                  >
                    Generate sample
                  </button>
                  <button
                    className="btn text-xs"
                    disabled={busy}
                    onClick={() =>
                      act(async () => {
                        const r = await apiSend<{ removed_files: number }>("DELETE", "/datasets/sample");
                        return `Removed ${r.removed_files} sample files.`;
                      })
                    }
                  >
                    Delete sample
                  </button>
                  <button
                    className={`btn text-xs ${source === "sample" ? "btn-primary font-semibold" : ""}`}
                    onClick={() => setSource(source === "sample" ? "processed" : "sample")}
                  >
                    {source === "sample" ? "Show processed data" : "Show synthetic sample"}
                  </button>
                </div>
              )}
            </div>

            {msg && (
              <div
                role="status"
                className="p-3 rounded-lg text-xs font-medium border"
                style={{
                  borderColor: msg.ok ? "var(--green)" : "var(--red)",
                  color: msg.ok ? "var(--green)" : "var(--red)",
                  background: "var(--bg-soft)",
                }}
              >
                {msg.text}
              </div>
            )}
          </div>
        </Panel>

        {/* Earth Engine Backend Connection */}
        <Panel
          title="Google Earth Engine Gateway"
          subtitle="Direct API connection status and authentication"
          actions={
            <button
              className="btn text-xs"
              onClick={() => setProbe(true)}
              disabled={probe && ee.isFetching}
            >
              {ee.isFetching ? "Probing API…" : "Probe Connection"}
            </button>
          }
        >
          <Q q={ee} h={90}>
            {(s) => (
              <div className="text-xs sm:text-sm space-y-3">
                <div className="grid gap-2.5 sm:grid-cols-3">
                  <div className="p-3 rounded-lg bg-[var(--bg-soft)] border border-[var(--border)]">
                    <div className="muted text-[11px]">Project configured:</div>
                    <div className="mt-1 font-semibold">
                      {s.project_configured ? (
                        <span className="badge badge-ok">Configured</span>
                      ) : (
                        <span className="badge badge-bad">Missing</span>
                      )}
                    </div>
                  </div>
                  <div className="p-3 rounded-lg bg-[var(--bg-soft)] border border-[var(--border)]">
                    <div className="muted text-[11px]">Auth Mode</div>
                    <div className="mt-1 font-mono font-semibold text-[var(--text)]">{s.auth_mode ?? "None"}</div>
                  </div>
                  <div className="p-3 rounded-lg bg-[var(--bg-soft)] border border-[var(--border)]">
                    <div className="muted text-[11px]">Handshake Status</div>
                    <div className="mt-1 font-semibold">
                      {s.verified ? (
                        <span className="badge badge-ok">Verified</span>
                      ) : (
                        <span className="badge badge-warn">Unverified</span>
                      )}
                    </div>
                  </div>
                </div>

                {s.error && (
                  <div role="alert" className="p-3 rounded-lg bg-[var(--bg-soft)] text-xs text-[var(--red)] border border-[var(--red)] font-mono">
                    {s.error}
                  </div>
                )}
                {s.setup_help && (
                  <p className="text-xs text-[var(--text-2)] bg-[var(--bg-soft)] p-3 rounded-lg border border-[var(--border)] leading-relaxed">
                    {s.setup_help}
                  </p>
                )}
                <p className="muted text-[11px] leading-relaxed">
                  Service credentials and API tokens are securely resolved from backend server environment variables (.env). Credentials never traverse browser networks or leak to client sessions.
                </p>
              </div>
            )}
          </Q>
        </Panel>
      </div>

      {/* API Access Token */}
      <Panel
        title="Session API Authorization Token"
        subtitle="Required only if backend was initialized with GCL_API_TOKEN. Stored transiently in this tab's sessionStorage."
      >
        <div className="flex flex-wrap gap-2.5 items-end max-w-xl">
          <label className="text-xs text-[var(--muted)] font-medium flex flex-col gap-1 flex-1">
            Bearer Token
            <input
              type="password"
              className="field font-mono"
              value={tok}
              onChange={(e) => setTok(e.target.value)}
              aria-label="API token"
              autoComplete="off"
              placeholder="Enter server access token…"
            />
          </label>
          <button
            className="btn btn-primary text-xs"
            onClick={() => {
              setToken(tok);
              setMsg({ ok: true, text: "Token set for this tab." });
            }}
          >
            Save for this session
          </button>
        </div>
      </Panel>

      {/* Batch Processing Tasks */}
      <SectionHeader
        title="Earth Engine Extraction Pipeline"
        description="Dispatch background tasks to extract spatial timeseries and construct multi-annual raster stacks."
      />

      <Panel
        title="Execute Data Processing Job"
        subtitle={`Active study area: ${region?.name} (${region?.study_period.start}–${region?.study_period.end})`}
      >
        <div className="grid gap-5 md:grid-cols-2">
          <fieldset className="p-3.5 rounded-lg bg-[var(--bg-soft)] border border-[var(--border)]">
            <legend className="text-xs font-bold uppercase tracking-wider text-[var(--text)] px-1">
              Time-Series Extraction
            </legend>
            <div className="space-y-1.5 mt-2">
              {SERIES.map((k) => (
                <label key={k} className="flex items-center gap-2 text-xs text-[var(--text-2)] cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={sel.has(k)}
                    onChange={() => toggle(sel, k, setSel)}
                    className="rounded accent-[var(--accent)]"
                  />
                  <span>{ds.data?.items.find((i) => i.key === k)?.label ?? k}</span>
                </label>
              ))}
            </div>
          </fieldset>

          <fieldset className="p-3.5 rounded-lg bg-[var(--bg-soft)] border border-[var(--border)]">
            <legend className="text-xs font-bold uppercase tracking-wider text-[var(--text)] px-1">
              Spatial Raster Stacks (Maps &amp; Pixel Trends)
            </legend>
            <div className="space-y-1.5 mt-2">
              {STACKS.map(([k, s]) => (
                <label key={k + s} className="flex items-center gap-2 text-xs text-[var(--text-2)] cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={stk.has(`${k}:${s}`)}
                    onChange={() => toggle(stk, `${k}:${s}`, setStk)}
                    className="rounded accent-[var(--accent)]"
                  />
                  <span className="font-mono">{k}</span> · <span>{s}</span>
                </label>
              ))}
            </div>
          </fieldset>
        </div>

        <div className="mt-4 flex items-center gap-3">
          <button className="btn btn-primary text-xs" onClick={run} disabled={busy}>
            {busy ? "Scheduling…" : "Start processing job"}
          </button>
          <span className="muted text-xs">
            {sel.size + stk.size} task(s) selected
          </span>
        </div>

        <p className="muted text-[11px] mt-2">
          Jobs require authenticated Earth Engine access. Long-running raster computations execute asynchronously; real-time task progress and stderr logs appear below.
        </p>

        <div className="mt-6 pt-4 border-t border-[var(--border)]">
          <h3 className="text-sm font-semibold text-[var(--text)] mb-3">Background Job Monitor</h3>
          <JobsPanel />
        </div>
      </Panel>
    </>
  );
}
