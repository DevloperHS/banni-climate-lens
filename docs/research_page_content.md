TASK: Restructure the Research page into two audience modes. You already consolidated the judging flow into Research (Overview | Research) and added the map layer switch. Build on that state; do not undo it.

SETUP
- Source of truth for all text: the CONTENT section at the end of this message. First save it verbatim as docs/research_page_content.md (create the docs folder), and include that file in the first commit.
- Create a new branch from the current HEAD named research-two-modes. Small commits are fine. Do NOT push. After each commit run typecheck, tests and build, and report results.
- Do not change any statistical number. Do not delete routes or pages. Do not touch backend/app/science or data/. Keep the PDF, GeoJSON, GeoTIFF and CSV export links working.

1. MODE TOGGLE (top of the Research page)
   Two buttons: "Researcher / Environmental scientist" and "Student / Local community". Replace the old 4-option "Explain for" dropdown and its Quick summary. Default = Researcher. Remember the choice in localStorage (wrapped in try/catch; page must work without it).

2. RESEARCHER MODE (formal register)
   Order:
   a. Research question as a highlighted block: "What is the major driver of the 2001-2024 greening of the Banni Grasslands, and does satellite evidence show a water deficit associated with it?" with the 4 sub-questions Q1-Q4.
   b. MAP (hero block, mandatory, directly after the question).
   c. Study area and data table.
   d. Methods (8 steps).
   e. Results table.
   f. Outputs: CSV / data download buttons (use the existing export endpoints: annual NDVI + rain CSV, water CSV, pixel-trend GeoTIFF, report PDF). If an export does not exist, show the button disabled with a tooltip and list it in your reply. Do not fake a file.
   g. Related published work table + "Why our results differ" (5 points).
   h. Limitations (7 items), then the callout "What this work achieves".
   i. "What would settle it".
   j. References: exactly the 6 entries in the file, with working links. Do not add references. Reference 1 is a conference abstract, reference 3 is a news report about the study and reference 6 is a secondary source: keep those labels.
   Keep the existing full report iframe below as "Full research report" and keep the report details accordion at the bottom.

3. STUDENT / LOCAL MODE (plain English)
   Order: MAP (same component, simple caption) -> the existing visual methodology explainer (6 visual steps + "What this study cannot tell you") -> new section "7 Output: what we found" -> new section "8 Impact: what this can change" -> closing line: "Banni is greening more than rain can explain. We know how much. We do not yet know why."
   Use the text from the file for sections 7 and 8, word for word.

4. MAP IMAGES (static fallbacks in frontend/public/img/)
   Expected files: trend-map.png, land-cover.png, before-2001.png, after-2024.png.
   - The 2001 vs 2024 comparison now uses TWO images (before-2001.png and after-2024.png) shown side by side, each with a caption: "Landsat 7, Sep 2001-Jan 2002" and "Landsat 8/9, Sep 2024-Jan 2025". Update any code or placeholder that expected before-after-2001-2024.png.
   - Show the live Leaflet map when the API is online, and the static image when it is offline or fails. If a file is missing, show the placeholder "image to be added" and list the missing file names in your reply. Never generate or invent an image.
   - Add alt text to every image and a source line (MODIS MOD13Q1 / MCD12Q1, Landsat; analysis rectangle 68.80-69.95 E, 23.20-23.95 N, about 9,770 sq km, not the exact Banni polygon, which is commonly cited as about 2,618 sq km).
   - Land-cover image needs a small legend: shrubland, savanna, grassland, barren, water.

