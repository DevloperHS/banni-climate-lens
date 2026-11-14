import { ReactNode, useRef } from "react";
import {
  Area, Bar, BarChart, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ReferenceLine, Cell, ErrorBar,
} from "recharts";
import { Meta } from "../lib/api";
import { SyntheticBadge, fmt } from "./ui";

export const COLORS = ["var(--c1)", "var(--c2)", "var(--c3)", "var(--c4)"];

/** Serialise the first <svg> inside `el` to a PNG download. */
export function downloadChartPng(el: HTMLElement | null, filename: string, synthetic = false) {
  const svg = el?.querySelector("svg.recharts-surface") as SVGSVGElement | null;
  if (!svg) return;
  const { width, height } = svg.getBoundingClientRect();
  const clone = svg.cloneNode(true) as SVGSVGElement;
  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  const cs = getComputedStyle(document.documentElement);
  let xml = new XMLSerializer().serializeToString(clone);
  // resolve CSS variables, which do not exist inside a detached image
  xml = xml.replace(/var\((--[\w-]+)\)/g, (_, v) => cs.getPropertyValue(v).trim() || "#888");
  const img = new Image();
  img.onload = () => {
    const s = 2, pad = synthetic ? 22 : 0;
    const c = document.createElement("canvas");
    c.width = width * s; c.height = (height + pad) * s;
    const g = c.getContext("2d")!;
    g.scale(s, s);
    g.fillStyle = cs.getPropertyValue("--bg-elev").trim() || "#fff";
    g.fillRect(0, 0, width, height + pad);
    if (synthetic) { g.fillStyle = "#c0392b"; g.font = "bold 12px sans-serif"; g.fillText("SYNTHETIC SAMPLE DATA - not an observation", 8, 15); }
    g.drawImage(img, 0, pad);
    const a = document.createElement("a");
    a.download = filename; a.href = c.toDataURL("image/png"); a.click();
  };
  img.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(xml);
}

