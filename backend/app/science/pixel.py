"""Vectorised pixel-wise Mann-Kendall / Sen analysis with Benjamini-Hochberg FDR control,
plus raster IO (GeoTIFF) and colourised PNG rendering."""
from __future__ import annotations
import io
from pathlib import Path
import numpy as np
from scipy import stats as sps
from .stats import benjamini_hochberg

MIN_VALID = 10  # minimum valid years per pixel


def pixel_trends(stack: np.ndarray, times: np.ndarray, q: float = 0.05, min_valid: int = MIN_VALID,
                 row_chunk: int = 32) -> dict[str, np.ndarray]:
    """stack: (T, H, W) float with NaN for missing; times: (T,) e.g. years.

    Per pixel: tie-corrected Mann-Kendall (S, Z, two-sided p) and Sen slope (median of pairwise
    slopes using real time gaps). Then BH-FDR at level q over all pixels with enough data.
    Returns arrays (H, W): slope, z, p, q_value, n_valid, cls where cls is
      +1 significant increase (FDR), -1 significant decrease (FDR), 0 not significant,
      NaN insufficient data. `cls_uncorrected` uses raw p<0.05 for comparison only.
    """
    T, H, W = stack.shape
    times = np.asarray(times, float)
    iu, ju = np.triu_indices(T, 1)
    slope = np.full((H, W), np.nan); z = np.full((H, W), np.nan); p = np.full((H, W), np.nan)
    nvalid = np.isfinite(stack).sum(axis=0).astype(np.int16)
    dt = (times[ju] - times[iu])[:, None, None]

    for r0 in range(0, H, row_chunk):
        sl = stack[:, r0:r0 + row_chunk, :]
        h = sl.shape[1]
        a, b = sl[iu], sl[ju]                         # (P, h, W)
        d = b - a
        valid_pair = np.isfinite(d)
        S = np.where(valid_pair, np.sign(d), 0).sum(axis=0)
        sl_ps = d / dt
        with np.errstate(all="ignore"):
            slope[r0:r0 + h] = np.nanmedian(np.where(valid_pair, sl_ps, np.nan), axis=0)
        n = nvalid[r0:r0 + h].astype(float)
        # tie correction: sort along time (NaN last) and measure run lengths
        srt = np.sort(sl, axis=0)
        tie = np.zeros((h, W))
        run = np.ones((h, W))
        for k in range(1, T):
            same = (srt[k] == srt[k - 1]) & np.isfinite(srt[k])
            ended = ~same & (run > 1)
            tie += np.where(ended, run * (run - 1) * (2 * run + 5), 0)
            run = np.where(same, run + 1, 1)
        tie += np.where(run > 1, run * (run - 1) * (2 * run + 5), 0)
        var = (n * (n - 1) * (2 * n + 5) - tie) / 18.0
        with np.errstate(all="ignore"):
            zz = np.where(S == 0, 0.0, (S - np.sign(S)) / np.sqrt(var))
        zz = np.where((n >= min_valid) & (var > 0), zz, np.nan)
        z[r0:r0 + h] = zz
        p[r0:r0 + h] = 2 * (1 - sps.norm.cdf(np.abs(zz)))
    slope = np.where(nvalid >= min_valid, slope, np.nan)

    rej, qv = benjamini_hochberg(p.ravel(), q)
    rej, qv = rej.reshape(p.shape), qv.reshape(p.shape)
    cls = np.where(np.isfinite(p), 0.0, np.nan)
    cls = np.where(rej & (slope > 0), 1.0, np.where(rej & (slope < 0), -1.0, cls))
    cls_unc = np.where(np.isfinite(p), 0.0, np.nan)
    cls_unc = np.where((p < 0.05) & (slope > 0), 1.0, np.where((p < 0.05) & (slope < 0), -1.0, cls_unc))
    return {"slope": slope, "z": z, "p": p, "q_value": qv, "n_valid": nvalid, "cls": cls, "cls_uncorrected": cls_unc}


