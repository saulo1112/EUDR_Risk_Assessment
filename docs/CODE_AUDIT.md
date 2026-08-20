# Code audit

Self-review of the pipeline, API and frontend, first run before Phase 7 (the
Docker stack) and updated after the follow-up hardening pass. Findings are
grouped by severity, with the resolved ones marked.

## Data contract: consistent end to end

No mismatches between what each phase writes and what the next one reads:

`farms.geojson` (`farm_id, area_ha, count, geom`) → `farms_risk_raw.csv`
(`farm_id, defo_m2, total_m2, defo_pct`) → PostGIS `farms` + `assessments` →
`farms_distance.csv` (`dist_to_defo_m`) + `farms_neighborhood_multi.csv`
(`nb_defo_pct_{200,500,1000}`) → `phase4_scoring_v3` joins on `farm_id` and
updates `assessments.risk_score` / `risk_class` → the API selects those columns →
the frontend reads them by name.

The invariants this relies on are now asserted, not assumed:
`tests/test_integration_db.py` checks the row counts, the class distribution,
that every parcel is scored, that scores are probabilities, that `risk_class`
agrees with `defo_pct`, and that geometries are valid EPSG:4326.

## Resolved

- ✅ **No tests at all, and `pytest` would have crashed.** `src/testing/` held
  four ad-hoc scripts, three named `test_*.py`; `test_ee.py` called
  `ee.Authenticate()` at import time, so a plain `pytest` run opened a browser.
  Moved to `scripts/` with non-colliding names, and replaced by a real suite:
  61 unit + API tests (`tests/`), plus opt-in integration tests behind the
  `integration` marker.
- ✅ **No pipeline script was importable.** None had an
  `if __name__ == "__main__"` guard, so importing any of them opened database
  connections and initialised Earth Engine, which is what made the logic
  untestable. Every script now does its work inside `main()`, and the pure model
  logic lives in [`src/pipeline/scoring.py`](../src/pipeline/scoring.py), which
  imports with no side effects.
- ✅ **Duplicated configuration.** The connection string was hardcoded in seven
  files and `ee.Initialize(project='eudr-forest-risk')` in six.
  [`src/config.py`](../src/config.py) is now the single source of truth, all
  environment-overridable; the EUDR reference layers are defined once in
  [`src/pipeline/earth_engine.py`](../src/pipeline/earth_engine.py).
- ✅ **Duplicated constants.** `NEIGHBORHOOD`/`SCALE`/`DIST_CAP_M` (defined in
  two scripts), `DEFO_MEDIAN_AFFECTED = 5.3755` (two scripts) and the `0.3`
  cocoa threshold (twice in phase 1) now come from `src/config.py`.
- ✅ **No CI, no linting.** `.github/workflows/ci.yml` runs ruff plus the test
  suite, with a second job that seeds PostGIS and runs the integration tests.
- ✅ **No LICENSE** despite the README calling the project open source. MIT
  added.
- ✅ **No `.dockerignore`.** Build contexts pulled in `.venv/`, `data/` (56 MB)
  and `.git/`. Added, and the SQL seed is now gzipped (24 MB → 2.9 MB).
- ✅ **Dead code**: the `main.py` `Hello from eudr-risk-assessment!` stub and a
  stale trailing comment in `.gitignore` are gone.
- ✅ **Flat `src/`** mixing pipeline scripts with the API and frontend →
  `src/pipeline/` (with `legacy/` for the superseded v2 model), `scripts/`,
  `tests/`.

## Found by the new tests

- **87% of parcel geometries fail `ST_IsValid`** (3,655 of 4,170), all with
  *Ring Self-intersection*. This surfaced the moment the integration tests
  asserted geometry validity, and is an artefact of vectorizing a 10 m raster:
  pixel-derived polygons touch at diagonal corners.

  Impact on this project is nil: `area_ha` comes from the pixel count rather
  than `ST_Area` (the two agree to within 1.78%), the model features are computed
  in Earth Engine, and `ST_AsGeoJSON` serializes the geometries correctly, so
  both the API and the dashboard are unaffected. It *would* matter for spatial
  overlays (`ST_Intersection`, `ST_Union`, spatial joins).

  Every affected geometry is repairable with `ST_MakeValid`, and
  `tests/test_integration_db.py::test_selfintersecting_rings_are_repairable`
  guards exactly that. Applying `ST_MakeValid` during the phase 3 load would be
  the fix; it was left out of this pass because it changes stored geometry and
  the current data is demonstrably fit for purpose.

## Open, nice to have

- **Frontend partial-failure states.** `loadFarms()` degrades gracefully when the
  API is unreachable, but `loadStats()` and `loadEarlyWarning()` only
  `console.error`, so their panels would sit on skeleton loaders indefinitely. A
  per-panel error state would be an improvement.
- **Frontend selection race.** `/stats` and `/early-warning` render before
  `/farms` finishes, so clicking an early-warning row during that window is a
  no-op (`layersById` is not yet populated). Harmless, but the rows could be
  disabled until the map layer is ready.
- **API does not distinguish a database outage.** Queries are not wrapped, so an
  outage surfaces as a generic 500. Production code would map it to 503 with a
  clear message.
- **No frontend tests.** The dashboard is plain JS with no build step; adding a
  test runner for it was judged out of proportion for this project's scope.

## Accepted for a demo, documented as such

- **CORS `allow_origins=["*"]`** in [`src/api/main.py`](../src/api/main.py):
  intentional so any local frontend origin can call the API. Must be tightened
  before a real deployment.
- **Default database password** (`eudr_dev_password`) in the compose file and as
  the fallback in `src/config.py`. Environment-overridable, but it ships with a
  known value, acceptable for a local demo, never for production.
- **`pyproject.toml` is one flat dependency list** mixing the heavy geospatial
  pipeline dependencies (earthengine, geemap, rasterio, geopandas) with the light
  API runtime. `src/api/Dockerfile` therefore installs only the API subset to
  keep the image small; splitting into optional extras would be the cleaner fix.
- **`data/farms.geojson` (32 MB) stays versioned** so the repo is reproducible
  without Earth Engine credentials. Git compresses it well, so a clone is only ~8 MB.
