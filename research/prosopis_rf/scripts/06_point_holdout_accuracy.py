"""Step 6: a stricter accuracy check than banni_rf.js reports.

banni_rf.js splits train/test by PIXEL (randomColumn after sampleRegions). Pixels from the same 20 m or 60 m buffer land on
both sides of the split, so the held-out score mostly measures how alike neighbouring pixels are. Here whole training
locations (polygons) are held out: 30 % of locations per class never contribute a pixel to training. Repeated for 5 seeds.
Everything else (composite, bands, 300-tree random forest) is as in banni_rf.js.

Run from the repository root:  .venv\\Scripts\\python research\\prosopis_rf\\scripts\\06_point_holdout_accuracy.py
Writes research/prosopis_rf/results/rf_accuracy_point_holdout.json
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
p = ROOT / "research" / "prosopis_rf" / "scripts" / "04_run_rf_python.py"
src = p.read_text()
g = {"__file__": str(p)}
exec(src.split("# ---- STEP C")[0], g)            # ROI, sites, hand-picked points, comp() and band list from step 4
ee, training, comp, bands = g["ee"], g["training"], g["comp"], g["bands"]

img23 = comp(2023).select(bands)
runs = []
for seed in (1, 2, 3, 4, 5):
    loc = training.randomColumn("loc_r", seed)
    tr_loc, te_loc = loc.filter(ee.Filter.lt("loc_r", 0.7)), loc.filter(ee.Filter.gte("loc_r", 0.7))
    tr = img23.sampleRegions(collection=tr_loc, properties=["class"], scale=10, tileScale=4)
    te = img23.sampleRegions(collection=te_loc, properties=["class"], scale=10, tileScale=4)
    rf = ee.Classifier.smileRandomForest(300).train(tr, "class", bands)
    cm = te.classify(rf).errorMatrix("class", "classification")
    r = ee.Dictionary({"seed": seed, "train_locations": tr_loc.size(), "test_locations": te_loc.size(), "test_pixels": te.size(),
                       "overall_accuracy": cm.accuracy(), "kappa": cm.kappa(), "producers_accuracy": cm.producersAccuracy(),
                       "consumers_accuracy": cm.consumersAccuracy(), "confusion_matrix": cm.array()}).getInfo()
    runs.append(r)
    print(f"seed {seed}: test locations {r['test_locations']}, OA {r['overall_accuracy']:.3f}, kappa {r['kappa']:.3f}", flush=True)

oa = [r["overall_accuracy"] for r in runs]
ka = [r["kappa"] for r in runs]
summary = {"overall_accuracy_mean": sum(oa) / len(oa), "overall_accuracy_min": min(oa), "overall_accuracy_max": max(oa),
           "kappa_mean": sum(ka) / len(ka), "runs": runs,
           "method": "70/30 split of training LOCATIONS (not pixels), 5 random seeds; Sentinel-2 Nov 2022-Mar 2023 composite; RF 300 trees"}
out = ROOT / "research" / "prosopis_rf" / "results" / "rf_accuracy_point_holdout.json"
out.write_text(json.dumps(summary, indent=2))
print(f"mean OA {summary['overall_accuracy_mean']:.3f} (range {min(oa):.3f}-{max(oa):.3f}), mean kappa {summary['kappa_mean']:.3f}")
