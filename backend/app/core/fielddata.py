"""Storage for user-supplied FIELD data (ground-truth class labels, measured EC). Atomic JSON writes; validated on upload."""
from __future__ import annotations
import json
from datetime import date
from .config import get_settings
from .security import safe_name


def _path(source: str, region: str, name: str):
    return get_settings().data_dir / ("sample" if source == "sample" else "processed") / "fielddata" / safe_name(region, "region") / f"{safe_name(name, 'name')}.json"


def save(source: str, region: str, name: str, payload: dict) -> None:
    p = _path(source, region, name)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({**payload, "uploaded": date.today().isoformat()}), encoding="utf-8")
    tmp.replace(p)


def load(source: str, region: str, name: str) -> dict | None:
    p = _path(source, region, name)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
