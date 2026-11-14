import { DatasetItem } from "../lib/api";
import { PageHeader, Panel, Q, SectionHeader, useApi, useScope } from "../components/ui";

const METHODS: [string, string][] = [
  [
    "Aggregation & Compositing",
    "Monthly values are built from satellite composites (NDVI/LST: mean of valid composites per month; ET: 8-day totals converted to daily rates, averaged, scaled by days in month; IMERG: mm/hr × 24 × days). Seasonal/annual values require full temporal coverage for sums (rainfall, ET) and ≥75% of months for means. Seasons: summer MAM, monsoon JJAS, post-monsoon ON, winter DJF.",
  ],
  [
    "Mann-Kendall Monotonic Test",
    "Non-parametric rank-based test for monotonic trends with tie correction. Z-statistic uses the continuity-corrected S statistic; two-sided p-values. Numerically validated against pymannkendall.",
  ],
  [
    "Hamed-Rao Autocorrelation Correction",
    "Variance of the S statistic is adjusted by a variance inflation factor derived from significant empirical autocorrelations of the rank-transformed, Sen-detrended series. Used preferentially when lag-1 serial correlation is detected.",
  ],
  [
    "Sen's Non-Parametric Slope",
    "Median of all pairwise temporal slopes using actual sample spacing gaps. Non-parametric confidence intervals calculated from the Sen/Gilbert order-statistic method incorporating Mann-Kendall variance.",
  ],
  [
    "Rainfall Adjustment (Residualization)",
    "Ordinary Least Squares: Response ~ Rainfall (monsoon seasonal totals). Model residuals are tested for lingering monotonic trends. Tested across five sensitivity specifications (S1: lagged rainfall; S2: Theil-Sen line; S3: Year trend with Newey-West HAC errors; S4: influential years Cook's D>4/n removed; S5: monthly deseasonalized anomaly ~ 3-month rainfall anomaly).",
  ],
  [
    "Vectorised Pixel Trends (FDR Controlled)",
    "Massively vectorised Mann-Kendall and Sen slope computed per pixel across raster stacks (≥10 valid observation years). Significance is controlled across thousands of pixels via the Benjamini-Hochberg false discovery rate algorithm (default q=0.05).",
  ],
  [
    "Rann-Water Occurrence Masking",
    "Grid cells with long-term JRC surface-water occurrence ≥ 10% (1984–2021) are removed before pixel statistical testing to prevent water body fluctuations from corrupting vegetation dynamics.",
  ],
  [
    "Dry-Season Persistence Indicator (Exploratory)",
    "Summer (Mar–May) NDVI divided by monsoon NDVI per pixel and year. Deep-rooted evergreen vegetation retains higher ratios than herbaceous cover, but so do irrigated plots and salt-tolerant halophytes. Treated strictly as an exploratory hypothesis generator, not a classifier.",
  ],
  [
    "Cross-Sensor Spatial Convergence",
    "Landsat 30m pixel slopes and FDR classes are aggregated onto the 250m MODIS grid to evaluate sign agreement and rank correlation.",
  ],
  [
    "Spectral Salinity Proxy",
    "SI1 = √(Green × Red) calculated over dry-season Landsat median composites. Treated as an uncalibrated spectral proxy requiring ground-truth electrical conductivity (EC) calibration.",
  ],
  [
    "Multivariate Comparative Modeling",
    "Pairwise correlation matrices with FDR correction, partial correlations, multi-predictor OLS with Variance Inflation Factors (VIF), and leave-one-out cross-validated R² (PRESS). Association and prediction are documented separately; causal attribution is rejected.",
  ],
  [
    "Interrupted Event Perturbations",
    "Change in deseasonalized indicator anomaly following extreme meteorological disruptions (e.g. Cyclone Biparjoy) is ranked against placebo calendar windows from all historical reference years.",
  ],
  [
    "In-Situ Groundwater Piezometry",
    "Per-well Mann-Kendall and Sen slope on annual CGWB well records with Benjamini-Hochberg FDR correction across wells.",
  ],
];

