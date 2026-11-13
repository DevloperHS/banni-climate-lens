"""Step 7: one location-holdout run in full detail (the stricter check behind the ~76 % figure).

Same split as 06_point_holdout_accuracy.py (70/30 by training LOCATION, randomColumn on the location collection), but every
location carries an id (Zenodo site name or hand-picked point id), so the held-out locations can be listed. Accuracy, kappa
and the confusion matrix all come from the same single getInfo() call, i.e. the same run.

Run from the repository root:  .venv\\Scripts\\python research\\prosopis_rf\\scripts\\07_point_holdout_detail.py [seed]
Default seed 2 (OA closest to the 5-seed mean in 06). Writes to research/prosopis_rf/results/:
  point_holdout_seed<seed>.json             accuracy, kappa, confusion matrix, per-class accuracies, counts
  point_holdout_seed<seed>_locations.csv    every location with its split (train/test) and its test-pixel results
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
p = ROOT / "research" / "prosopis_rf" / "scripts" / "04_run_rf_python.py"
g = {"__file__": str(p)}
exec(p.read_text().split("# ---- STEP C")[0], g)          # ee init, ROI, sites, comp(), bands, training points
ee, sites, pts, comp, bands = g["ee"], g["sites"], g["pts"], g["comp"], g["bands"]
RES = ROOT / "research" / "prosopis_rf" / "results"
SEED = int(sys.argv[1]) if len(sys.argv) > 1 else 2
NAMES = {1: "Prosopis woodland", 2: "Mixed", 3: "Wetland/water", 4: "Saline brushland"}

# Same collections and order as step 4 (so system:index, and therefore randomColumn, match step 6), plus a loc_id.
siteFC = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([s[1], s[2]], "EPSG:32642").buffer(60),
                                          {"class": s[3], "loc_id": s[0], "source": "Zenodo field site"}) for s in sites])
manual = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([float(r["lon"]), float(r["lat"])]).buffer(20),
                                          {"class": int(r["class_code"]), "loc_id": r["point_id"], "source": "hand-picked"}) for r in pts])
loc = siteFC.merge(manual).randomColumn("loc_r", SEED)
tr_loc, te_loc = loc.filter(ee.Filter.lt("loc_r", 0.7)), loc.filter(ee.Filter.gte("loc_r", 0.7))

img23 = comp(2023).select(bands)
tr = img23.sampleRegions(collection=tr_loc, properties=["class"], scale=10, tileScale=4)
te = img23.sampleRegions(collection=te_loc, properties=["class", "loc_id"], scale=10, tileScale=4)
rf = ee.Classifier.smileRandomForest(300).train(tr, "class", bands)
te_c = te.classify(rf)
cm = te_c.errorMatrix("class", "classification")

# per held-out location: test pixels and how many were classified correctly
per_loc = te_c.map(lambda f: f.set("ok", ee.Number(f.get("class")).eq(f.get("classification"))))
r = ee.Dictionary({
    "train_locations": tr_loc.size(), "test_locations": te_loc.size(), "train_pixels": tr.size(), "test_pixels": te.size(),
    "confusion_matrix": cm.array(), "overall_accuracy": cm.accuracy(), "kappa": cm.kappa(),
    "producers_accuracy": cm.producersAccuracy(), "consumers_accuracy": cm.consumersAccuracy(),
    "locations": loc.select(["loc_id", "class", "source", "loc_r"], None, False).toList(500),
    "pix_n": per_loc.aggregate_histogram("loc_id"),
    "pix_ok": per_loc.filter(ee.Filter.eq("ok", 1)).aggregate_histogram("loc_id"),
}).getInfo()

locs = [f["properties"] for f in r.pop("locations")]
pix_n, pix_ok = r.pop("pix_n"), r.pop("pix_ok")
coords = {s[0]: f"UTM42N {s[1]:.0f} E, {s[2]:.0f} N" for s in sites}
coords.update({x["point_id"]: f"{float(x['lon']):.5f} E, {float(x['lat']):.5f} N" for x in pts})
rows = []
for l in sorted(locs, key=lambda x: (x["loc_r"] < 0.7, x["class"], x["loc_id"])):
    split = "train" if l["loc_r"] < 0.7 else "test"
    n, ok = int(pix_n.get(l["loc_id"], 0)), int(pix_ok.get(l["loc_id"], 0))
    rows.append({"loc_id": l["loc_id"], "split": split, "class_code": l["class"], "class_name": NAMES[l["class"]], "source": l["source"],
                 "location": coords.get(l["loc_id"], ""), "test_pixels": n if split == "test" else "",
                 "test_pixels_correct": ok if split == "test" else "",
                 "test_pixel_accuracy": round(ok / n, 3) if split == "test" and n else ""})

RES.mkdir(parents=True, exist_ok=True)
r.update(seed=SEED, method="70/30 split of training LOCATIONS (randomColumn on locations), RF 300 trees, Sentinel-2 Nov 2022-Mar 2023",
         note="Confusion matrix rows = true class, columns = predicted class, index = class code (row/column 0 unused).")
(RES / f"point_holdout_seed{SEED}.json").write_text(json.dumps(r, indent=2))
with (RES / f"point_holdout_seed{SEED}_locations.csv").open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader(); w.writerows(rows)

# ---- console output (all from the single run above)
print(f"Seed {SEED}: train locations {r['train_locations']}, test locations {r['test_locations']}")
print(f"Training pixels {r['train_pixels']}  Test pixels {r['test_pixels']}")
print("Confusion matrix (test)  rows = true, columns = predicted")
print("               " + "".join(f"{NAMES[c][:10]:>12}" for c in (1, 2, 3, 4)))
for c in (1, 2, 3, 4):
    print(f"{NAMES[c][:14]:<15}" + "".join(f"{v:>12}" for v in r["confusion_matrix"][c][1:]))
print(f"Overall accuracy {r['overall_accuracy']:.4f}   Kappa {r['kappa']:.4f}")
print("Producer's accuracy (recall):", {NAMES[c]: round(r["producers_accuracy"][c][0], 3) for c in (1, 2, 3, 4)})
print("User's accuracy (precision):", {NAMES[c]: round(r["consumers_accuracy"][0][c], 3) for c in (1, 2, 3, 4)})
print("\nTest locations:")
for x in rows:
    if x["split"] == "test":
        print(f"  {x['loc_id']:<11} {x['class_name']:<18} {x['source']:<17} {x['location']:<28} "
              f"{x['test_pixels_correct']}/{x['test_pixels']} pixels correct")
