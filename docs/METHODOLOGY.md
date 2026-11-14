# Statistical methodology

All methods live in `backend/app/science/stats.py`, `timeseries.py`, `pixel.py`, and are validated in `backend/tests/test_science.py`.

## 1. Temporal aggregation
Seasons: summer MAM, monsoon JJAS, post-monsoon ON, winter DJF (Dec/Jan/Feb in the same calendar year), "peak" Sep–Oct, annual Jan–Dec. Sums (rainfall, ET) require every month; means require ≥75% of months. Years failing the rule are omitted, not imputed.

## 2. Trend tests
**Mann-Kendall.** S = Σ sign(x_j − x_i), i<j. Variance with tie correction: Var(S) = [n(n−1)(2n+5) − Σ t(t−1)(2t+5)]/18. Z = (S − sign(S))/√Var(S); two-sided p from the normal distribution; τ = S/(n(n−1)/2). Needs n ≥ 4.

**Hamed-Rao modification.** Detrend with Sen's slope, rank the residuals, compute the rank autocorrelation ρ_k for k = 1…n−1, keep lags outside ±z₁₋α/₂/√n, and scale Var(S) by n/n*_s = 1 + 2/[n(n−1)(n−2)] Σ (n−k)(n−k−1)(n−k−2) ρ_k. Non-positive factors fall back to 1. **Implementation is cross-checked against `pymannkendall` (agreement to 1e-8 on random AR(1) series).** The API returns both tests; `recommended = hr` when |lag-1 autocorrelation| > 0.3 or the correction ≠ 1.

**Sen's slope.** Median of (x_j − x_i)/(t_j − t_i) using real time values, so gaps are handled correctly; intercept = median(x − slope·t). 95% CI by the Sen/Gilbert order-statistic method with the (corrected) variance of S.

**Reading a result.** "Increasing/decreasing" means a monotonic change unlikely under chance at α=0.05. It says nothing about cause. "No significant trend" means the data cannot distinguish a trend from variability, not that none exists (n≈24, limited power).

## 3. Regression and correlation
OLS (statsmodels) with intercept: coefficients, SE, t, p, 95% CI, R², adjusted R², F-test p, residuals. Robustness: Newey-West (HAC) SE/p/CI with lag ⌊4(n/100)^(2/9)⌋. Diagnostics: Durbin-Watson, Ljung-Box (lag ≤10), Shapiro-Wilk, Breusch-Pagan, Cook's distance (> 4/n flagged). Correlation: Pearson with Fisher-z 95% CI, Spearman ρ; optional linear detrending so shared trends are not mistaken for co-variability. **Association is not causation**; every response carries that note.

## 4. Rainfall-adjusted vegetation analysis
Reproduces the intended analysis *NDVI ~ Rainfall → trend in residuals*, then critically tests it. The full handover (15 pp.) has since been compared with the implementation: see `docs/SCIENTIFIC_VALIDATION_REPORT.md` §2. `science/handover.py` runs the handover's exact Colab protocol (pymannkendall Hamed-Rao + `sens_slope`, OLS, residual trend) and compares it with the reported values, labelling each row *reproduced*, *consistent* or *not reproduced*; results are never adjusted to match. ET and soil moisture are controlled for with **monsoon** rainfall (`rain_season`), as in the handover.

Primary model (annual resolution, same-season totals):  `NDVI_y = b0 + b1·Rain_y + e_y`. Residuals e_y are tested with MK / Hamed-Rao / Sen.

