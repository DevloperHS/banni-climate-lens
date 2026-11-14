"""Raster quality control, alignment, masking, differencing, cross-resolution agreement and the exploratory
dry-season-persistence indicator. Pure NumPy/rasterio; no web or Earth Engine imports."""
from __future__ import annotations
import numpy as np
from scipy import stats as sps

TOL_DEG = 0.05


class RasterError(ValueError):
    pass


def validate_stack(info: dict, bbox: dict | None = None, require_years: bool = True) -> dict:
    """Check CRS, pixel geometry, extent and band labels. Returns a report; `ok` is False if any hard issue exists."""
    issues, warnings = [], []
    crs = info["crs"]
    if crs is None or crs.to_epsg() != 4326:
        issues.append(f"CRS is {crs} (expected EPSG:4326)")
    t = info["transform"]
    if abs(t.b) > 1e-12 or abs(t.d) > 1e-12:
        issues.append("raster is rotated/sheared")
    if t.e >= 0:
        issues.append("raster is not north-up")
    dx, dy = abs(t.a), abs(t.e)
    if dx <= 0 or dy <= 0:
        issues.append("zero pixel size")
    elif abs(dx - dy) / max(dx, dy) > 0.10:
        issues.append(f"pixels are not square in degrees (dx={dx:.5f}, dy={dy:.5f})")
    b = info["bounds"]
    if bbox:
        if (b.left > bbox["west"] + TOL_DEG or b.right < bbox["east"] - TOL_DEG or
                b.bottom > bbox["south"] + TOL_DEG or b.top < bbox["north"] - TOL_DEG):
            issues.append("raster does not cover the region bbox")
        if (b.left < bbox["west"] - 1 or b.right > bbox["east"] + 1 or b.bottom < bbox["south"] - 1 or b.top > bbox["north"] + 1):
            warnings.append("raster extends >1 degree beyond the region")
    data = info["data"]
    n = data.shape[0]
    if require_years:
        digits = [("".join(c for c in (d or "") if c.isdigit())) for d in info["descriptions"][:n]]
        if any(len(d) < 4 for d in digits):
            issues.append("band descriptions do not carry a year (expected y<YYYY>)")
        else:
            ys = [int(d[-4:]) for d in digits]
            if ys != sorted(ys) or len(set(ys)) != len(ys):
                issues.append("band years are not strictly increasing")
    finite = np.isfinite(data)
    if not finite.any():
        issues.append("no valid pixels")
    elif finite.mean() < 0.5:
        warnings.append(f"only {100 * finite.mean():.0f}% of pixel-values are valid")
    mid_lat = (b.top + b.bottom) / 2
    px_m = (dx * 111320 * np.cos(np.radians(mid_lat)), dy * 110574)
    return {"ok": not issues, "issues": issues, "warnings": warnings, "n_bands": int(n), "shape": [int(data.shape[1]), int(data.shape[2])],
            "pixel_size_deg": [float(dx), float(dy)], "pixel_size_m_approx": [round(float(px_m[0])), round(float(px_m[1]))],
            "valid_fraction": float(finite.mean()), "crs": str(crs), "bounds": [b.left, b.bottom, b.right, b.top]}


def grids_aligned(a: dict, b: dict, tol: float = 1e-6) -> bool:
    return (a["data"].shape[1:] == b["data"].shape[1:] and all(abs(x - y) <= tol for x, y in zip(tuple(a["transform"])[:6], tuple(b["transform"])[:6])))


def align_to(src: dict, dst: dict, resampling: str = "nearest") -> np.ndarray:
    """Resample every band of `src` onto the grid of `dst` (same CRS). Returns array (T,H,W) with NaN for no data."""
    from rasterio.warp import reproject, Resampling
    rs = getattr(Resampling, resampling)
    H, W = dst["data"].shape[1:]
    out = np.full((src["data"].shape[0], H, W), np.nan, dtype="float64")
    for i in range(src["data"].shape[0]):
        reproject(src["data"][i], out[i], src_transform=src["transform"], src_crs=src["crs"], dst_transform=dst["transform"], dst_crs=dst["crs"],
                  resampling=rs, src_nodata=np.nan, dst_nodata=np.nan)
    return out