5. NUMBERS
   Every number must come from the app's API response or from the values written in docs/research_page_content.md. Prefer API values where they exist (Hamed-Rao p-values, slopes, R-squared, Durbin-Watson). Where a number is only in the file (for example the GRACE p = 0.21, the permutation count, the dry-season p), show it from the file and list all such numbers in your reply. Never invent a value to fill a gap. Show Durbin-Watson only once, from the app's diagnostics. Use the method label the app reports for each p-value: Hamed-Rao for the NDVI and residual trends; the rainfall trend is a plain Mann-Kendall and must stay labelled as such. Never present a plain Mann-Kendall p-value as Hamed-Rao.
   AREA: search the whole frontend (pages, components, public/*.html) for '2,618', '2618' and 'sq km'. The analysis rectangle is about 9,770 sq km; 2,618 sq km is the Banni grassland itself. Make every statement consistent with the file, and list each place you changed.
   Keep 66/34 (share of the greening trend) clearly separate from R-squared = 0.83 (share of year-to-year variance).

6. MOBILE
   Tables scroll horizontally inside a wrapper; toggle buttons wrap; the map has a minimum height of 280px; the two before/after images stack on narrow screens.

7. WORDING
   Prosopis, groundwater and salinity stay "hypothesis" / "not established". Do not state that Prosopis causes the greening or the drying. Do not rewrite the Research Report iframe text.

8. REPORT BACK
   Give: branch name, commit list, typecheck/test/build results, files changed, numbers taken from the file rather than the API, missing images, disabled export buttons, and anything you could not implement with the reason. Show diffs as File | Line | Current | Should be.


==================== CONTENT (save verbatim as docs/research_page_content.md) ====================

# RESEARCH PAGE CONTENT (two modes)

Toggle at top of the Research page: **[ Researcher / Environmental scientist ]  [ Student / Local community ]**
Both modes use the same numbers (one data source). Wording rule: Prosopis, groundwater, salinity = hypothesis.

---

# MODE 1: RESEARCHER / ENVIRONMENTAL SCIENTIST

## 1. Research question

**What is the major driver of the 2001-2024 greening of the Banni Grasslands, and does satellite evidence show a water deficit associated with it?**

Sub-questions:
- Q1. Does monsoon rainfall explain the greening?
- Q2. After rainfall is removed, does a significant residual trend remain?
- Q3. Do independent water variables (ET, soil moisture, GRACE terrestrial water storage, surface temperature) show a coherent signal of water stress?
- Q4. Can the cause of the residual be identified from satellite data alone?

## 2. Study area and data

Analysis window 68.80-69.95 E, 23.20-23.95 N: a rectangle of about 9,770 sq km (computed), not the exact Banni polygon. The Banni grassland itself is commonly cited as about 2,618 sq km (reference 6), so the rectangle is roughly 3.7 times larger and part of it lies outside the grassland. n = 24 annual values (2001-2024).

| Variable | Product | Resolution | Role |
|---|---|---|---|
| Vegetation greenness (NDVI, EVI) | MODIS MOD13Q1 v6.1 (Terra) and Aqua cross-check | 250 m, 16-day | Response variable |
| Rainfall | GPM IMERG Monthly V07 | ~11 km | Explanatory variable |
| Evapotranspiration | MODIS MOD16A2GF | 500 m, 8-day | Water use (partly NDVI-derived) |
| Soil moisture | GLDAS-2.1 Noah | ~28 km model | Root-zone and surface moisture |
| Land surface temperature | MODIS MOD11A2 | 1 km | Day and night |
| Terrestrial water storage | GRACE JPL mascons | 3 degrees | Regional groundwater context |
| Land cover | MODIS MCD12Q1 v6.1 | 500 m | Grassland / shrubland / savanna shares |

## 3. Methods

1. **Aggregation.** Monsoon (Jun-Sep) NDVI and rainfall per year; annual and dry-season (Mar-May) series for cross-checks.
2. **Trend tests.** Mann-Kendall with Hamed-Rao autocorrelation correction for the NDVI and residual trends; Sen's slope. Where a plain Mann-Kendall p-value is shown (the rainfall trend), it is labelled as such.
3. **RESTREND (residual trend) analysis.** Regress monsoon NDVI on monsoon rainfall (OLS), then test the residuals for a monotonic trend over time. A second model, NDVI ~ rain + year, confirms the year term.
4. **Sensitivity analyses.** Sensor (Terra vs Aqua), index (NDVI vs EVI), rainfall formulation, analysis window; influential-year check (Cook's D).
5. **Dry-season test.** Same RESTREND procedure on Mar-May NDVI, when annual grasses are senescent and evergreen woody cover dominates the signal.
6. **Water variables.** ET, soil moisture, LST and GRACE tested for trend; ET re-tested with rainfall periods matched to the ET window.
7. **Spatial analysis.** Pixel-wise Sen slope with Benjamini-Hochberg FDR correction; only FDR-significant pixels are mapped.
8. **Chance test.** The 24 years are replayed 1,000 times under a no-trend assumption; 6 of the 1,000 replays produced a rise as strong as the one observed.

## 4. Results

| Test | Result | Reading |
|---|---|---|
| Annual NDVI trend | Sen slope +0.0047/yr, Hamed-Rao p = 2.8e-05 | Greening is real |
| Monsoon rainfall trend | p = 0.056 (Mann-Kendall), +15.7 mm/yr | Not significant at 5% |
| NDVI vs rain | r = +0.91, R-squared = 0.83 | Rain explains most year-to-year variance |
| Residual trend (monsoon) | +0.0017 NDVI/yr, p = 0.0059; NDVI ~ rain + year, p = 0.0004 | Greening not explained by rain |
| Residual trend (dry season Mar-May) | rising, p = approx 0.002 | Consistent with year-round green cover, not proof |
| ET (rainfall periods matched) | residual rising; second method p = 0.19 | Inconclusive |
| Soil moisture | no trend | No evidence of drying |
| LST | day cooling p = 0.009; night warming p = 0.004 | Observation only |
| GRACE TWS | p = 0.21 (3 degree cell) | Not significant; far coarser than Banni |

Attribution note: rain accounts for about 66% of the observed greening trend; about 34% remains after rainfall is removed. This is a different quantity from R-squared = 0.83 (share of year-to-year variance). Do not equate them.

## 5. Outputs

- **Map:** pixel NDVI trend (Sen slope, FDR-significant pixels only), land-cover shares, 2001 vs 2024 comparison; analysis rectangle shown on the basemap.
- **CSV / data exports:** annual NDVI + rainfall series; annual water series (ET, soil moisture, rainfall); pixel trend raster; report PDF. These exports let a reader reproduce the headline numbers.

## 6. Candidate explanations, published work, and why we do not name a cause

Four candidate explanations for the residual greening need ground data: shrub invasion (for example Prosopis juliflora, which is invasive, evergreen and deep-rooted), groundwater abstraction, altered surface water, and salinity. Prosopis is the one most discussed in the Banni literature. The satellite index cannot separate shrub from grass: both register as the same NDVI, so none of the four can be confirmed from orbit.

**Related published work and how it compares**

| Study | Approach | Finding | Relation to ours |
|---|---|---|---|
| Tundia, Rao and Shastri (IIT Bombay), EGU General Assembly 2022, EGU22-12254 (conference abstract) | GRACE storage change + hydrological model + remote-sensing ET + groundwater table, Banni, 2002-2017 | Groundwater depletion; authors attribute it to Prosopis after finding soil moisture, surface water and biomass did not contribute significantly; they note the record is short | Same direction as our hypothesis. We could not reproduce a significant GRACE trend (p = 0.21). |
| Shiferaw et al. 2021, Scientific Reports 11:2688 (Afar, Ethiopia) | Sap flow and eddy covariance, upscaled by cover map | Evergreen Prosopis uses groundwater year-round; stand ET about 3.7 mm/day; upscaled about 279 mm/yr | Supports the mechanism (deep-rooted, evergreen, dry-season water use) in another region. Does not prove it for Banni. |
| Nerlekar, Misher, Hiremath et al. (ATREE and Sahjeevan), 2021, reported by Mongabay | Field plots in Banni: mechanical removal vs lopping | Mechanical removal raised native plant diversity and cover | Ecological and livelihood context; did not measure water. |

**Why our satellite results differ from a "Prosopis is drying the land" finding**
1. **Different observable.** Greening (NDVI) is not drying. An evergreen deep-rooted shrub can raise NDVI while drawing groundwater; both can be true together. NDVI cannot tell which plant is responsible.
2. **Different time window.** The IIT Bombay analysis covers 2002-2017; ours uses the full available record to 2024.
3. **Different data.** They combined GRACE with a hydrological model, ET and groundwater-table data; we tested GRACE (JPL mascon), GLDAS soil moisture and MODIS ET as separate series, without a combined water balance and without well records.
4. **Scale.** The GRACE cell is 3 degrees, far larger than Banni, so a local signal can be diluted.
5. **Attribution by elimination.** Attributing a storage decline to one species by excluding other terms is not a direct measurement, and the authors flag the short record.

We therefore treat the water-deficit link as **not established**: consistent with the literature, not confirmed by our data.

## 7. Limitations

1. Rectangle (about 9,770 sq km), not the Banni polygon (about 2,618 sq km): much of the measured area lies outside the grassland.
2. 24 annual values: enough to see a direction, not to pin a cause.
3. NDVI measures greenness, not species; shrub and grass are indistinguishable.
4. No ground data (wells, soil samples, field surveys, dam records).
5. MODIS ET depends partly on NDVI; GLDAS is a ~28 km model; GRACE is 3 degrees.
6. Residual autocorrelation is suggested (Durbin-Watson reported by the app); Hamed-Rao and HAC results are preferred over OLS p-values.
7. One influential year (2023, Cook's D above 4/n).

**What this work achieves.** Within these limits, the study establishes a rainfall-independent greening of known size (+0.0017 NDVI/yr, p = 0.006) and turns it into a sharply posed, testable question: *which species is responsible, and is it drawing groundwater?*

## 8. What would settle it

- CGWB / India-WRIS well water-level records (pre- and post-monsoon) for Kachchh.
- A Prosopis-versus-grass map from high-resolution imagery with field training points, then NDVI trends per class.
- Sap-flow or eddy-covariance measurements in Banni.

## 9. References

1. Tundia, K., Rao, A., Shastri, Y. (2022). Satellite based assessment of groundwater depletion by the invasive tree species Prosopis juliflora in a semi-arid region of Gujarat, India. EGU General Assembly 2022, EGU22-12254. https://meetingorganizer.copernicus.org/EGU22/EGU22-12254.html
2. Shiferaw, H., Alamirew, T., Dzikiti, S., Bewket, W., Zeleke, G., Schaffner, U. (2021). Water use of Prosopis juliflora and its impacts on catchment water budget and rural livelihoods in Afar Region, Ethiopia. Scientific Reports 11, 2688. https://pmc.ncbi.nlm.nih.gov/articles/PMC7846740
3. Nerlekar, A., Misher, C., Hiremath, A. et al. (2021). Mechanical removal vs lopping of Prosopis juliflora in Banni (ATREE and Sahjeevan); news report: https://india.mongabay.com/2021/08/large-scale-removal-of-bannis-invasive-mad-tree-prosopis-is-not-the-solution-study/
4. Pasha et al. (2014), cited in reference 1: +42.9% area under Prosopis cover in Kutch, 1977-2011 (secondary citation).
5. Data: MODIS MOD13Q1, MOD16A2GF, MOD11A2, MCD12Q1 v6.1; GPM IMERG V07; GLDAS-2.1 Noah; GRACE JPL mascons (NASA, via Google Earth Engine).
6. Banni grassland area (about 2,618 sq km, stated as "2,618 km"): GKToday, Banni grassland, https://www.gktoday.in/banni-grassland (secondary source; the rectangle area is our own calculation).

---

# MODE 2: STUDENT / LOCAL COMMUNITY (simple)

Keep the existing 6 visual steps (what the satellite measures, rain and greenness U-tube, take the rain away, the leftover tips upward, random chance test, eight suspects) and the box "What this study cannot tell you". Then add the two sections below.

## 7. Output: what we found

- **Banni is getting greener.** Satellite pictures from 2001 to 2024 show the land becoming greener over the years.
- **Rain explains most of it.** In wet years Banni is greener, in dry years less so (the link is strong: 0.91 out of 1).
- **But rain is not the whole story.** About two thirds of the greening is explained by rain. About one third is left over, and that leftover keeps rising year after year. We replayed the 24 years 1,000 times as if nothing but rain were acting; only 6 of those replays showed a rise this strong, so luck is an unlikely explanation.
- **It shows in the dry season too.** Even in March to May, when grass is dry, the land still looks greener over the years.
- **The map shows where.** Coloured patches mark where the greening is clear enough to count.
- **What we did not find.** We did not find proof that the water under the ground is falling. Satellites cannot see that clearly here.

## 8. Impact: what this can change

- **For herders and villages.** Green on a satellite picture is not always grass for animals. A thicket of Prosopis looks as green as a pasture from space. So "greener" does not automatically mean "better grazing".
- **For planners.** Rainfall alone does not explain the change, so rainfall-based forecasts of grass may miss something. The map shows where to look first.
- **For water.** Some studies say Prosopis draws a lot of groundwater. Our satellite data could not confirm that. The people who know best are those who use the wells. Your observations (water levels, grass, shrubs) are the missing evidence.
- **For decisions about Prosopis.** Many families also use Prosopis (charcoal, fuel). Any decision should be made with local people, using field checks, not from a satellite picture alone.
- **What happens next.** Check well records, map where Prosopis actually grows, and measure its water use on the ground.

**One line to remember:** Banni is greening more than rain can explain. We know how much. We do not yet know why.