"""Research report generator. Every number, table, chart and map is computed from the stored series/rasters at
generation time; nothing is templated text with embedded results. Sections that lack data are omitted and listed in the
manifest (and in the report) with the reason."""
from __future__ import annotations
import io
from datetime import datetime, timezone

import numpy as np

from . import services as svc
from .core import store
from .core.catalog import CATALOG
from .core.regions import get_region

REFERENCES = [
    "Mann, H.B. (1945). Nonparametric tests against trend. Econometrica 13, 245-259.",
    "Kendall, M.G. (1975). Rank Correlation Methods (4th ed.). Charles Griffin, London.",
    "Sen, P.K. (1968). Estimates of the regression coefficient based on Kendall's tau. J. Am. Stat. Assoc. 63, 1379-1389.",
    "Hamed, K.H. and Rao, A.R. (1998). A modified Mann-Kendall trend test for autocorrelated data. J. Hydrol. 204, 182-196.",
    "Benjamini, Y. and Hochberg, Y. (1995). Controlling the false discovery rate. J. R. Stat. Soc. B 57, 289-300.",
    "Newey, W.K. and West, K.D. (1987). A simple, positive semi-definite, heteroskedasticity and autocorrelation consistent covariance matrix. Econometrica 55, 703-708.",
    "Cook, R.D. (1977). Detection of influential observations in linear regression. Technometrics 19, 15-18.",
    "Didan, K. (2021). MODIS/Terra Vegetation Indices 16-Day L3 Global 250m SIN Grid V061 (MOD13Q1). NASA LP DAAC. doi:10.5067/MODIS/MOD13Q1.061",
    "Huffman, G.J. et al. (2023). GPM IMERG Final Precipitation L3 1 month 0.1 degree x 0.1 degree V07 (GPM_3IMERGM). NASA GES DISC. doi:10.5067/GPM/IMERGM/3B-MONTH/07",
    "Wan, Z., Hook, S. and Hulley, G. (2021). MODIS/Terra Land Surface Temperature/Emissivity 8-Day L3 Global 1km SIN Grid V061 (MOD11A2). NASA LP DAAC. doi:10.5067/MODIS/MOD11A2.061",
    "Running, S., Mu, Q. and Zhao, M. (2021). MODIS/Terra Net Evapotranspiration Gap-Filled 8-Day L4 Global 500m SIN Grid V061 (MOD16A2GF). NASA LP DAAC. doi:10.5067/MODIS/MOD16A2GF.061",
    "Rodell, M. et al. (2004). The Global Land Data Assimilation System. Bull. Am. Meteorol. Soc. 85, 381-394.",
    "Pekel, J.-F., Cottam, A., Gorelick, N. and Belward, A.S. (2016). High-resolution mapping of global surface water and its long-term changes. Nature 540, 418-422.",
    "Gorelick, N. et al. (2017). Google Earth Engine: planetary-scale geospatial analysis for everyone. Remote Sens. Environ. 202, 18-27.",
]

KEY_TRENDS = [("ndvi", "annual"), ("ndvi", "monsoon"), ("ndvi", "summer"), ("ndvi_nowater", "monsoon"), ("ndvi_landsat", "annual"), ("precip", "monsoon"),
              ("precip", "annual"), ("lst_day", "annual"), ("lst_night", "annual"), ("et", "annual"), ("sm_root", "annual"), ("sm_surface", "annual"),
              ("water_extent", "annual"), ("salinity_index", "annual"), ("groundwater", "annual")]