export function ChartFrame({ title, subtitle, meta, filename, children, height = 280, extra }: {
  title: ReactNode; subtitle?: ReactNode; meta?: Meta; filename: string; children: ReactNode; height?: number; extra?: ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  return (
    <div>
      <div className="flex flex-wrap justify-between gap-2 mb-2 items-start">
        <div>
          <h3 className="text-sm font-semibold">{title} <SyntheticBadge meta={meta} /></h3>
          {subtitle && <p className="muted text-xs">{subtitle}</p>}
        </div>
        <div className="flex gap-2 items-center">
          {extra}
          <button className="btn" onClick={() => downloadChartPng(ref.current, filename + ".png", meta?.synthetic)} aria-label={`Download chart ${filename}`}>⬇ PNG</button>
        </div>
      </div>
      <div ref={ref} style={{ width: "100%", height }} data-testid="chart">
        <ResponsiveContainer width="100%" height="100%">{children as React.ReactElement}</ResponsiveContainer>
      </div>
    </div>
  );
}

const axis = { stroke: "var(--muted)", tick: { fill: "var(--muted)", fontSize: 11 } } as const;
const tip = { contentStyle: { background: "var(--bg-elev)", border: "1px solid var(--border)", borderRadius: 8, color: "var(--text)" }, labelStyle: { color: "var(--muted)" } };

type Dim = { width?: number; height?: number };

export interface LineSpec { key: string; name: string; color?: string; dashed?: boolean; dots?: boolean }

/** Multi-line chart over rows [{x, <key>: number|null}] */
export function LinesChart({ rows, lines, unit, xLabel, yLabel, width, height }: Dim & { rows: Record<string, unknown>[]; lines: LineSpec[]; unit?: string; xLabel?: string; yLabel?: string }) {
  return (
    <ComposedChart width={width} height={height} data={rows} margin={{ top: 6, right: 12, left: 0, bottom: 0 }}>
      <CartesianGrid stroke="var(--grid)" strokeDasharray="3 3" />
      <XAxis dataKey="x" {...axis} minTickGap={32} label={xLabel ? { value: xLabel, position: "insideBottom", offset: -2, fill: "var(--muted)", fontSize: 11 } : undefined} />
      <YAxis {...axis} width={52} tickFormatter={(v) => fmt(v, 2)} label={yLabel ? { value: yLabel, angle: -90, position: "insideLeft", fill: "var(--muted)", fontSize: 11 } : undefined} />
      <Tooltip {...tip} formatter={(v: number) => [`${fmt(v, 4)} ${unit ?? ""}`]} />
      {lines.length > 1 && <Legend />}
      {lines.map((l, i) => (
        <Line key={l.key} type="monotone" dataKey={l.key} name={l.name} stroke={l.color ?? COLORS[i % 4]} strokeWidth={l.dashed ? 1.5 : 2}
          strokeDasharray={l.dashed ? "5 4" : undefined} dot={l.dots ? { r: 2.5 } : false} connectNulls isAnimationActive={false} />
      ))}
    </ComposedChart>
  );
}

export function BarsChart({ rows, unit, flagKey, yLabel, width, height }: Dim & { rows: { x: string | number; v: number | null; flag?: boolean }[]; unit?: string; flagKey?: boolean; yLabel?: string }) {
  return (
    <BarChart width={width} height={height} data={rows} margin={{ top: 6, right: 12, left: 0, bottom: 0 }}>
      <CartesianGrid stroke="var(--grid)" strokeDasharray="3 3" />
      <XAxis dataKey="x" {...axis} minTickGap={24} />
      <YAxis {...axis} width={52} tickFormatter={(v) => fmt(v, 2)} label={yLabel ? { value: yLabel, angle: -90, position: "insideLeft", fill: "var(--muted)", fontSize: 11 } : undefined} />
      <Tooltip {...tip} formatter={(v: number) => [`${fmt(v, 4)} ${unit ?? ""}`]} />
      <ReferenceLine y={0} stroke="var(--muted)" />
      <Bar dataKey="v" isAnimationActive={false}>
        {rows.map((r, i) => <Cell key={i} fill={flagKey && r.flag ? "var(--amber)" : (r.v ?? 0) >= 0 ? "var(--c1)" : "var(--c2)"} />)}
      </Bar>
    </BarChart>
  );
}

export function PatternChart({ month, mean, sd, unit, width, height }: Dim & { month: number[]; mean: (number | null)[]; sd: (number | null)[]; unit?: string }) {
  const names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const rows = month.map((m, i) => ({ x: names[m - 1], v: mean[i], err: sd[i] ?? 0 }));
  return (
    <BarChart width={width} height={height} data={rows} margin={{ top: 6, right: 12, left: 0, bottom: 0 }}>
      <CartesianGrid stroke="var(--grid)" strokeDasharray="3 3" />
      <XAxis dataKey="x" {...axis} /><YAxis {...axis} width={52} tickFormatter={(v) => fmt(v, 2)} />
      <Tooltip {...tip} formatter={(v: number) => [`${fmt(v, 3)} ${unit ?? ""}`, "mean"]} />
      <Bar dataKey="v" fill="var(--c1)" isAnimationActive={false}><ErrorBar dataKey="err" stroke="var(--muted)" width={4} /></Bar>
    </BarChart>
  );
}

export function ScatterPlot({ pts, xName, yName, line, width, height }: Dim & { pts: { x: number; y: number; year?: number }[]; xName: string; yName: string; line?: { x: number; y: number }[] }) {
  return (
    <ScatterChart width={width} height={height} margin={{ top: 6, right: 12, left: 0, bottom: 16 }}>
      <CartesianGrid stroke="var(--grid)" strokeDasharray="3 3" />
      <XAxis type="number" dataKey="x" name={xName} {...axis} domain={["auto", "auto"]} tickFormatter={(v) => fmt(v, 2)} label={{ value: xName, position: "insideBottom", offset: -8, fill: "var(--muted)", fontSize: 11 }} />
      <YAxis type="number" dataKey="y" name={yName} {...axis} width={52} domain={["auto", "auto"]} tickFormatter={(v) => fmt(v, 2)} />
      <Tooltip {...tip} cursor={{ strokeDasharray: "3 3" }} formatter={(v: number) => fmt(v, 4)} />
      <Scatter data={pts} fill="var(--c2)" isAnimationActive={false} />
      {line && <Scatter data={line} line={{ stroke: "var(--c3)", strokeWidth: 2 }} shape={() => <g />} isAnimationActive={false} legendType="none" />}
    </ScatterChart>
  );
}

/** Observed vs predicted with the gap between them shaded (green where observed > predicted, amber where below). */
export function GapChart({ years, observed, predicted, unit, markYear, obsName = "Observed", predName = "Predicted from rainfall", width, height }: Dim & {
  years: number[]; observed: number[]; predicted: number[]; unit?: string; markYear?: number | null; obsName?: string; predName?: string;
}) {
  const rows = years.map((x, i) => {
    const o = observed[i], p = predicted[i];
    return { x, obs: o, pred: p, above: o >= p ? [p, o] : [p, p], below: o < p ? [o, p] : [p, p] };
  });
  return (
    <ComposedChart width={width} height={height} data={rows} margin={{ top: 6, right: 12, left: 0, bottom: 0 }}>
      <CartesianGrid stroke="var(--grid)" strokeDasharray="3 3" />
      <XAxis dataKey="x" {...axis} minTickGap={24} />
      <YAxis {...axis} width={52} domain={["auto", "auto"]} tickFormatter={(v) => fmt(v, 2)} />
      <Tooltip {...tip} formatter={(v: number | number[], n: string) => (Array.isArray(v) ? [null, null] : [`${fmt(v, 4)} ${unit ?? ""}`, n])} />
      <Legend />
      <Area type="linear" dataKey="above" name="Greener than rain predicts" stroke="none" fill="var(--green)" fillOpacity={0.3} isAnimationActive={false} />
      <Area type="linear" dataKey="below" name="Browner than rain predicts" stroke="none" fill="var(--amber)" fillOpacity={0.3} isAnimationActive={false} />
      <Line type="linear" dataKey="pred" name={predName} stroke="var(--muted)" strokeDasharray="5 4" strokeWidth={1.5} dot={false} isAnimationActive={false} />
      <Line type="linear" dataKey="obs" name={obsName} stroke="var(--c1)" strokeWidth={2} dot={{ r: 2.5 }} isAnimationActive={false} />
      {markYear && <ReferenceLine x={markYear} stroke="var(--amber)" strokeWidth={1.5} />}
    </ComposedChart>
  );
}

/** Stacked percentage bars, one bar per year (e.g. land-cover class shares). */
export function StackedShareChart({ rows, series, unit = "%", width, height }: Dim & { rows: Record<string, number | string>[]; series: { key: string; name: string; color: string }[]; unit?: string }) {
  return (
    <BarChart width={width} height={height} data={rows} margin={{ top: 6, right: 12, left: 0, bottom: 0 }}>
      <CartesianGrid stroke="var(--grid)" strokeDasharray="3 3" />
      <XAxis dataKey="x" {...axis} minTickGap={24} />
      <YAxis {...axis} width={40} domain={[0, 100]} tickFormatter={(v) => fmt(v, 0)} />
      <Tooltip {...tip} formatter={(v: number, n: string) => [`${fmt(v, 1)} ${unit}`, n]} />
      <Legend />
      {series.map((s) => <Bar key={s.key} dataKey={s.key} name={s.name} stackId="a" fill={s.color} isAnimationActive={false} />)}
    </BarChart>
  );
}
