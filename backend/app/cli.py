"""Sequential live-data workflow. Each stage stops the run on failure; nothing is written after a failed stage.

    python -m app.cli live-check     # Task 4: credentials, connection, dataset/band verification
    python -m app.cli extract        # Task 5: MODIS NDVI + IMERG rainfall, 2001-2024 (raw + processed)
    python -m app.cli reproduce      # Task 6: handover protocol vs reported values
    python -m app.cli water          # Task 7: ET + GLDAS (run only after reproduce looks sane)
    python -m app.cli quality        # data-quality / missing-observation summaries
    python -m app.cli checks         # Aqua NDVI + EVI: extract, then repeat the trend / rain-removed tests vs Terra NDVI
Options: --region banni --start 2001 --end 2024
"""
from __future__ import annotations
import argparse
import json
import sys

from .gee import client


def _p(o):
    print(json.dumps(o, indent=2, default=str))


def live_check(a) -> int:
    st = client.status(probe=True)
    _p(st)
    if not st["verified"]:
        print("\nSTOP: Earth Engine is not verified. No data was requested and nothing was written.", file=sys.stderr)
        return 2
    from .gee.extract import verify_dataset_bands
    rep = verify_dataset_bands()
    _p(rep)
    if not all(v.get("ok") for v in rep.values()):
        print("\nSTOP: dataset/band verification failed (see above).", file=sys.stderr)
        return 3
    print("\nOK: authenticated; all collections and bands present.")
    return 0


def _run(a, keys, raw_checks=()) -> int:
    from .gee import extract
    if live_check(a) != 0:
        return 2
    for k in raw_checks:
        try:
            _p(extract.run_raw_artifact(k, a.region, a.start, a.end))
        except Exception as e:
            print(f"STOP: {k} failed: {type(e).__name__}: {e}", file=sys.stderr)
            return 4
    for k in keys:
        try:
            _p(extract.run_series_job(k, a.region, a.start, a.end))
        except Exception as e:
            print(f"STOP: {k} failed: {type(e).__name__}: {e}", file=sys.stderr)
            return 4
    return 0


EXTENDED_SERIES = ["ndvi_qa", "ndvi_aqua", "evi","lst_day", "lst_night", "sm_surface", "water_extent", "ndvi_nowater", "salinity_index", "ndvi_landsat", "water_extent_mndwi",
                   "grace_tws", "lc_grassland", "lc_shrubland", "lc_savanna", "lc_cropland", "lc_barren", "lc_water"]
EXTENDED_STACKS = [("water_occurrence", "static"), ("ndvi", "annual"), ("ndvi", "monsoon"), ("ndvi", "summer"), ("ndvi", "peak"), ("precip", "monsoon"),
                   ("lst_day", "summer"), ("et", "annual"), ("sm_root", "annual"), ("ndvi_landsat", "peak"), ("salinity_index", "summer"),
                   ("lst_night", "summer")]


def extended(a) -> int:
    """Remaining series and all raster stacks. Unlike `extract`, a failing task does NOT stop the run: every outcome is recorded
    (the extractors themselves never store partial data, and the completeness gate still applies)."""
    from .gee import extract
    import time
    if live_check(a) != 0:
        return 2
    results = []
    tasks = [("series", k, None) for k in EXTENDED_SERIES] + [("stack", k, s) for k, s in EXTENDED_STACKS]
    for typ, key, season in tasks:
        t0 = time.time()
        label = f"{typ}:{key}" + (f":{season}" if season else "")
        try:
            res = extract.run_series_job(key, a.region, a.start, a.end) if typ == "series" else extract.run_stack_job(key, a.region, a.start, a.end, season)
            results.append((label, "done", res)); print(f"DONE   {label} ({time.time() - t0:.0f}s) {res}", flush=True)
        except Exception as e:
            results.append((label, "failed", f"{type(e).__name__}: {e}")); print(f"FAILED {label} ({time.time() - t0:.0f}s) {type(e).__name__}: {str(e)[:300]}", flush=True)
    print("\nSUMMARY:", sum(1 for r in results if r[1] == "done"), "done,", sum(1 for r in results if r[1] == "failed"), "failed", flush=True)
    return 0 if all(r[1] == "done" for r in results) else 7


def checks(a) -> int:
    """Research brief s.7: extract Aqua NDVI (MYD13Q1) and Terra EVI (MOD13Q1) with the handover protocol, then repeat the
    trend and rain-removed tests and report whether each agrees with Terra NDVI. Stops on the first failure."""
    rc = _run(a, ["ndvi_aqua", "evi"])
    if rc != 0:
        return rc
    from . import services as svc
    try:
        r = svc.sensor_index_checks_payload(a.region, "processed", a.start, a.end)["result"]
    except svc.AppError as e:
        print(f"STOP: {e.message}", file=sys.stderr)
        return 5
    print(f"\nCommon period {r['period']}  ({r['note']})")
    for s in r["seasons"]:
        print(f"\n{s['label']}  (rain removed using the {s['rain_control']})")
        print(f"  {'series':24s} {'raw trend':34s} {'rain removed':34s} R2 rain")
        for row in s["rows"]:
            if not row["available"]:
                print(f"  {row['label']:24s} unavailable: {row['reason']}"); continue
            f = lambda t: f"{t['direction'][:22]:22s} p={t['p']:.4f}"
            print(f"  {row['label']:24s} {f(row['raw_trend']):34s} {f(row['residual_trend']):34s} {row['r2_rain']:.2f}")
        print(f"  -> {s['agreement']['status'].upper()}: {s['agreement']['text']}")
    if r["terra_aqua_monsoon"]:
        c = r["terra_aqua_monsoon"]
        print(f"\nTerra vs Aqua monsoon NDVI: r = {c['pearson_r']:.3f} over {c['n']} years; mean Aqua - Terra = {c['mean_difference_aqua_minus_terra']:+.4f}")
    return 0


