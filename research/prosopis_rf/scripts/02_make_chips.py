"""Step 2: build high-resolution image chips for visual labelling.

For every candidate in labelling/candidates.csv this cuts a ~330 m square chip centred on the point from Esri World
Imagery (zoom 17, about 1.1 m/pixel at Banni's latitude) and draws a yellow circle of 20 m radius, the buffer that
banni_rf.js puts around each hand-picked point. Chips are tiled 4 x 4 into contact sheets that are inspected by eye;
the decisions are written to labelling/visual_labels.csv.

Imagery: Esri World Imagery (Maxar / Earthstar Geographics). Attribution: "Imagery (c) Esri, Maxar, Earthstar Geographics".
Run from the repository root:  .venv\\Scripts\\python research\\prosopis_rf\\scripts\\02_make_chips.py
"""
import csv
import io
import math
import time
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[3]
LAB = ROOT / "research" / "prosopis_rf" / "labelling"
CACHE = ROOT / "data" / "cache" / "esri_tiles"          # git-ignored
SHEETS = LAB / "sheets"
Z, TILE, CHIP, COLS = 17, 256, 300, 4
URL = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"


def global_px(lon, lat, z=Z):
    n = TILE * 2 ** z
    x = (lon + 180) / 360 * n
    y = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n
    return x, y


def tile(z, x, y):
    p = CACHE / f"{z}_{x}_{y}.jpg"
    if not p.exists():
        req = urllib.request.Request(URL.format(z=z, x=x, y=y), headers={"User-Agent": "banni-research-labelling"})
        with urllib.request.urlopen(req, timeout=60) as r:
            p.write_bytes(r.read())
        time.sleep(0.05)
    return Image.open(p).convert("RGB")


def chip(lon, lat):
    gx, gy = global_px(lon, lat)
    x0, y0 = int(gx - CHIP / 2), int(gy - CHIP / 2)
    canvas = Image.new("RGB", (CHIP, CHIP))
    for tx in range(x0 // TILE, (x0 + CHIP) // TILE + 1):
        for ty in range(y0 // TILE, (y0 + CHIP) // TILE + 1):
            canvas.paste(tile(Z, tx, ty), (tx * TILE - x0, ty * TILE - y0))
    m_per_px = 156543.03392 * math.cos(math.radians(lat)) / 2 ** Z
    r = 20 / m_per_px
    d = ImageDraw.Draw(canvas)
    c = CHIP / 2
    d.ellipse([c - r, c - r, c + r, c + r], outline=(255, 230, 0), width=2)
    d.line([c - 4, c, c + 4, c], fill=(255, 230, 0)); d.line([c, c - 4, c, c + 4], fill=(255, 230, 0))
    bar = 100 / m_per_px                                   # 100 m scale bar
    d.rectangle([8, CHIP - 14, 8 + bar, CHIP - 10], fill=(255, 255, 255))
    return canvas


def main(candidates="candidates.csv", prefix=""):
    """candidates: CSV in labelling/ (candidates.csv or candidates_round2.csv); prefix: added to sheet names (e.g. 'r2_')."""
    CACHE.mkdir(parents=True, exist_ok=True)
    SHEETS.mkdir(parents=True, exist_ok=True)
    rows = list(csv.DictReader((LAB / candidates).open()))
    by = {}
    for r in rows:
        by.setdefault(prefix + r["stratum"], []).append(r)
    for stratum, items in by.items():
        for s in range(0, len(items), COLS * COLS):
            group = items[s:s + COLS * COLS]
            sheet = Image.new("RGB", (COLS * (CHIP + 6), ((len(group) + COLS - 1) // COLS) * (CHIP + 24)), (20, 20, 20))
            d = ImageDraw.Draw(sheet)
            for i, r in enumerate(group):
                x, y = (i % COLS) * (CHIP + 6), (i // COLS) * (CHIP + 24)
                sheet.paste(chip(float(r["lon"]), float(r["lat"])), (x, y + 20))
                d.text((x + 4, y + 4), r["cand_id"], fill=(255, 255, 255))
            out = SHEETS / f"{stratum}_{s // (COLS * COLS) + 1:02d}.jpg"
            sheet.save(out, quality=88)
            print("wrote", out.name, len(group))


if __name__ == "__main__":
    import sys
    # round 1: no arguments;  round 2: candidates_round2.csv r2_
    main(*sys.argv[1:3])