const LIMITS = [
  "NDVI cannot discriminate plant species. A positive rainfall-adjusted NDVI trend is not evidence of Prosopis juliflora expansion versus native grassland recovery.",
  "MODIS LST measures radiometric skin surface temperature, not ambient 2m meteorological air temperature.",
  "MOD16 ET and GLDAS soil moisture are land-surface model outputs; GLDAS spans only a few 0.25° cells over this region. Neither determines groundwater table movement.",
  "IMERG is a satellite-gauge hybrid precipitation estimate at ~11 km resolution; local convective rainfall may differ.",
  "Annual time-series have ~24 observations: statistical power is constrained, and failure to reject the null is not proof of absence of change.",
  "Salinity: only an unvalidated spectral index proxy exists; field electrical conductivity (EC) measurements are required for calibration.",
  "No field ground-truth labels exist, so no species-level supervised classification or machine learning accuracy claims are made.",
  "JRC monthly water history ends in January 2022; the Landsat MNDWI series (2013+) is an unvalidated alternative.",
];

export default function Methodology() {
  const sc = useScope();
  const ds = useApi<{ items: DatasetItem[] }>("/datasets", { region: sc.region, source: sc.source });

  return (
    <>
      <PageHeader
        title="Methodology"
        subtitle="Mathematical specifications, compositing workflows, sensor references, and methodological limitations governing the GlobalClimateLens platform. Complete technical documentation available in docs/METHODOLOGY.md."
        badges={
          <div className="flex items-center gap-2">
            <span className="badge font-mono text-[11px] text-[var(--teal)] border-[var(--border-hi)]">
              Reproducible Pipeline
            </span>
            <span className="badge font-mono text-[11px]">Strict Provenance</span>
          </div>
        }
      />

      <Panel title="Earth Observation Datasets & Provenance" subtitle="Primary satellite collections, spatial/temporal resolution, and filtering criteria">
        <Q q={ds}>
          {(d) => (
            <div className="tbl-wrap">
              <table className="tbl">
                <thead>
                  <tr>
                    <th>Variable</th>
                    <th>Collection ID</th>
                    <th>Provider</th>
                    <th>Resolution</th>
                    <th>Unit</th>
                    <th>Scale Factor</th>
                    <th>Quality Filter</th>
                    <th>Documented Limits</th>
                  </tr>
                </thead>
                <tbody>
                  {d.items.map((i) => (
                    <tr key={i.key}>
                      <td className="font-medium text-[var(--text)]">{i.label}</td>
                      <td className="font-mono text-xs text-[var(--teal)]">{i.ee_id ?? "User upload"}</td>
                      <td>{i.provider}</td>
                      <td className="text-xs">
                        {i.spatial_resolution}
                        <br />
                        <span className="muted">{i.temporal_resolution}</span>
                      </td>
                      <td className="font-mono text-xs">{i.unit}</td>
                      <td className="font-mono text-xs">{i.scale_factor}</td>
                      <td className="text-xs">{i.quality_filter}</td>
                      <td className="text-xs text-[var(--muted)]">{i.limitations}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Q>
      </Panel>

      <SectionHeader
        title="Statistical Framework & Algorithms"
        description="Formal definitions of statistical tests, variance corrections, and multiple-hypothesis adjustments."
      />

      <div className="grid gap-3.5 md:grid-cols-2">
        {METHODS.map(([title, desc]) => (
          <article
            key={title}
            className="p-3.5 rounded-lg bg-[var(--bg-elev)] border border-[var(--border)] hover:border-[var(--border-hi)] transition-colors"
          >
            <h3 className="font-semibold text-xs sm:text-sm text-[var(--text)] flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent)]" />
              {title}
            </h3>
            <p className="text-xs text-[var(--text-2)] mt-1.5 leading-relaxed">{desc}</p>
          </article>
        ))}
      </div>

      <SectionHeader
        title="Known Scientific Limitations & Guardrails"
        description="Explicit boundaries preventing over-interpretation of Earth observation proxies."
      />

      <div className="p-4 rounded-lg bg-[var(--bg-soft)] border border-[var(--amber)]">
        <div className="flex items-center gap-2 mb-2 text-sm font-semibold text-[var(--amber)]">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
            <line x1="12" y1="9" x2="12" y2="13" />
            <line x1="12" y1="17" x2="12.01" y2="17" />
          </svg>
          Strict Platform Scientific Guardrails
        </div>
        <ul className="grid gap-2 sm:grid-cols-2 text-xs text-[var(--text-2)]">
          {LIMITS.map((l) => (
            <li key={l} className="flex items-start gap-2">
              <span className="text-[var(--amber)] font-bold">•</span>
              <span className="leading-relaxed">{l}</span>
            </li>
          ))}
        </ul>
      </div>
    </>
  );
}
