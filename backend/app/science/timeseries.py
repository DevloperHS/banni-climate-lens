"""Monthly-series aggregation, anomalies and alignment. Pure functions over pandas Series
indexed by month-start Timestamps."""
from __future__ import annotations
import numpy as np
import pandas as pd

SEASONS: dict[str, tuple[int, ...]] = {
    "annual": tuple(range(1, 13)),
    "summer": (3, 4, 5),            # pre-monsoon hot dry season
    "monsoon": (6, 7, 8, 9),        # JJAS
    "peak": (9, 10),                # Sep-Oct: post-monsoon vegetation peak / Landsat composite window
    "postmonsoon": (10, 11),
    "winter": (12, 1, 2),
}
# Fraction of months in a season that must be valid for the season/year to be reported.
MIN_COVERAGE = 0.75


def to_series(dates: list[str], values: list) -> pd.Series:
    idx = pd.to_datetime([d + "-01" for d in dates])
    return pd.Series([np.nan if v is None else float(v) for v in values], index=idx, dtype=float).sort_index()


def from_series(s: pd.Series) -> tuple[list[str], list[float | None]]:
    return [d.strftime("%Y-%m") for d in s.index], [None if not np.isfinite(v) else float(v) for v in s.values]


def clip_years(s: pd.Series, start: int | None, end: int | None) -> pd.Series:
    if start is not None:
        s = s[s.index.year >= start]
    if end is not None:
        s = s[s.index.year <= end]
    return s


def seasonal_aggregate(s: pd.Series, season: str, reducer: str) -> pd.Series:
    """Per-year aggregate over `season` months. Index = year (int).

    Sums (precip, ET) need every month present: a partial-season sum is biased low.
    Means need >= MIN_COVERAGE of the months. "winter" is {Dec, Jan, Feb} within one calendar year.
    """
    months = SEASONS[season]
    sub = s[s.index.month.isin(months)]
    g = sub.groupby(sub.index.year)
    n_valid = g.count()
    n_expected = len(months)
    if reducer == "sum":
        agg = g.sum(min_count=1)
        ok = n_valid >= n_expected
    else:
        agg = g.mean()
        ok = n_valid >= int(np.ceil(MIN_COVERAGE * n_expected))
    agg = agg[ok]
    agg.index = agg.index.astype(int)
    agg.name = season
    return agg


def monthly_climatology(s: pd.Series, exclude_years: tuple[int, ...] = ()) -> pd.Series:
    sub = s[~s.index.year.isin(exclude_years)]
    return sub.groupby(sub.index.month).mean()


def monthly_anomaly(s: pd.Series, exclude_years: tuple[int, ...] = ()) -> pd.Series:
    clim = monthly_climatology(s, exclude_years)
    return s - s.index.month.map(clim).values


def standardised_monthly_anomaly(s: pd.Series) -> pd.Series:
    clim = s.groupby(s.index.month).mean()
    sd = s.groupby(s.index.month).std(ddof=1)
    return (s - s.index.month.map(clim).values) / s.index.month.map(sd).values


def annual_anomaly(a: pd.Series) -> pd.DataFrame:
    """a: year-indexed. Returns anomaly vs period mean and z-score; flags |z| > 2."""
    mu, sd = a.mean(), a.std(ddof=1)
    z = (a - mu) / sd if sd and np.isfinite(sd) and sd > 0 else a * np.nan
    return pd.DataFrame({"value": a, "anomaly": a - mu, "z": z, "flag": z.abs() > 2})


def align(a: pd.Series, b: pd.Series) -> pd.DataFrame:
    return pd.concat([a.rename("a"), b.rename("b")], axis=1).dropna()


def cumulative_lag(s: pd.Series, window: int) -> pd.Series:
    """Rolling sum over `window` months ending at each month (requires full window)."""
    return s.rolling(window, min_periods=window).sum()
