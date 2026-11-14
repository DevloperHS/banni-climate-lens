import { ReactNode } from "react";
import { UseQueryResult, useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ApiError, apiGet, DatasetItem, Meta, TrendTest } from "../lib/api";
import { useApp } from "../state/AppState";

/* ------------------------------------------------------------------ API Scope & Query Hooks */

export function useApi<T>(
  path: string,
  params: Record<string, string | number | boolean | null | undefined> = {},
  enabled = true
) {
  return useQuery<T, ApiError>({
    queryKey: [path, params],
    queryFn: () => apiGet<T>(path, params),
    enabled,
    retry: (n, e) => (e.status >= 500 || e.status === 0 ? n < 1 : false),
  });
}

export function useScope() {
  const { regionId, source, start, end } = useApp();
  return { region: regionId, source, start, end };
}

/* ------------------------------------------------------------------ Design System: PageHeader */

export function PageHeader({
  title,
  subtitle,
  badges,
  actions,
}: {
  title: string;
  subtitle?: string;
  badges?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="pb-2 border-b border-[var(--border-subtle)] flex flex-col md:flex-row md:items-end justify-between gap-4">
      <div>
        <div className="flex items-center gap-3 flex-wrap">
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-[var(--text)]">
            {title}
          </h1>
          {badges}
        </div>
        {subtitle && (
          <p className="mt-1.5 text-sm text-[var(--muted)] max-w-3xl leading-relaxed">
            {subtitle}
          </p>
        )}
      </div>
      {actions && (
        <div className="flex items-center gap-2 flex-wrap flex-shrink-0">
          {actions}
        </div>
      )}
    </header>
  );
}

/* ------------------------------------------------------------------ Design System: SectionHeader */

export function SectionHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="pt-4 pb-1 flex flex-col sm:flex-row sm:items-baseline justify-between gap-2 border-b border-[var(--border-subtle)]">
      <div>
        <h2 className="text-base sm:text-lg font-semibold tracking-tight text-[var(--text)] flex items-center gap-2">
          <span className="w-1.5 h-3.5 rounded-full bg-[var(--accent)]" />
          {title}
        </h2>
        {description && (
          <p className="text-xs text-[var(--muted)] mt-0.5 ml-3.5 max-w-2xl leading-relaxed">
            {description}
          </p>
        )}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}

/* ------------------------------------------------------------------ Design System: MetricCard */

export function MetricCard({
  label,
  value,
  hint,
  tone,
  unit,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: "ok" | "warn" | "bad";
  unit?: string;
}) {
  const toneColor =
    tone === "ok"
      ? "var(--green)"
      : tone === "warn"
      ? "var(--amber)"
      : tone === "bad"
      ? "var(--red)"
      : "var(--text)";

  return (
    <div className="metric-card group">
      <div className="text-[11px] font-bold uppercase tracking-wider text-[var(--muted)]">
        {label}
      </div>
      <div className="my-2 flex items-baseline gap-1.5">
        <span
          className="text-2xl sm:text-3xl font-bold tracking-tight font-mono leading-none"
          style={{ color: toneColor }}
        >
          {value}
        </span>
        {unit && (
          <span className="text-xs font-mono font-medium text-[var(--muted)]">
            {unit}
          </span>
        )}
      </div>
      {hint && (
        <div className="text-xs text-[var(--muted)] line-clamp-2 leading-relaxed">
          {hint}
        </div>
      )}
      <div
        className="absolute top-0 right-0 w-12 h-12 pointer-events-none opacity-5 rounded-bl-full transition-opacity group-hover:opacity-10"
        style={{ background: toneColor }}
      />
    </div>
  );
}

/** Stat is aliased to MetricCard for backward compatibility */
export const Stat = MetricCard;

/* ------------------------------------------------------------------ Design System: Panel & ChartPanel */

export function Panel({
  title,
  subtitle,
  actions,
  children,
  className = "",
}: {
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      {(title || actions) && (
        <header className="flex flex-wrap items-start justify-between gap-3 mb-4 pb-3 border-b border-[var(--border-subtle)]">
          <div>
            {title && (
              <h2 className="text-sm font-semibold tracking-tight text-[var(--text)]">
                {title}
              </h2>
            )}
            {subtitle && (
              <p className="text-xs text-[var(--muted)] mt-0.5 leading-relaxed">
                {subtitle}
              </p>
            )}
          </div>
          {actions && (
            <div className="flex gap-2 flex-wrap items-center">{actions}</div>
          )}
        </header>
      )}
      {children}
    </section>
  );
}