def apply_water_mask(stack: np.ndarray, occurrence: np.ndarray, threshold: float = 10.0) -> tuple[np.ndarray, dict]:
    """Set pixels whose long-term surface-water occurrence (%) >= threshold to NaN in every band.
    `occurrence` must be on the same grid as `stack` (T,H,W). No-data occurrence is treated as 0 (never observed as water)."""
    if occurrence.shape != stack.shape[1:]:
        raise RasterError(f"mask grid {occurrence.shape} does not match stack grid {stack.shape[1:]}")
    occ = np.nan_to_num(occurrence, nan=0.0)
    masked = occ >= threshold
    out = np.where(masked[None, :, :], np.nan, stack)
    valid_before = np.isfinite(stack[0]).sum()
    return out, {"threshold_pct": threshold, "pixels_masked": int((masked & np.isfinite(stack[0])).sum()),
                 "fraction_of_valid_masked": float((masked & np.isfinite(stack[0])).sum() / max(valid_before, 1))}


def period_mean(stack: np.ndarray, years: np.ndarray, y0: int, y1: int) -> np.ndarray:
    sel = (years >= y0) & (years <= y1)
    if not sel.any():
        raise RasterError(f"no bands in {y0}-{y1}")
    with np.errstate(all="ignore"):
        return np.nanmean(stack[sel], axis=0)


def difference_summary(a: np.ndarray, b: np.ndarray) -> dict:
    d = b - a
    v = d[np.isfinite(d)]
    if v.size == 0:
        raise RasterError("no overlapping valid pixels")
    return {"n_pixels": int(v.size), "mean_change": float(v.mean()), "median_change": float(np.median(v)), "sd": float(v.std(ddof=1)) if v.size > 1 else 0.0,
            "pct_increase": float(100 * np.mean(v > 0)), "pct_decrease": float(100 * np.mean(v < 0)),
            "p05": float(np.percentile(v, 5)), "p95": float(np.percentile(v, 95))}


def trend_agreement(coarse: dict[str, np.ndarray], fine_on_coarse: dict[str, np.ndarray]) -> dict:
    """Compare two trend products on the SAME grid (fine product already averaged onto the coarse grid).
    Each dict needs `slope` and `cls` (+1/-1/0/NaN)."""
    s1, s2 = coarse["slope"], fine_on_coarse["slope"]
    ok = np.isfinite(s1) & np.isfinite(s2)
    if ok.sum() < 10:
        raise RasterError("fewer than 10 comparable pixels")
    rho, rp = sps.spearmanr(s1[ok], s2[ok])
    r, _ = sps.pearsonr(s1[ok], s2[ok])
    sign = np.sign(s1[ok]) == np.sign(s2[ok])
    c1, c2 = coarse["cls"], fine_on_coarse["cls"]
    both = np.isfinite(c1) & np.isfinite(c2) & (c1 != 0) & (c2 != 0)
    # fine class averaged onto coarse grid is fractional: treat |value| >= 0.5 as majority significant
    f_sig = np.where(np.isfinite(c2) & (np.abs(c2) >= 0.5), np.sign(c2), 0)
    both = np.isfinite(c1) & (c1 != 0) & (f_sig != 0)
    return {"n_pixels": int(ok.sum()), "spearman_rho": float(rho), "spearman_p": float(rp), "pearson_r": float(r),
            "sign_agreement_pct": float(100 * sign.mean()), "n_both_significant": int(both.sum()),
            "significant_sign_agreement_pct": float(100 * np.mean(np.sign(c1[both]) == f_sig[both])) if both.any() else None,
            "note": "Fine-resolution slopes are averaged onto the coarse grid. Agreement of trend signs supports, but does not prove, that coarse greening is real at fine scale."}


def evergreen_index(dry: np.ndarray, wet: np.ndarray, min_wet: float = 0.05, cap: float = 2.0) -> np.ndarray:
    """EXPLORATORY dry-season persistence indicator: dry-season NDVI / wet-season NDVI per pixel and year.
    Perennial, deep-rooted evergreen woody cover (e.g. invasive Prosopis) tends to keep a higher ratio than seasonal
    grassland, but so does irrigated land, saline-tolerant shrubs and groundwater-fed vegetation. It is a
    hypothesis-generating index, NOT a classifier."""
    with np.errstate(all="ignore"):
        r = np.where(wet >= min_wet, dry / wet, np.nan)
    return np.clip(r, 0, cap)


def block_mean(arr: np.ndarray, f: int) -> np.ndarray:
    H, W = arr.shape[-2:]
    h, w = H // f * f, W // f * f
    a = arr[..., :h, :w].reshape(*arr.shape[:-2], h // f, f, w // f, f)
    with np.errstate(all="ignore"):
        return np.nanmean(a, axis=(-3, -1))
