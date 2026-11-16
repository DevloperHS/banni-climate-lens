import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useApp } from "../state/AppState";
import { useApi } from "./ui";
import { EEStatus } from "../lib/api";

export const NAV = [
  { to: "/", label: "Overview", end: true, icon: "overview" },
  { to: "/reports", label: "Research", icon: "reports" },
];

function NavIcon({ name }: { name: string }) {
  switch (name) {
    case "overview":
      return (
        <svg className="w-4 h-4 flex-shrink-0 opacity-80" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <rect x="3" y="3" width="7" height="9" rx="1" />
          <rect x="14" y="3" width="7" height="5" rx="1" />
          <rect x="14" y="12" width="7" height="9" rx="1" />
          <rect x="3" y="16" width="7" height="5" rx="1" />
        </svg>
      );
    case "dashboards":
      return (
        <svg className="w-4 h-4 flex-shrink-0 opacity-80" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <polyline points="3 17 9 11 13 15 21 7" />
          <polyline points="15 7 21 7 21 13" />
        </svg>
      );
    case "regions":
      return (
        <svg className="w-4 h-4 flex-shrink-0 opacity-80" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <polygon points="1 6 1 22 8 18 16 22 23 18 23 2 16 6 8 2 1 6" />
          <line x1="8" y1="2" x2="8" y2="18" />
          <line x1="16" y1="6" x2="16" y2="22" />
        </svg>
      );
    case "satellite":
      return (
        <svg className="w-4 h-4 flex-shrink-0 opacity-80" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="12" cy="12" r="9" />
          <path d="M12 3a15.3 15.3 0 0 1 4 9 15.3 15.3 0 0 1-4 9 15.3 15.3 0 0 1-4-9 15.3 15.3 0 0 1 4-9z" />
          <line x1="3" y1="12" x2="21" y2="12" />
        </svg>
      );
    case "vegetation":
      return (
        <svg className="w-4 h-4 flex-shrink-0 opacity-80" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M12 22v-8m0 0C8.5 14 5 10 5 4c6 0 10 3.5 10 7a6.8 6.8 0 0 1-3 3z" />
          <path d="M12 14c2.5 0 7-1 7-6-4.5 0-7 2.5-7 6z" />
        </svg>
      );
    case "climate":
      return (
        <svg className="w-4 h-4 flex-shrink-0 opacity-80" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M17.5 19H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 1 1 0 9Z" />
        </svg>
      );
    case "water":
      return (
        <svg className="w-4 h-4 flex-shrink-0 opacity-80" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M12 2.69l5.66 5.66a8 8 0 1 1-11.31 0z" />
        </svg>
      );
    case "spatial":
      return (
        <svg className="w-4 h-4 flex-shrink-0 opacity-80" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <rect x="3" y="3" width="18" height="18" rx="2" />
          <path d="M3 9h18M3 15h18M9 3v18M15 3v18" />
        </svg>
      );
    case "statistics":
      return (
        <svg className="w-4 h-4 flex-shrink-0 opacity-80" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <line x1="18" y1="20" x2="18" y2="10" />
          <line x1="12" y1="20" x2="12" y2="4" />
          <line x1="6" y1="20" x2="6" y2="14" />
          <line x1="2" y1="20" x2="22" y2="20" />
        </svg>
      );
    case "reports":
      return (
        <svg className="w-4 h-4 flex-shrink-0 opacity-80" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <polyline points="14 2 14 8 20 8" />
          <line x1="16" y1="13" x2="8" y2="13" />
          <line x1="16" y1="17" x2="8" y2="17" />
          <polyline points="10 9 9 9 8 9" />
        </svg>
      );
    case "methodology":
      return (
        <svg className="w-4 h-4 flex-shrink-0 opacity-80" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M10 2v7.31L4.2 18.5a2 2 0 0 0 1.7 3h12.2a2 2 0 0 0 1.7-3L14 9.31V2" />
          <line x1="8.5" y1="2" x2="15.5" y2="2" />
          <line x1="7" y1="16" x2="17" y2="16" />
        </svg>
      );
    case "settings":
      return (
        <svg className="w-4 h-4 flex-shrink-0 opacity-80" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="12" cy="12" r="3" />
          <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
        </svg>
      );
    default:
      return null;
  }
}

