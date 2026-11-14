import { createContext, useCallback, useContext, useEffect, useMemo, useState, ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiGet, Region, Source } from "../lib/api";

type Theme = "dark" | "light";
interface State {
  regions: Region[];
  region: Region | undefined;
  regionId: string;
  setRegionId: (id: string) => void;
  source: Source;
  setSource: (s: Source) => void;
  demo: boolean;
  setDemo: (d: boolean) => void;
  start: number;
  end: number;
  setPeriod: (start: number, end: number) => void;
  theme: Theme;
  toggleTheme: () => void;
  regionsError: Error | null;
  regionsLoading: boolean;
}
const Ctx = createContext<State | null>(null);

const read = (k: string, d: string) => {
  try {
    return localStorage.getItem(k) ?? d;
  } catch {
    return d;
  }
};
const write = (k: string, v: string) => {
  try {
    localStorage.setItem(k, v);
  } catch {
    /* storage unavailable */
  }
};

export function AppStateProvider({ children }: { children: ReactNode }) {
  const regionsQ = useQuery({ queryKey: ["regions"], queryFn: () => apiGet<{ items: Region[] }>("/regions") });
  const regions = regionsQ.data?.items ?? [];
  const [regionId, setRegionIdRaw] = useState(read("gcl.region", "banni"));
  const [source, setSourceRaw] = useState<Source>(read("gcl.source", "processed") as Source);
  const [theme, setTheme] = useState<Theme>(read("gcl.theme", "dark") as Theme);
  const [demo, setDemoRaw] = useState(read("gcl.demo", "0") === "1");
  const [period, setPeriodRaw] = useState<[number | null, number | null]>([null, null]);

  const region = regions.find((r) => r.id === regionId) ?? regions[0];
  const start = period[0] ?? region?.study_period.start ?? 2001;
  const end = period[1] ?? region?.study_period.end ?? 2024;

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);

  const setRegionId = useCallback((id: string) => {
    setRegionIdRaw(id);
    setPeriodRaw([null, null]);
    write("gcl.region", id);
  }, []);
  const setSource = useCallback((s: Source) => {
    setSourceRaw(s);
    write("gcl.source", s);
  }, []);
  const setDemo = useCallback((d: boolean) => {
    setDemoRaw(d);
    write("gcl.demo", d ? "1" : "0");
    if (!d) { setSourceRaw("processed"); write("gcl.source", "processed"); }
  }, []);
  const setPeriod = useCallback((a: number, b: number) => setPeriodRaw([Math.min(a, b), Math.max(a, b)]), []);
  const toggleTheme = useCallback(() => {
    setTheme((t) => {
      const n = t === "dark" ? "light" : "dark";
      write("gcl.theme", n);
      return n;
    });
  }, []);

  const value = useMemo<State>(
    () => ({
      regions, region, regionId: region?.id ?? regionId, setRegionId, source: demo ? source : "processed", setSource, demo, setDemo, start, end, setPeriod, theme, toggleTheme,
      regionsError: regionsQ.error as Error | null, regionsLoading: regionsQ.isLoading,
    }),
    [regions, region, regionId, setRegionId, source, setSource, demo, setDemo, start, end, setPeriod, theme, toggleTheme, regionsQ.error, regionsQ.isLoading],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useApp() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useApp outside AppStateProvider");
  return v;
}