export function ChartPanel({
  title,
  subtitle,
  actions,
  children,
  className = "",
}: {
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`panel ${className}`}>
      {(title || actions) && (
        <div className="flex items-center justify-between gap-3 mb-3 pb-2.5 border-b border-[var(--border-subtle)]">
          <HeaderContent title={title} subtitle={subtitle} actions={actions} />
        </div>
      )}
      <div className="w-full">{children}</div>
    </div>
  );
}

/* ------------------------------------------------------------------ Design System: MapPanel */

export function MapPanel({
  title,
  subtitle,
  actions,
  children,
  footer,
  className = "",
}: {
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  className?: string;
}) {
  return (
    <div className={`panel !p-0 overflow-hidden flex flex-col ${className}`}>
      {(title || actions) && (
        <div className="px-5 py-3 border-b border-[var(--border-subtle)] flex items-center justify-between gap-3 bg-[var(--bg-elev)]">
          <HeaderContent title={title} subtitle={subtitle} actions={actions} />
        </div>
      )}
      <div className="relative flex-1 w-full bg-[#070b12]">{children}</div>
      {footer && (
        <div className="px-4 py-2 border-t border-[var(--border-subtle)] bg-[var(--bg-elev)] text-xs text-[var(--muted)]">
          {footer}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ Design System: DataStatus */

export function DataStatus({
  verified,
  projectConfigured,
  label = "Earth Engine Gateway",
}: {
  verified?: boolean;
  projectConfigured?: boolean;
  label?: string;
}) {
  const status = verified
    ? "ONLINE & VERIFIED"
    : projectConfigured
    ? "CONFIGURED (UNPROBED)"
    : "OFFLINE / UNCONFIGURED";
  const color = verified
    ? "var(--green)"
    : projectConfigured
    ? "var(--amber)"
    : "var(--red)";

  return (
    <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded bg-[var(--bg-soft)] border border-[var(--border)] text-xs font-mono">
      <span className="w-2 h-2 rounded-full" style={{ background: color }} />
      <span className="text-[var(--muted)]">{label}:</span>
      <span className="font-semibold text-[var(--text)]">{status}</span>
    </div>
  );
}

/* ------------------------------------------------------------------ Design System: FilterToolbar */

export function FilterToolbar({ children }: { children: ReactNode }) {
  return (
    <div className="p-2.5 rounded-lg bg-[var(--bg-soft)] border border-[var(--border-subtle)] flex flex-wrap items-center gap-3 text-xs">
      {children}
    </div>
  );
}

/* ------------------------------------------------------------------ Design System: ResearchFinding */

export function ResearchFinding({
  title,
  statement,
  synthetic,
  tag,
  children,
}: {
  title: string;
  statement: string;
  synthetic?: boolean;
  tag?: string;
  children?: ReactNode;
}) {
  return (
    <article className="p-4 rounded-lg bg-[var(--bg-soft)] border border-[var(--border-subtle)] space-y-2 hover:border-[var(--border)] transition-colors">
      <div className="flex items-center justify-between gap-2">
        <h3 className="font-semibold text-sm text-[var(--text)] flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent)]" />
          {title}
        </h3>
        <div className="flex items-center gap-2">
          {tag && <span className="badge font-mono text-[10px]">{tag}</span>}
          {synthetic && (
            <span className="badge badge-warn font-semibold">SYNTHETIC</span>
          )}
        </div>
      </div>
      <p className="text-xs sm:text-sm text-[var(--text-2)] leading-relaxed">
        {statement}
      </p>
      {children}
    </article>
  );
}

/* ------------------------------------------------------------------ Design System: EmptyState */

export function EmptyState({
  title = "No Data Available",
  description,
  action,
}: {
  title?: string;
  description: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="panel !p-8 text-center flex flex-col items-center justify-center space-y-3">
      <div className="w-12 h-12 rounded-full bg-[var(--bg-soft)] border border-[var(--border)] flex items-center justify-center text-[var(--amber)]">
        <svg
          className="w-6 h-6"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          viewBox="0 0 24 24"
        >
          <path d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
        </svg>
      </div>
      <h3 className="text-base font-semibold text-[var(--text)]">{title}</h3>
      <div className="text-xs sm:text-sm text-[var(--muted)] max-w-md leading-relaxed">
        {description}
      </div>
      {action && <div className="pt-2">{action}</div>}
    </div>
  );
}

/* ------------------------------------------------------------------ Query & State Handlers */

export function Skeleton({ h = 220 }: { h?: number }) {
  return (
    <div
      className="skeleton w-full"
      style={{ height: h }}
      role="status"
      aria-label="Loading"
    />
  );
}

export function ErrorState({ error }: { error: ApiError | Error }) {
  const e = error as ApiError;
  const noData = e.code === "no_data";
  const ee = e.code === "earth_engine_unavailable";

  return (
    <div
      role="alert"
      className="rounded-lg p-4 border text-sm"
      style={{
        borderColor: noData ? "var(--amber)" : "var(--red)",
        background: "var(--bg-soft)",
      }}
    >
      <div
        className="font-semibold mb-1 flex items-center gap-2"
        style={{ color: noData ? "var(--amber)" : "var(--red)" }}
      >
        <span>
          {noData
            ? "No data available"
            : ee
            ? "Earth Engine unavailable"
            : e.code === "network"
            ? "Backend unreachable"
            : "Request failed"}
        </span>
      </div>
      <p className="text-xs sm:text-sm text-[var(--text-2)]">{e.message}</p>
      {(noData || ee) && (
        <p className="mt-2 text-xs text-[var(--muted)]">
          <Link
            to="/settings"
            className="underline font-medium text-[var(--teal)] hover:brightness-125"
          >
            Open Settings
          </Link>{" "}
          to configure Earth Engine, upload datasets, or toggle demonstration
          mode.
        </p>
      )}
    </div>
  );
}

export function Q<T>({
  q,
  children,
  h,
}: {
  q: UseQueryResult<T, ApiError>;
  children: (d: T) => ReactNode;
  h?: number;
}) {
  if (q.isLoading) return <Skeleton h={h} />;
  if (q.error) return <ErrorState error={q.error} />;
  if (!q.data) return <p className="muted text-xs">No results returned.</p>;
  return <>{children(q.data)}</>;
}

export function SyntheticBadge({ meta }: { meta?: Meta }) {
  if (!meta?.synthetic) return null;
  return (
    <span
      className="badge badge-warn font-semibold tracking-wider"
      title={meta.disclaimer ?? ""}
    >
      SYNTHETIC SAMPLE
    </span>
  );
}

export const fmt = (v: number | null | undefined, d = 3) =>
  v === null || v === undefined || !Number.isFinite(v)
    ? "–"
    : Math.abs(v) >= 1000
    ? v.toFixed(0)
    : Math.abs(v) < 0.001 && v !== 0
    ? v.toExponential(2)
    : v.toFixed(d);

export const fmtP = (p: number) => (p < 0.001 ? "<0.001" : p.toFixed(3));

const dirIcon: Record<string, string> = {
  increasing: "▲ increasing",
  decreasing: "▼ decreasing",
  "no significant trend": "● no significant trend",
};

export function ResultBlock({
  t,
  meta,
  unit,
  interpretation,
  limitations,
  label,
}: {
  t: TrendTest;
  meta: Meta;
  unit: string;
  interpretation?: string;
  limitations?: string;
  label?: string;
}) {
  const tone = t.direction === "no significant trend" ? "" : "font-semibold";
  return (
    <div className="text-xs sm:text-sm space-y-2.5" data-testid="result-block">
      <div className="flex flex-wrap gap-2 items-center">
        <span className="badge font-mono">{t.test}</span>
        <SyntheticBadge meta={meta} />
        <span
          className={tone}
          style={{
            color:
              t.direction === "increasing"
                ? "var(--green)"
                : t.direction === "decreasing"
                ? "var(--amber)"
                : "var(--muted)",
          }}
        >
          {dirIcon[t.direction] ?? t.direction}
        </span>
      </div>
      <div className="tbl-wrap">
        <table className="tbl">
          <tbody>
            <tr>
              <td className="muted font-medium w-1/3">Variable</td>
              <td className="font-medium text-[var(--text)]">
                {label ?? meta.variable} ({meta.aggregation})
              </td>
            </tr>
            <tr>
              <td className="muted font-medium">Dataset</td>
              <td className="font-mono text-xs">
                {meta.dataset?.ee_id ?? meta.dataset?.provider} ·{" "}
                {meta.dataset?.spatial_resolution}
              </td>
            </tr>
            <tr>
              <td className="muted font-medium">Period</td>
              <td>
                {meta.period ?? meta.dataset?.processing_period} (n={t.n})
              </td>
            </tr>
            <tr>
              <td className="muted font-medium">Z / p-value</td>
              <td>
                <span className="font-mono">{fmt(t.z, 2)}</span> /{" "}
                <b className="font-mono">{fmtP(t.p)}</b>{" "}
                <span className="text-xs muted">
                  {t.significant
                    ? `(significant at α=${t.alpha})`
                    : "(not significant)"}
                </span>
              </td>
            </tr>
            <tr>
              <td className="muted font-medium">Sen slope</td>
              <td>
                <span className="font-mono font-semibold">{fmt(t.slope, 4)}</span>{" "}
                {unit}/yr ·{" "}
                <span className="text-xs muted font-mono">
                  95% CI [{fmt(t.slope_ci_low, 4)}, {fmt(t.slope_ci_high, 4)}]
                </span>
              </td>
            </tr>
            <tr>
              <td className="muted font-medium">Kendall τ</td>
              <td className="font-mono">{fmt(t.tau, 3)}</td>
            </tr>
          </tbody>
        </table>
      </div>
      {interpretation && (
        <p className="text-xs sm:text-sm text-[var(--text-2)] bg-[var(--bg-soft)] p-2.5 rounded border border-[var(--border)]">
          <b className="text-[var(--text)]">Interpretation.</b> {interpretation}
        </p>
      )}
      {limitations && (
        <p className="muted text-xs">
          <b>Limitations.</b> {limitations}
        </p>
      )}
    </div>
  );
}

export function Field({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1 text-xs text-[var(--muted)] font-medium">
      {label}
      {children}
    </label>
  );
}

export function Select<T extends string>({
  value,
  onChange,
  options,
  label,
}: {
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: string }[];
  label: string;
}) {
  return (
    <Field label={label}>
      <select
        className="field"
        value={value}
        onChange={(e) => onChange(e.target.value as T)}
        aria-label={label}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </Field>
  );
}

export function RequireData({
  keys,
  what,
  children,
}: {
  keys: string[];
  what: string;
  children: ReactNode;
}) {
  const { regionId, source } = useApp();
  const q = useApi<{ items: DatasetItem[] }>("/datasets", {
    region: regionId,
    source,
  });
  if (q.isLoading) return <Skeleton h={300} />;
  if (q.error) return <ErrorState error={q.error} />;
  const ok = q.data?.items.some((i) => keys.includes(i.key) && i.available);
  if (ok) return <>{children}</>;
  return (
    <div role="status" className="panel !p-6" data-testid="empty-state">
      <div className="flex items-start gap-4">
        <div className="p-2.5 rounded-lg bg-[var(--bg-soft)] border border-[var(--border)] text-[var(--amber)]">
          <svg
            className="w-6 h-6"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            viewBox="0 0 24 24"
          >
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
        </div>
        <div>
          <h2 className="text-base font-semibold text-[var(--amber)]">
            No data available
          </h2>
          <p className="text-sm text-[var(--text-2)] mt-1 max-w-2xl leading-relaxed">
            {what} has not been processed for this region (source:{" "}
            <span className="font-mono font-semibold">{source}</span>). In
            accordance with scientific integrity guidelines, no speculative or
            mock values are shown.
          </p>
          <ul className="list-disc pl-5 text-xs text-[var(--muted)] mt-3 space-y-1">
            <li>
              Configure Google Earth Engine credentials and launch an extraction
              job in Settings, or
            </li>
            <li>Upload verified ground measurement records (e.g. well logs), or</li>
            <li>
              Switch to the isolated Synthetic Sample mode to evaluate dashboard
              calculations.
            </li>
          </ul>
          <Link to="/settings" className="btn btn-primary mt-4 text-xs">
            Open Settings &amp; Data Pipeline
          </Link>
        </div>
      </div>
    </div>
  );
}

/* shared header used by Panel and MapPanel */
function HeaderContent({ title, subtitle, actions }: { title?: ReactNode; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <>
      <div>
        {title && <h3 className="text-sm font-semibold tracking-tight text-[var(--text)]">{title}</h3>}
        {subtitle && <p className="text-xs text-[var(--muted)] mt-0.5">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </>
  );
}