function Logo() {
  return (
    <div className="flex items-center gap-3 px-1 py-1">
      <div className="flex items-center justify-center w-8 h-8 rounded-md bg-[var(--bg-soft)] border border-[var(--border)] shadow-sm">
        <svg width="20" height="20" viewBox="0 0 32 32" aria-hidden="true">
          <circle cx="16" cy="16" r="13" fill="none" stroke="var(--teal)" strokeWidth="2.5" />
          <path d="M3 16h26M16 3c5.5 5.5 5.5 20.5 0 26M16 3c-5.5 5.5-5.5 20.5 0 26" fill="none" stroke="var(--green)" strokeWidth="2" />
          <circle cx="16" cy="16" r="2.5" fill="var(--teal)" />
        </svg>
      </div>
      <div>
        <div className="font-bold tracking-tight text-[15px] leading-tight flex items-center">
          <span style={{ color: "var(--text)" }}>GlobalClimate</span>
          <span style={{ color: "var(--green)" }} className="ml-0.5">Lens</span>
        </div>
        <div className="text-[10px] uppercase font-mono tracking-wider font-semibold opacity-60 text-[var(--muted)]">
          Earth Observation Intelligence
        </div>
      </div>
    </div>
  );
}

export default function Layout() {
  const [open, setOpen] = useState(false);
  const {
    regions,
    region,
    regionId,
    setRegionId,
    source,
    setSource,
    demo,
    theme,
    toggleTheme,
    regionsError,
    start,
    end,
    setPeriod,
  } = useApp();

  const yrs = region
    ? Array.from(
        { length: region.study_period.end - region.study_period.start + 1 },
        (_, i) => region.study_period.start + i
      )
    : [];

  const ee = useApi<EEStatus>("/health/earthengine");

  return (
    <div className="min-h-full lg:grid" style={{ gridTemplateColumns: "245px 1fr" }}>
      {/* ── Refined Sidebar (approx 245px wide) ── */}
      <aside
        className={`${
          open ? "block" : "hidden"
        } lg:flex lg:flex-col p-4 border-r border-[var(--border-subtle)] lg:sticky lg:top-0 lg:h-screen overflow-y-auto z-40 bg-[var(--bg-elev)] transition-all`}
      >
        <div className="mb-6 pb-4 border-b border-[var(--border-subtle)]">
          <Logo />
        </div>

        {/* ── Main Navigation ── */}
        <nav aria-label="Main navigation" className="flex flex-col gap-1 flex-1">
          <div className="text-[10.5px] font-bold uppercase tracking-wider px-3 pt-1 pb-1.5 text-[var(--muted)] opacity-70">
            Domain
          </div>
          <NavLink
            to="/"
            end
            className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
            onClick={() => setOpen(false)}
          >
            <NavIcon name="overview" />
            <span>Overview</span>
          </NavLink>
          <NavLink
            to="/reports"
            className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
            onClick={() => setOpen(false)}
          >
            <NavIcon name="reports" />
            <span>Research</span>
          </NavLink>
        </nav>

        {/* ── Active Context Card in Sidebar ── */}
        <div className="mt-auto pt-4 border-t border-[var(--border-subtle)]">
          <div className="p-3 rounded-lg bg-[var(--bg-soft)] border border-[var(--border-subtle)] text-xs space-y-1.5">
            <div className="flex items-center justify-between font-medium">
              <span className="truncate text-[var(--text)] font-semibold">{region?.name ?? "Banni Grasslands"}</span>
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-[var(--bg-elev)] border border-[var(--border)] text-[var(--teal)]">
                Y{start}–Y{end}
              </span>
            </div>
            <div className="text-[11px] flex items-center justify-between text-[var(--muted)]">
              <span>Engine Status:</span>
              <span className="font-semibold flex items-center gap-1.5">
                <span
                  className="w-1.5 h-1.5 rounded-full"
                  style={{
                    background: ee.data?.verified
                      ? "var(--green)"
                      : ee.data?.project_configured
                      ? "var(--amber)"
                      : "var(--red)",
                  }}
                />
                <span className="font-mono text-[10.5px]">
                  {ee.data?.verified ? "Connected" : ee.data?.project_configured ? "Unverified" : "Offline"}
                </span>
              </span>
            </div>
          </div>
        </div>
      </aside>

      {/* ── Main Canvas with spacious 24–32px padding ── */}
      <div className="min-w-0 flex flex-col bg-[var(--bg)]">
        {/* Clean, Non-Cluttered Top Toolbar */}
        <header className="flex flex-wrap items-center gap-3 px-6 lg:px-8 py-3 border-b border-[var(--border-subtle)] sticky top-0 z-[1000] bg-[var(--bg-elev)] backdrop-blur-md">
          <button
            className="btn lg:hidden"
            aria-label="Toggle navigation"
            aria-expanded={open}
            onClick={() => setOpen(!open)}
          >
            ☰
          </button>
          <div className="lg:hidden">
            <Logo />
          </div>

          <div className="flex items-center gap-3 ml-auto flex-wrap text-xs">
            {/* Temporal Window Controls */}
            <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-[var(--bg-soft)] border border-[var(--border)]">
              <label className="text-[11px] font-bold uppercase tracking-wider text-[var(--muted)]" htmlFor="period-start">
                Period
              </label>
              <select
                id="period-start"
                className="field !py-0.5 !px-1.5 text-xs font-mono"
                value={start}
                onChange={(e) => setPeriod(Number(e.target.value), end)}
                aria-label="Period start"
              >
                {yrs.map((y) => (
                  <option key={y}>{y}</option>
                ))}
              </select>
              <span className="text-[var(--muted)] font-mono">–</span>
              <select
                className="field !py-0.5 !px-1.5 text-xs font-mono"
                value={end}
                onChange={(e) => setPeriod(start, Number(e.target.value))}
                aria-label="Period end"
              >
                {yrs.map((y) => (
                  <option key={y}>{y}</option>
                ))}
              </select>
            </div>

            {/* Geographic Focus Selector */}
            <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-[var(--bg-soft)] border border-[var(--border)]">
              <label className="text-[11px] font-bold uppercase tracking-wider text-[var(--muted)]" htmlFor="region-select">
                Region
              </label>
              <select
                id="region-select"
                className="field !py-0.5 !px-2 text-xs font-medium"
                value={regionId}
                onChange={(e) => setRegionId(e.target.value)}
                aria-label="Region"
              >
                {regions.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.name}
                  </option>
                ))}
              </select>
            </div>

            {/* Demo Source Selector (When Demo mode is active) */}
            {demo && (
              <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-[var(--bg-soft)] border border-[var(--border)]">
                <label className="text-[11px] font-bold uppercase tracking-wider text-[var(--muted)]" htmlFor="source-select">
                  Data
                </label>
                <select
                  id="source-select"
                  className="field !py-0.5 !px-2 text-xs"
                  value={source}
                  onChange={(e) => setSource(e.target.value as "processed" | "sample")}
                  aria-label="Data source"
                >
                  <option value="processed">Processed (observed)</option>
                  <option value="sample">Synthetic sample (demo)</option>
                </select>
              </div>
            )}

            {/* Theme Toggle Button */}
            <button
              className="btn !py-1 !px-2.5 text-xs font-medium flex items-center gap-1.5"
              onClick={toggleTheme}
              aria-label="Toggle theme"
            >
              {theme === "dark" ? (
                <>
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                    <circle cx="12" cy="12" r="4" />
                    <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" />
                  </svg>
                  <span>Light</span>
                </>
              ) : (
                <>
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                    <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
                  </svg>
                  <span>Dark</span>
                </>
              )}
            </button>
          </div>
        </header>

        {/* Global Synthetic Data Warning Bar */}
        {source === "sample" && (
          <div
            role="alert"
            className="px-6 py-2.5 text-xs font-semibold flex items-center gap-2 border-b border-[var(--border)]"
            style={{
              background: "color-mix(in srgb, var(--amber) 15%, transparent)",
              color: "var(--amber)",
            }}
          >
            <span className="px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider bg-[var(--amber)] text-black">
              DEMO
            </span>
            SYNTHETIC SAMPLE DATA: generated by a toy model for software testing. Nothing shown is a satellite observation or a scientific result.
          </div>
        )}

        {regionsError && (
          <div role="alert" className="p-4 text-sm text-[var(--red)]">
            {regionsError.message}
          </div>
        )}

        {/* ── Page Content Container with spacious 24–32px padding ── */}
        <main className="p-6 lg:p-8 space-y-8 max-w-[1536px] w-full">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