def summarise(res: dict[str, np.ndarray], q: float = 0.05) -> dict:
    valid = np.isfinite(res["p"])
    nv = int(valid.sum())
    cnt = lambda arr, v: int(np.sum(arr == v))
    return {
        "pixels_tested": nv, "fdr_q": q,
        "significant_increase_fdr": cnt(res["cls"], 1), "significant_decrease_fdr": cnt(res["cls"], -1),
        "not_significant": cnt(res["cls"], 0),
        "significant_increase_uncorrected": cnt(res["cls_uncorrected"], 1),
        "significant_decrease_uncorrected": cnt(res["cls_uncorrected"], -1),
        "pct_increase_fdr": float(100 * cnt(res["cls"], 1) / nv) if nv else None,
        "pct_decrease_fdr": float(100 * cnt(res["cls"], -1) / nv) if nv else None,
        "median_slope": float(np.nanmedian(res["slope"])) if nv else None,
        "note": ("Spatially autocorrelated pixels violate BH's independence/positive-dependence assumptions "
                 "somewhat; FDR control is approximate. Uncorrected counts are shown only to illustrate the "
                 "multiple-testing inflation and must not be read as discoveries."),
    }


# ----------------------------------------------------------------------- raster IO
def read_stack(path: Path) -> dict:
    import rasterio
    with rasterio.open(path) as ds:
        arr = ds.read().astype("float64")
        nod = ds.nodata
        if nod is not None:
            arr[arr == nod] = np.nan
        arr[~np.isfinite(arr)] = np.nan
        return {"data": arr, "transform": ds.transform, "crs": ds.crs, "bounds": ds.bounds,
                "descriptions": list(ds.descriptions), "tags": ds.tags(), "height": ds.height, "width": ds.width}


def band_years(descriptions: list[str | None], count: int) -> np.ndarray:
    ys = []
    for i in range(count):
        d = descriptions[i] if i < len(descriptions) else None
        digits = "".join(c for c in (d or "") if c.isdigit())
        ys.append(float(digits[-4:]) if len(digits) >= 4 else np.nan)
    return np.array(ys)


def write_geotiff(path: Path, arrays: dict[str, np.ndarray], transform, crs, tags: dict | None = None) -> Path:
    import rasterio
    path.parent.mkdir(parents=True, exist_ok=True)
    names = list(arrays)
    H, W = next(iter(arrays.values())).shape
    with rasterio.open(path, "w", driver="GTiff", height=H, width=W, count=len(names), dtype="float32",
                       crs=crs, transform=transform, nodata=np.nan, compress="deflate") as dst:
        for i, nme in enumerate(names, 1):
            dst.write(arrays[nme].astype("float32"), i)
            dst.set_band_description(i, nme)
        if tags:
            dst.update_tags(**{k: str(v) for k, v in tags.items()})
    return path


# ----------------------------------------------------------------------- rendering
CLASS_COLOURS = {1: (27, 158, 119, 220), -1: (217, 95, 2, 220), 0: (150, 150, 150, 90)}


def render_class_png(cls: np.ndarray, show_nonsig: bool = True) -> bytes:
    """show_nonsig=False leaves non-significant pixels transparent, so only significant pixels are coloured."""
    from PIL import Image
    rgba = np.zeros(cls.shape + (4,), np.uint8)
    for v, c in CLASS_COLOURS.items():
        if v == 0 and not show_nonsig:
            continue
        rgba[cls == v] = c
    return _png(rgba)


def render_scalar_png(arr: np.ndarray, vmin: float, vmax: float, cmap: str = "viridis") -> bytes:
    import matplotlib
    cm = matplotlib.colormaps[cmap]
    norm = np.clip((arr - vmin) / (vmax - vmin if vmax > vmin else 1), 0, 1)
    rgba = (cm(norm) * 255).astype(np.uint8)
    rgba[..., 3] = np.where(np.isfinite(arr), 215, 0)
    return _png(rgba)


def _png(rgba: np.ndarray) -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.fromarray(rgba, "RGBA").save(buf, format="PNG")
    return buf.getvalue()


def sample_value(stack_info: dict, band: int, lon: float, lat: float):
    import rasterio.transform as rt
    r, c = rt.rowcol(stack_info["transform"], lon, lat)
    if 0 <= r < stack_info["height"] and 0 <= c < stack_info["width"]:
        v = stack_info["data"][band, r, c]
        return None if not np.isfinite(v) else float(v)
    return None