def manifest(region: str, source: str, start=None, end=None) -> dict:
    """What a report would contain for this region/source, section by section."""
    have = set(store.list_series(source, region))
    rasters = store.list_rasters(source, region)
    secs = [
        {"id": "summary", "title": "Findings summary", "available": "ndvi" in have or "precip" in have, "needs": "NDVI or rainfall series"},
        {"id": "data", "title": "Datasets and provenance", "available": bool(have), "needs": "any processed series"},
        {"id": "trends", "title": "Trend estimates (p-values, confidence intervals)", "available": bool(have), "needs": "any processed series"},
        {"id": "adjusted", "title": "Rainfall-adjusted analysis", "available": {"ndvi", "precip"} <= have, "needs": "ndvi + precip series"},
        {"id": "handover", "title": "Reproduction of the research handover", "available": {"ndvi", "precip"} <= have, "needs": "ndvi + precip series"},
        {"id": "maps", "title": "Maps (pixel trends, layers)", "available": any(s != "static" for _, s in rasters), "needs": "raster stacks (stack jobs)"},
        {"id": "quality", "title": "Data quality", "available": bool(have), "needs": "any processed series"},
    ]
    return {"region": region, "source": source, "sections": secs, "ready": any(s["available"] for s in secs[:3]),
            "synthetic": any((store.load_series(source, region, k) or {}).get("kind") == "synthetic" for k in have)}


def _figs():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def _png(fig) -> bytes:
    b = io.BytesIO(); fig.savefig(b, format="png", dpi=150, bbox_inches="tight"); return b.getvalue()


