# Contributing

## Ground rules (scientific)
1. **Never fabricate** observations, statistics or findings, and never present sample/simulated data as real. Anything synthetic must carry `kind="synthetic"` and live under `data/sample/`.
2. A failed or unavailable data source must produce an explicit error or empty state - no silent fallback.
3. Every new dataset needs a `DatasetSpec` in `core/catalog.py` (id, provider, unit, scale factor, QA, limitations) and an entry in `docs/DATASETS.md`.
4. Scale factors, unit conversions and aggregation go in `science/processing.py` with a unit test on a **small known dataset** that does not need Earth Engine.
5. New statistics go in `science/stats.py`, with a validation test against an independent reference (SciPy, statsmodels, pymannkendall or a hand calculation) and a note in `docs/METHODOLOGY.md`.
6. Interpretation text must distinguish association from causation and must not name causes/species the data cannot identify.
7. Never commit secrets, `.env`, key files or `data/` contents.

## Workflow
```powershell
cd backend;  ..\.venv\Scripts\python -m pytest -q
cd frontend; npx tsc --noEmit; npm test; npm run e2e
```
Keep all suites green. Do not describe tests as passing unless you ran them.

## Adding things
- **Region**: add to `backend/app/config/regions.json`.
- **Variable**: catalog spec → extractor in `gee/extract.py` (`EXTRACTORS`) → it is automatically served by the matching group router.
- **Page**: add under `frontend/src/pages`, route in `App.tsx`, nav entry in `components/Layout.tsx`; use `<Q>` / `<RequireData>` for loading, error and empty states; show provenance via `meta`.

## Style
Python: typed, small pure functions, no web imports in `science/`. TypeScript: strict mode; shared panels over copy-paste. Charts must forward `width`/`height` props from `ResponsiveContainer` (see `charts.tsx`).

## Releases
No pushes to GitHub or releases without explicit maintainer approval.