def validate_csv(a) -> int:
    """Validate a field-data CSV offline (no upload, no Earth Engine): python -m app.cli validate-csv <kind> <file>
    kind = ground-truth | field-ec | groundwater"""
    from pathlib import Path
    from .science import validation as VA
    from .core import groundwater as GW
    raw = Path(a.file).read_bytes()
    try:
        if a.kind == "ground-truth":
            _, rep = VA.parse_labels_csv(raw)
            ok = all(n >= VA.MIN_PER_CLASS for n in rep["class_counts"].values())
            rep["sufficient_for_validation"] = ok
        elif a.kind == "groundwater":
            _, rep = GW.parse(raw)
            ok = True
        else:
            import io, pandas as pd
            df = pd.read_csv(io.BytesIO(raw)); df.columns = [c.strip().lower() for c in df.columns]
            good = df[df["ec"].between(0, 500) & df["lat"].between(-90, 90) & df["lon"].between(-180, 180)].drop_duplicates(["lat", "lon"])
            rep = {"rows_in": int(len(df)), "rows_valid": int(len(good)), "needed": VA.MIN_PER_CLASS}
            ok = len(good) >= VA.MIN_PER_CLASS
            rep["sufficient_for_validation"] = ok
    except Exception as e:
        print(f"INVALID: {type(e).__name__}: {e}", file=sys.stderr)
        return 8
    _p(rep)
    print("\nSUFFICIENT for independent validation." if ok else f"\nINSUFFICIENT: independent validation needs at least {VA.MIN_PER_CLASS} valid points (per class for labels). Results would not be reported.")
    return 0 if ok else 9


def reproduce(a) -> int:
    from . import services as svc
    try:
        r = svc.handover_payload(a.region, "processed", a.start, a.end)["result"]
    except svc.AppError as e:
        print(f"STOP: {e.message}", file=sys.stderr)
        return 5
    print(f"{'comparison':58s} {'status':15s} reported -> computed")
    for row in r["rows"]:
        rp, c = row["reported"], row["computed"]
        rs = ", ".join(f"{k}={v}" for k, v in rp.items())
        cs = "n/a" if c is None else (f"{c:.5f}" if isinstance(c, float) else f"{c['direction']}, p={c['p']:.4f}, slope={c['slope']:.5g}, z={c['z']:.3f}")
        print(f"{row['label'][:58]:58s} {row['status']:15s} {rs}  ->  {cs}")
    print("\ncounts:", r["counts"], "| engine cross-check agrees:", r["engine_cross_check"]["agree"])
    return 0


def quality(a) -> int:
    from . import services as svc
    for k in ("ndvi", "ndvi_qa", "precip", "et", "sm_root", "sm_surface"):
        try:
            q = svc.quality_report(a.region, k, "processed")["result"]
            print(f"{k:10s} valid {q['valid_months']}/{q['expected_months']} ({q['completeness_pct']}%) missing {q['missing_months']} flags {q['flags']}")
        except svc.AppError as e:
            print(f"{k:10s} {e.code}: not processed")
    return 0


def verify_metadata(a) -> int:
    from .verify_metadata import verify_all
    r = verify_all()
    for x in r["results"]:
        print(f"{'OK ' if x['ok'] else 'FAIL'} {x['collection']:38s} {'; '.join(x['notes'])}")
        for i in x["issues"]:
            print("      -", i)
    print("\nall ok:", r["all_ok"], "| retrieved", r["retrieved"])
    return 0 if r["all_ok"] else 6


def main() -> int:
    ap = argparse.ArgumentParser(prog="python -m app.cli", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["live-check", "extract", "reproduce", "water", "quality", "verify-metadata", "extended", "checks", "validate-csv"])
    ap.add_argument("kind", nargs="?", help="validate-csv: ground-truth | field-ec | groundwater")
    ap.add_argument("file", nargs="?", help="validate-csv: path to the CSV")
    ap.add_argument("--region", default="banni")
    ap.add_argument("--start", type=int, default=2001)
    ap.add_argument("--end", type=int, default=2024)
    a = ap.parse_args()
    return {"live-check": live_check, "extract": lambda x: _run(x, ["ndvi", "precip"], ["ndvi_annual_image_mean"]), "reproduce": reproduce,
            "water": lambda x: _run(x, ["et", "sm_root", "sm_surface"], ["handover_water_table"]), "quality": quality, "verify-metadata": verify_metadata, "extended": extended, "checks": checks, "validate-csv": validate_csv}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
