"""Pure-Python/NumPy product processing: scale factors, QA decoding, unit conversion and
temporal aggregation. No Earth Engine dependency -> fully unit-testable."""
from __future__ import annotations
import calendar
from collections import defaultdict
from datetime import date, datetime, timezone
import numpy as np

MODIS_NDVI_SCALE = 0.0001
MODIS_NDVI_FILL = -3000
LST_SCALE = 0.02            # Kelvin
ET_SCALE = 0.1              # kg/m2 per composite
ET_FILL_MIN = 32700         # DN > 32700 are fill / non-vegetated codes
LANDSAT_SR_SCALE, LANDSAT_SR_OFFSET = 0.0000275, -0.2


def ndvi_from_dn(dn):
    dn = np.asarray(dn, float)
    return np.where(dn == MODIS_NDVI_FILL, np.nan, dn * MODIS_NDVI_SCALE)


def lst_dn_to_celsius(dn):
    dn = np.asarray(dn, float)
    return np.where(dn <= 0, np.nan, dn * LST_SCALE - 273.15)


def et_dn_to_mm_composite(dn):
    dn = np.asarray(dn, float)
    return np.where(dn > ET_FILL_MIN, np.nan, dn * ET_SCALE)


def landsat_sr_to_reflectance(dn):
    return np.asarray(dn, float) * LANDSAT_SR_SCALE + LANDSAT_SR_OFFSET


def ndvi_from_reflectance(nir, red):
    nir, red = np.asarray(nir, float), np.asarray(red, float)
    den = nir + red
    return np.where(den == 0, np.nan, (nir - red) / np.where(den == 0, 1, den))


def days_in_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def imerg_rate_to_month_mm(rate_mm_per_hr, year: int, month: int):
    """IMERG monthly stores a mean rate in mm/hr; monthly total = rate * 24 * days."""
    if rate_mm_per_hr is None or not np.isfinite(rate_mm_per_hr):
        return None
    return float(rate_mm_per_hr) * 24.0 * days_in_month(year, month)


def lst_qc_ok(qc: int, max_error_class: int = 1) -> bool:
    """MOD11A2 QC: bits 0-1 mandatory QA (0 good, 1 other quality; 2,3 not produced);
    bits 6-7 LST error class (0: <=1K, 1: <=2K, 2: <=3K, 3: >3K)."""
    return (qc & 0b11) in (0, 1) and ((qc >> 6) & 0b11) <= max_error_class


def landsat_qa_clear(qa_pixel: int) -> bool:
    """Landsat C2 QA_PIXEL: bit1 dilated cloud, bit3 cloud, bit4 shadow, bit5 snow must be 0."""
    return all(((qa_pixel >> b) & 1) == 0 for b in (1, 3, 4, 5))


def ms_to_date(ms: float) -> date:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date()


def composite_span_days(d: date, nominal: int = 8) -> int:
    """MODIS 8-day composites restart on 1 Jan, so the last composite of a year is shorter."""
    return min(nominal, (date(d.year + 1, 1, 1) - d).days)


def composites_to_monthly(dates: list[date], values: list, reducer: str = "mean",
                          span_days: list[int] | None = None, min_obs: int = 1) -> dict[str, float]:
    """Aggregate composites to calendar months keyed 'YYYY-MM'.

    Each composite is assigned to the month containing its midpoint.
    reducer='mean': average of valid composites (NDVI, LST).
    reducer='sum' : values are TOTALS over each composite (e.g. ET mm per 8 days). Daily rate =
                    value / span_days; month total = mean daily rate * days_in_month. This handles
                    composites straddling month ends and the short final composite of each year.
    """
    buckets: dict[tuple[int, int], list[float]] = defaultdict(list)
    for i, (d, v) in enumerate(zip(dates, values)):
        if v is None or not np.isfinite(v):
            continue
        span = span_days[i] if span_days else 1
        mid = date.fromordinal(d.toordinal() + max(span - 1, 0) // 2)
        buckets[(mid.year, mid.month)].append(v / span if reducer == "sum" else v)
    out: dict[str, float] = {}
    for (y, m), vals in sorted(buckets.items()):
        if len(vals) < min_obs:
            continue
        mean = float(np.mean(vals))
        out[f"{y:04d}-{m:02d}"] = mean * days_in_month(y, m) if reducer == "sum" else mean
    return out