def build_pdf(region_id: str, source: str, start=None, end=None, include_maps: bool = True) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    r = svc.check(region_id)
    ins = svc.build_insights(region_id, source, start, end)
    if not ins["findings"] and not store.list_series(source, region_id):
        raise svc.AppError("no_data", "Nothing to report: no processed series for this region/source.", 404)
    syn = bool(ins.get("synthetic")) or manifest(region_id, source)["synthetic"]
    ss = getSampleStyleSheet()
    sm = ss["BodyText"].clone("sm", fontSize=8, leading=10)
    h2, h3 = ss["Heading2"], ss["Heading3"]
    story: list = []
    omitted: list[str] = []

    def table(rows, widths=None, fs=7.5):
        t = Table(rows, repeatRows=1, colWidths=widths, hAlign="LEFT")
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), .3, colors.grey), ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                               ("FONTSIZE", (0, 0), (-1, -1), fs), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        return t

    def P(x, st=sm): return Paragraph(str(x).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"), st)

    # ---- cover
    g = r["geometry"]
    story += [Paragraph("GlobalClimateLens - Research Report", ss["Title"]),
              Paragraph(f"{r['name']} &middot; generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}", ss["Normal"]), Spacer(1, 6)]
    if syn:
        story.append(Paragraph("<font color='#b00020'><b>SYNTHETIC SAMPLE DATA - results below come from a toy model for software testing and have NO scientific meaning.</b></font>", ss["BodyText"]))
    per = f"{start or r['study_period']['start']}-{end or r['study_period']['end']}"
    story += [Paragraph("1. Study region and period", h2),
              table([["Region", r["name"]], ["Study period", per],
                     ["Analysis geometry", f"{g['id']} ({g['kind']}), {r['computed_bbox_area_km2']:,.0f} km2 (WGS84 ellipsoidal)"],
                     ["Geometry source", g.get("source", "")],
                     ["Bounding box", f"{r['bbox']['south']}-{r['bbox']['north']} N, {r['bbox']['west']}-{r['bbox']['east']} E"],
                     ["Data source", f"{source} ({'synthetic' if syn else 'observed / user-supplied'})"]], [4 * cm, 12 * cm]),
              Spacer(1, 4)]
    if g["kind"] != "polygon":
        story.append(P(f"Note: the analysis geometry is a rectangle, not the Banni grassland boundary. {r.get('reference_area_note', '')}"))
    story += [Paragraph("Research question", h3), P(ins.get("question", ""), ss["BodyText"])]

    # ---- findings
    if ins["findings"]:
        story.append(Paragraph("2. Findings summary (computed from the data below)", h2))
        for f in ins["findings"]:
            story += [Paragraph(f"<b>{f['title']}</b>", ss["BodyText"]), P(f["statement"], ss["BodyText"]), Spacer(1, 3)]

    # ---- datasets and provenance
    story += [Paragraph("3. Datasets and provenance", h2)]
    rows = [["Variable", "Dataset", "Provider", "Resolution", "Unit", "Scale", "Quality filter", "Period", "Retrieved", "Kind"]]
    for key in store.list_series(source, region_id):
        rec = store.load_series(source, region_id, key); pv = rec["provenance"]
        rows.append([P(x) for x in (key, pv.get("ee_id") or "user upload", pv.get("provider"), f"{pv.get('spatial_resolution')} / {pv.get('temporal_resolution')}",
                                    pv.get("unit"), pv.get("scale_factor"), pv.get("quality_filter"), pv.get("processing_period"), pv.get("retrieval_date") or "n/a", rec["kind"])])
    story.append(table(rows, [1.5*cm, 2.8*cm, 1.6*cm, 2.0*cm, 1.7*cm, 1.3*cm, 3.3*cm, 1.3*cm, 1.4*cm, 1.2*cm], 6.5))

    # ---- methodology
    story += [Paragraph("4. Processing and statistical methodology", h2),
              P("Processing: monthly values are built from product composites (NDVI, LST: mean of valid composites; ET: composite totals converted to daily rates and scaled to the month; "
                "IMERG: mm/hr x 24 x days). Seasons: summer MAM, monsoon JJAS, post-monsoon ON, winter DJF. Sums require complete seasons; means require >=75% of months. "
                "Missing months are never interpolated.", ss["BodyText"]),
              P("Statistics: Mann-Kendall and Hamed-Rao modified Mann-Kendall tests (two-sided, alpha=0.05), Sen's slope with a Sen/Gilbert 95% confidence interval; OLS regression with t-based and "
                "Newey-West (HAC) intervals and residual diagnostics (Durbin-Watson, Ljung-Box, Shapiro-Wilk, Breusch-Pagan, Cook's distance); Benjamini-Hochberg false-discovery-rate control for pixel-wise "
                "and multiple-pair tests. Correlation and regression describe association, not causation.", ss["BodyText"])]

    # ---- trends
    story.append(Paragraph("5. Trend estimates", h2))
    rows = [["Variable", "Season", "n", "Period", "Test", "Z", "p", "Sen slope / yr", "95% CI", "Direction"]]
    first_ndvi = None
    for key, agg in KEY_TRENDS:
        try:
            t = svc.trend_payload(region_id, key, source, agg, start, end, 0.05)
        except svc.AppError:
            continue
        x = t["result"]; p = x[x["recommended"]]
        if key == "ndvi" and agg == "annual":
            first_ndvi = x
        rows.append([key, agg, p["n"], t["meta"]["period"], p["test"].replace("modified Mann-Kendall", "mod. MK"), f"{p['z']:.2f}", f"{p['p']:.3g}", f"{p['slope']:+.4g} {svc.short_unit(key)}",
                     f"[{p['slope_ci_low']:+.3g}, {p['slope_ci_high']:+.3g}]", p["direction"]])
    if len(rows) > 1:
        story += [table([[P(c) for c in row] for row in rows]), Spacer(1, 4)]
    else:
        omitted.append("Trend table (no series long enough)")
    plt = _figs()
    if first_ndvi:
        fig, ax = plt.subplots(figsize=(6.5, 2.6))
        ax.plot(first_ndvi["years"], first_ndvi["values"], "o-", color="#2f8f5b", ms=3, label="annual mean NDVI")
        ax.plot(first_ndvi["years"], first_ndvi["line"], "--", color="#555", label="Sen slope")
        ax.set_ylabel("NDVI"); ax.legend(fontsize=7); ax.grid(alpha=.3); ax.set_title("Annual NDVI" + ("  [SYNTHETIC]" if syn else ""), fontsize=9)
        story.append(Image(io.BytesIO(_png(fig)), width=15 * cm, height=6 * cm, kind="proportional")); plt.close(fig)

    # ---- rainfall-adjusted
    adj = None
    try:
        adj = svc.rainfall_adjusted_payload(region_id, source, "ndvi", "monsoon", start, end)["result"]
    except svc.AppError as e:
        omitted.append(f"Rainfall-adjusted analysis ({e.message})")
    if adj:
        story.append(Paragraph("6. Rainfall-adjusted vegetation analysis", h2))
        story.append(P(adj["verdict"]["text"], ss["BodyText"]))
        fig, ax = plt.subplots(1, 2, figsize=(6.5, 2.6))
        ax[0].scatter(adj["rainfall"], adj["ndvi"], s=14, color="#2b6cb0"); ax[0].set_xlabel("Monsoon rainfall (mm)"); ax[0].set_ylabel("Monsoon NDVI")
        ax[1].bar(adj["years"], adj["residuals"], color=["#2f8f5b" if v >= 0 else "#d95f02" for v in adj["residuals"]]); ax[1].set_title("Residuals", fontsize=8)
        for a in ax: a.grid(alpha=.3)
        fig.tight_layout(); story.append(Image(io.BytesIO(_png(fig)), width=15 * cm, height=6 * cm, kind="proportional")); plt.close(fig)
        rows = [["Term", "Estimate", "95% CI", "p", "p (HAC)"]] + [[c["name"], f"{c['coef']:.4g}", f"[{c['ci_low']:.3g}, {c['ci_high']:.3g}]", f"{c['p']:.3g}", f"{c['hac_p']:.3g}"] for c in adj["regression"]["coefficients"]]
        story += [P(f"OLS NDVI ~ rainfall: R2={adj['regression']['r2']:.3f}, n={adj['n']}", ss["BodyText"]), table(rows)]
        rt = adj["residual_trend"]; pk = rt[rt["recommended"]]
        story += [P(f"Residual trend ({pk['test']}): {pk['direction']}, Z={pk['z']:.2f}, p={pk['p']:.3g}, Sen slope {pk['slope']:+.4g} NDVI/yr (95% CI {pk['slope_ci_low']:+.3g} to {pk['slope_ci_high']:+.3g}).", ss["BodyText"]),
                  Paragraph("Sensitivity analyses", h3)]
        story += [P(f"- {s['name']}: {s['direction']} (n={s['n']})") for s in adj["sensitivity"]]
        story += [Paragraph("Caveats from diagnostics", h3)] + [P(f"- {c}") for c in adj["caveats"]]

    # ---- handover reproduction
    try:
        hv = svc.handover_payload(region_id, source, start, end)["result"]
        story.append(Paragraph("7. Reproduction of the research handover", h2))
        rows = [["Quantity", "Handover reported", "Computed here", "Status"]]
        for x in hv["rows"]:
            rp, c = x["reported"], x["computed"]
            rs = f"{rp.get('value')}" if "value" in rp else f"{rp.get('direction')}; p={rp.get('p')}; slope={rp.get('slope')}"
            cs = "n/a" if c is None else (f"{c:.5f}" if isinstance(c, float) else f"{c['direction']}; p={c['p']:.4g}; slope={c['slope']:.4g}")
            rows.append([P(x["label"]), P(rs), P(cs), x["status"]])
        story += [table(rows, [6 * cm, 4.5 * cm, 4.5 * cm, 2 * cm]), P("Statuses are never adjusted to match: " + hv["notes"][0] if hv["notes"] else "")]
    except svc.AppError:
        omitted.append("Handover reproduction (needs ndvi + precip)")

    # ---- maps
    if include_maps:
        try:
            from .routers.analysis import _pixel, _stack, LAYER_META
            from .routers.extra import figure_png
            info = _stack(source, region_id, "ndvi", "annual")
            res, _, yrs, _ = _pixel(region_id, source, "ndvi", "annual", start, end, 0.05)
            b = {"south": info["bounds"].bottom, "west": info["bounds"].left, "north": info["bounds"].top, "east": info["bounds"].right}
            syn_r = info["tags"].get("kind") == "synthetic"
            foot = f"{r['name']} | geometry {g['id']} | EPSG:4326 | source {source}"
            story += [PageBreak(), Paragraph("8. Maps", h2)]
            story.append(Image(io.BytesIO(figure_png(res["cls"], b, f"NDVI significant pixel trends {int(yrs.min())}-{int(yrs.max())} (BH-FDR q=0.05)", None, -1, 1, "", foot, syn_r, True)),
                               width=13 * cm, height=10 * cm, kind="proportional"))
            from .science import pixel as PX
            summ = PX.summarise(res)
            story.append(P(f"{summ['pixels_tested']:,} pixels tested; after FDR control {summ['significant_increase_fdr']:,} significant increases and {summ['significant_decrease_fdr']:,} decreases "
                           f"(uncorrected p<0.05 would give {summ['significant_increase_uncorrected'] + summ['significant_decrease_uncorrected']:,}). {summ['note']}"))
            allv = info["data"][np.isfinite(info["data"])]
            story.append(Image(io.BytesIO(figure_png(np.nanmean(info["data"], axis=0), b, "NDVI annual mean (all years)", LAYER_META["ndvi"][2], float(np.percentile(allv, 2)), float(np.percentile(allv, 98)), "NDVI", foot, syn_r)),
                               width=13 * cm, height=10 * cm, kind="proportional"))
        except svc.AppError as e:
            omitted.append(f"Maps ({e.message})")
        except Exception as e:   # a failing map must not produce a silently wrong report
            omitted.append(f"Maps (rendering failed: {type(e).__name__})")

    # ---- quality
    story.append(Paragraph("9. Data quality", h2))
    rows = [["Series", "Valid / expected months", "Completeness", "Missing", "Flags"]]
    for key in store.list_series(source, region_id):
        try:
            q = svc.quality_report(region_id, key, source)["result"]
            rows.append([key, f"{q['valid_months']} / {q['expected_months']}", f"{q['completeness_pct']}%", q["missing_months"], P("; ".join(q["flags"]) or "none")])
        except svc.AppError:
            pass
    story.append(table(rows))

    # ---- interpretation, limitations, omissions, references
    story += [Paragraph("10. Interpretation and limitations", h2),
              P("Trends describe changes in satellite-derived quantities. They do not identify causes, vegetation species or groundwater change. A positive rainfall-adjusted NDVI trend means "
                "greener than rainfall alone predicts; it is not evidence of Prosopis expansion or of grassland recovery. MOD16 ET is a model that uses NDVI/LAI as input; GLDAS soil moisture is a 0.25 degree model; "
                "LST is surface (skin) temperature; salinity indices are unvalidated proxies unless compared with field EC; groundwater claims require measured well levels. "
                "Annual tests have ~24 observations and limited power; non-significance is not proof of no change.", ss["BodyText"])]
    if g["kind"] != "polygon":
        story.append(P("All results refer to the analysis rectangle, which includes non-grassland land. They must not be reported as grassland-only values."))
    if omitted:
        story += [Paragraph("Sections omitted (insufficient data)", h3)] + [P(f"- {o}") for o in omitted]
    story += [Paragraph("11. References", h2)] + [P(f"[{i}] {x}") for i, x in enumerate(REFERENCES, 1)]

    def footer(c, d):
        c.saveState(); c.setFont("Helvetica", 7)
        c.drawString(2 * cm, 1 * cm, f"GlobalClimateLens | {region_id} | source={source}" + (" | SYNTHETIC DATA" if syn else ""))
        c.drawRightString(A4[0] - 2 * cm, 1 * cm, f"Page {d.page}"); c.restoreState()

    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm,
                      title=f"GlobalClimateLens {r['name']}", author="GlobalClimateLens").build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()
