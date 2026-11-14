"""Dataset catalogue: one entry per analysable variable ('series key').

Everything the platform records about a dataset's provenance starts here.
"""
from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class DatasetSpec:
    key: str
    label: str
    group: str            # vegetation | rainfall | temperature | water
    ee_id: str | None
    provider: str
    variable: str
    spatial_resolution: str
    temporal_resolution: str
    unit: str
    scale_factor: str
    quality_filter: str
    reducer: str          # how sub-annual values aggregate: mean | sum
    scale_m: int          # reduction / export scale in metres
    limitations: str


CATALOG: dict[str, DatasetSpec] = {s.key: s for s in [
    DatasetSpec("ndvi", "NDVI (MODIS MOD13Q1)", "vegetation", "MODIS/061/MOD13Q1", "NASA LP DAAC",
                "NDVI", "250 m", "16-day composite", "dimensionless (-1..1)", "0.0001",
                "Handover protocol: no SummaryQA mask (Earth Engine's own fill/valid-range mask only); monthly mean of the composites whose date falls in the month, then regional mean. QA-filtered variant: ndvi_qa",
                "mean", 250,
                "Mixed-pixel greenness index; saturates in dense canopy; cannot identify species. Cloud/snow-flagged composites are NOT removed in this series (handover protocol) - compare ndvi_qa."),
    DatasetSpec("ndvi_qa", "NDVI, QA-filtered (MODIS MOD13Q1)", "vegetation", "MODIS/061/MOD13Q1", "NASA LP DAAC",
                "NDVI", "250 m", "16-day composite", "dimensionless (-1..1)", "0.0001",
                "SummaryQA == 0 (good) per pixel; regional mean per composite; composites assigned to month by midpoint",
                "mean", 250,
                "Sensitivity series. Stricter than the handover; may remove many monsoon pixels."),
    DatasetSpec("ndvi_aqua", "NDVI, Aqua (MODIS MYD13Q1)", "vegetation", "MODIS/061/MYD13Q1", "NASA LP DAAC",
                "NDVI", "250 m", "16-day composite", "dimensionless (-1..1)", "0.0001",
                "Same handover protocol as `ndvi` (no SummaryQA mask; monthly mean of the composites dated in the month, then regional mean)",
                "mean", 250,
                "Cross-sensor check (research brief s.7): the same index from the Aqua satellite (afternoon overpass) instead of Terra. "
                "Record starts 4 Jul 2002, so its trend period is shorter than Terra's. Agreement guards against a single-instrument artefact."),
    DatasetSpec("evi", "EVI (MODIS MOD13Q1)", "vegetation", "MODIS/061/MOD13Q1", "NASA LP DAAC",
                "EVI", "250 m", "16-day composite", "dimensionless (-1..1)", "0.0001",
                "Same handover protocol as `ndvi` (no SummaryQA mask; monthly mean of the composites dated in the month, then regional mean)",
                "mean", 250,
                "Cross-index check (research brief s.7): the Enhanced Vegetation Index from the same product corrects for soil background "
                "and atmosphere and saturates less than NDVI. Like NDVI it measures green cover and cannot identify species."),
    DatasetSpec("ndvi_nowater","NDVI, Rann-water masked (MODIS MOD13Q1)", "vegetation", "MODIS/061/MOD13Q1 + JRC/GSW1_4/GlobalSurfaceWater",
                "NASA LP DAAC + EC JRC", "NDVI; pixels with JRC water occurrence >= 10% removed", "250 m", "16-day composite", "dimensionless (-1..1)", "0.0001",
                "Handover protocol (no SummaryQA) plus removal of pixels whose long-term surface-water occurrence is >= 10% (Rann / seasonal wetland)", "mean", 250,
                "The 10% occurrence threshold is a documented choice (handover p.14 asks for a JRC water mask without a threshold); occurrence covers 1984-2021 only."),
    DatasetSpec("water_extent_mndwi", "Surface-water extent, Landsat 8/9 MNDWI", "water", "LANDSAT/LC08,LC09/C02/T1_L2", "USGS/NASA",
                "MNDWI = (Green - SWIR1)/(Green + SWIR1) > 0", "60 m", "monthly (Landsat 8 from 2013, 9 from 2021)", "km2", "0.0000275 * DN - 0.2",
                "QA_PIXEL cloud/shadow/snow masked; months with <50% clear-pixel coverage dropped", "mean", 60,
                "Covers 2013 onward, so it spans Cyclone Biparjoy (2023) where JRC does not. MNDWI > 0 is a generic threshold; salt crust and wet soil can be misclassified. Not validated for Banni."),
    DatasetSpec("salinity_index", "Salinity proxy: SI1 = sqrt(Green x Red) (Landsat)", "salinity", "LANDSAT/{LT05,LE07,LC08,LC09}/C02/T1_L2", "USGS/NASA",
                "SI1 spectral index (Mar-May dry-season median composite)", "30 m (stacks at 120 m)", "annual dry-season composite", "reflectance (dimensionless)", "0.0000275 * DN - 0.2",
                "QA_PIXEL cloud/shadow/snow masked", "mean", 120,
                "A spectral PROXY from the remote-sensing literature. It responds to bright salt crust but also to bare soil and sand. It is UNVALIDATED for Banni until compared with field EC measurements (upload in Water Resources)."),
    DatasetSpec("water_occurrence", "Surface-water occurrence (JRC GSW, static)", "water", "JRC/GSW1_4/GlobalSurfaceWater", "EC JRC / Google",
                "occurrence (% of valid observations 1984-2021 with water)", "30 m (stack at 250 m)", "static layer", "percent", "1",
                "none", "mean", 250, "Static long-term layer used for masking only; no time series."),
    DatasetSpec("ndvi_landsat", "NDVI (Landsat C2 L2)", "vegetation", "LANDSAT/{LT05,LE07,LC08,LC09}/C02/T1_L2",
                "USGS/NASA", "NDVI from surface reflectance", "30 m", "annual Sep-Oct median composite",
                "dimensionless (-1..1)", "0.0000275 * DN - 0.2",
                "QA_PIXEL: cloud, cloud shadow, dilated cloud, snow masked", "mean", 30,
                "Sensor transitions (TM/ETM+/OLI) need harmonisation; ETM+ SLC-off gaps after 2003; sparse clear-sky scenes."),
    DatasetSpec("precip", "Precipitation (GPM IMERG V07)", "rainfall", "NASA/GPM_L3/IMERG_MONTHLY_V07", "NASA GES DISC",
                "precipitation", "0.1 deg (~11 km)", "monthly", "mm/month (converted from mm/hr)",
                "mm/hr * 24 * days_in_month", "Product-level quality (gauge-calibrated monthly)", "sum", 11132,
                "Coarse relative to the region; satellite-gauge estimates carry bias in arid regions."),
    DatasetSpec("lst_day", "Land surface temperature, day (MOD11A2)", "temperature", "MODIS/061/MOD11A2", "NASA LP DAAC",
                "LST_Day_1km", "1 km", "8-day composite", "deg C (converted from K)", "0.02 (Kelvin)",
                "QC_Day bits0-1 in {0,1}; bits6-7 (LST error) <= 1 (<=2 K)", "mean", 1000,
                "Land SURFACE temperature (skin), not air temperature; clear-sky only; day/night overpass times differ."),
    DatasetSpec("lst_night", "Land surface temperature, night (MOD11A2)", "temperature", "MODIS/061/MOD11A2", "NASA LP DAAC",
                "LST_Night_1km", "1 km", "8-day composite", "deg C (converted from K)", "0.02 (Kelvin)",
                "QC_Night bits0-1 in {0,1}; bits6-7 <= 1", "mean", 1000,
                "Land SURFACE temperature (skin), not air temperature; clear-sky only."),
    DatasetSpec("et", "Evapotranspiration (MOD16A2GF)", "water", "MODIS/061/MOD16A2GF", "NASA LP DAAC / UMT",
                "ET", "500 m", "8-day composite (gap-filled)", "mm/month", "0.1 (kg/m2 per composite)",
                "Fill values (>32700) masked", "sum", 500,
                "Model-derived (Penman-Monteith); driven by reanalysis meteorology and MODIS LAI; low skill in arid land."),
    DatasetSpec("sm_surface", "Surface soil moisture, 0-10 cm (GLDAS Noah)", "water", "NASA/GLDAS/V021/NOAH/G025/T3H",
                "NASA GSFC", "SoilMoi0_10cm_inst", "0.25 deg (~28 km)", "3-hourly", "kg/m2 (~mm of water)", "1",
                "Model output; none applied", "mean", 27830,
                "Modelled, not observed; the 0.25 deg grid is only a few cells across this region."),
    DatasetSpec("sm_root", "Root-zone soil moisture (GLDAS Noah RootMoist)", "water", "NASA/GLDAS/V021/NOAH/G025/T3H",
                "NASA GSFC", "RootMoist_inst", "0.25 deg (~28 km)", "3-hourly",
                "kg/m2 (~mm of water)", "1", "Model output; none applied", "mean", 27830,
                "Modelled, not observed; coarse grid (a few cells over the region); cannot see Prosopis or pumping."),
    DatasetSpec("water_extent", "Surface-water extent (JRC GSW monthly)", "water", "JRC/GSW1_4/MonthlyHistory",
                "EC JRC / Google", "water (class 2)", "30 m", "monthly", "km2", "1",
                "Months with <50% valid-observation coverage dropped", "mean", 30,
                "Optical: cloud gaps; salt crust can be confused. Catalog coverage ends 2022-01-01, so it cannot cover Cyclone Biparjoy (2023)."),
    DatasetSpec("grace_tws", "Total water storage anomaly (GRACE/GRACE-FO JPL mascons, CRI)", "water", "NASA/GRACE/MASS_GRIDS_V04/MASCON_CRI",
                "NASA JPL", "lwe_thickness", "3 deg mascon (0.5 deg grid)", "monthly", "cm liquid water equivalent", "1",
                "Product-level (CRI-filtered mascon solution, recommended by the catalogue for non-expert use)", "mean", 55660,
                "Regional CONTEXT only: one 3-degree mascon is far larger than Banni, so this cannot show a Banni-specific signal. "
                "Gap between GRACE and GRACE-FO (mid-2017 to mid-2018); catalogue coverage Apr 2002 - Sep 2024. Anomaly relative to the 2004-2009 mean."),
    *[DatasetSpec(f"lc_{name}", f"Land cover share: {label} (MODIS MCD12Q1 IGBP)", "landcover", "MODIS/061/MCD12Q1", "NASA LP DAAC",
                  f"LC_Type1 class {'/'.join(str(c) for c in classes)}", "500 m", "yearly", "% of classified area", "1",
                  "None (classification product); water/unclassified pixels count in the denominator", "mean", 500,
                  "A global classifier, not validated for Banni; year-to-year class flips at 500 m are partly classification noise. "
                  "Cannot separate Prosopis from other shrubs.")
      for name, label, classes in [("grassland", "grassland (10)", (10,)), ("shrubland", "shrubland (6, 7)", (6, 7)),
                                   ("savanna", "savanna / woody savanna (8, 9)", (8, 9)), ("cropland", "cropland (12, 14)", (12, 14)),
                                   ("barren", "barren (16)", (16,)), ("water", "permanent wetland / water (11, 17)", (11, 17))]],
    DatasetSpec("groundwater","Groundwater level (user-supplied CGWB / India-WRIS)", "water", None,
                "CGWB / India-WRIS (manual upload)", "depth to water level", "point wells",
                "irregular (aggregated monthly)", "m below ground level", "1", "As supplied; no automatic QA",
                "mean", 0,
                "Point measurements; representativeness depends on the well network. No automated download is implemented."),
]}


def spec_dict(key: str) -> dict:
    return asdict(CATALOG[key])