Sensitivity analyses (each reports the residual-trend direction):
- **S1** add previous-year rainfall (lagged water availability).
- **S2** Theil-Sen robust line instead of OLS.
- **S3** `NDVI ~ Rain + Year` with HAC errors (direct test of the year coefficient).
- **S4** refit after removing influential years (Cook's D > 4/n).
- **S5** monthly, deseasonalised NDVI anomaly ~ 3-month cumulative rainfall anomaly (removes seasonality explicitly), HR test on residuals.

Caveats are generated from the diagnostics (autocorrelation, non-normality, heteroscedasticity, influential years, low R², trending rainfall, small n). A fixed caveat always states that grazing, *Prosopis* spread, flooding/salinity, temperature and land-cover change are unmodelled confounders: **a positive residual trend is not evidence of *Prosopis* expansion or of grassland recovery.** The verdict text reports how many sensitivities agree and never names a cause.

## 5. Pixel-level trends and multiple testing
For every pixel with ≥10 valid years: tie-corrected Mann-Kendall (vectorised, verified equal to the scalar implementation) and Sen's slope. All pixel p-values are then adjusted with the **Benjamini-Hochberg** procedure (default q=0.05); only FDR-passing pixels are classed significant. The UI shows the uncorrected count beside the corrected one to expose the inflation (a pure-noise test in the suite yields ≈5% uncorrected and ≈0 corrected). Limitations: spatial autocorrelation makes BH approximate; per-pixel tests ignore serial correlation (no pixel-level Hamed-Rao); a significant NDVI pixel is a greenness change, not a species or cause. GeoTIFF export bands: `sen_slope_per_year`, `mk_z`, `p_value`, `fdr_q_value`, `class_fdr` (EPSG:4326).

## 6. Event study (Cyclone Biparjoy)
For month-of-event `m`, compute `Δ_y = mean(anomaly in [m, m+post)) − mean(anomaly in [m−pre, m))` for the event year and for every other year; anomalies are relative to the monthly climatology excluding the event year. The event year's percentile within the placebo distribution is reported. This is a screen for unusual change, **not attribution**: rainfall timing, monsoon strength and land-cover state are not controlled, and the text says so.

## 7. MODIS vs Landsat
Annual peak-season (Sep–Oct) MODIS NDVI vs Landsat Sep–Oct composite NDVI: Pearson (CI), Spearman, and separate trend tests. This asks whether MODIS greening is also seen at 30 m; it does not discriminate species. Species classification was **not attempted**: it would need labelled field points, multi-temporal/multi-band features and an independent accuracy assessment, none of which exist in this project.

## 8. Reproducibility
Computations are deterministic functions of the stored series. Results are cached by (file mtime, parameters). Exports record dataset provenance and timestamps. The synthetic generator uses a fixed seed.

## 9. Validation performed (see `docs/TEST_RESULTS.md`)
Scale factors, fill values, K→°C, mm/hr→mm/month (incl. leap February), QA bit decoding, ET composite→month identity, MK/HR vs `pymannkendall`, Sen slope with gaps, OLS vs `scipy.stats.linregress`, BH vs manual computation, pixel vs scalar MK, FDR behaviour under null data, GeoTIFF round-trip, seasonal aggregation coverage rules, event-study sensitivity/specificity, and end-to-end rainfall-adjusted recovery of a planted trend (and of a rain-only series giving no residual trend).

## 10. Final-phase methods
- **Rann-water masking.** Pixels with long-term JRC surface-water occurrence ≥ 10% (default; adjustable 1-100) are removed from every band before pixel statistics. The threshold is a documented analyst choice, not a property of the data. The mask raster must share the stack's grid; otherwise it is resampled (nearest) and the response says so.
- **Seasonal NDVI.** Summer (Mar-May), monsoon, peak (Sep-Oct), post-monsoon and winter aggregates are available everywhere; dry-season NDVI can be controlled for the *previous* monsoon's rainfall (`rain_season=prev_monsoon`).
- **Dry-season persistence indicator (exploratory).** ratio = summer NDVI / monsoon NDVI (monsoon ≥ 0.05, capped at 2) per pixel and year; pixel trend with BH-FDR. It cannot separate *Prosopis* from other perennial or groundwater-fed vegetation. Validation requires field labels: class distributions and pairwise ROC-AUC with bootstrap CIs, reported only for classes with ≥ 10 valid points. **No labels exist in this project; no classification or accuracy claim is made.**
- **MODIS vs Landsat agreement.** Landsat pixel slopes and classes are block-averaged onto the MODIS grid; Spearman ρ, sign agreement, and sign agreement among jointly FDR-significant pixels are reported.
- **Salinity.** SI1 is a spectral proxy. Validation: Spearman ρ with Fisher-type CI against measured EC at ≥ 10 points; otherwise the proxy is reported as unvalidated.
- **Groundwater.** CSV validation (dates, depth 0-300 m, duplicates, step-change detection). Multi-well aggregate = mean of per-well anomalies + grand mean. Per-well Mann-Kendall/Sen on annual means with BH-FDR across wells. Increasing depth = deepening water table.
- **Cyclone Biparjoy.** Placebo-year event study; plus a rainfall-adjusted version: deseasonalised response regressed on 3-month rainfall anomalies using non-event years only, then the same event study on the residuals. If the unusual change vanishes after adjustment, rainfall timing is the more parsimonious explanation. No attribution is made.
- **Multi-variable comparison.** Pearson and Spearman matrices with BH-adjusted p-values across pairs; partial correlation (OLS residualisation); OLS with VIF (>5 flagged); leave-one-out cross-validated R² via PRESS (exact for OLS); lagged correlations (±2 years; interpret cautiously because many lags are examined); coincident |z| > 2 anomalies. Predictor count is limited to n/5.
- **Raster QC.** EPSG:4326, north-up, non-rotated, near-square pixels, extent covering the region, band descriptions carrying strictly increasing years, non-empty data. Failures block use with a clear error.
