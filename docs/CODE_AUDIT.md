# Code audit

Read-only review of the pipeline (`phase1` → `phase4_scoring_v3`), the API
(`src/api`), and the frontend (`src/frontend`), ahead of Phase 7. Grouped by
severity. Trivial items marked ✅ were fixed directly; everything else is
documented here only (no broad refactor).

## Consistency — filenames & columns across phases

The data contract is **consistent end-to-end**; no mismatches found:

`farms.geojson` (`farm_id, area_ha, count, geom`) → `farms_risk_raw.csv`
(`farm_id, defo_m2, total_m2, defo_pct`) → PostGIS `farms` + `assessments` →
`farms_distance.csv` (`dist_to_defo_m`) + `farms_neighborhood_multi.csv`
(`nb_defo_pct_{200,500,1000}`) → `phase4_scoring_v3.py` joins on `farm_id` and
updates `assessments.risk_score` / `risk_class` → API selects those columns →
frontend reads them by name. Verified the API/SQL column names
(`farm_id, area_ha, defo_pct, risk_score, risk_class`) match the frontend
property accesses.

One nuance worth stating explicitly (now in `docs/PIPELINE.md`): the canonical
v3 model consumes the **unmasked** `farms_distance.csv`. The masked variant is
a diagnostic only.

## Should fix before Phase 7

- **None blocking.** The pipeline, API, and frontend are internally consistent
  and the API was verified against the live DB. The only Phase-7 prerequisites
  are packaging concerns (Dockerfiles, seed dump, service wiring), handled in
  Phase 7 itself — not code defects.

## Nice to have (documented, not changed)

- **Duplicated DB credentials.** The literal
  `postgresql://eudr:eudr_dev_password@localhost:5432/eudr_risk` is hardcoded in
  every offline script: `phase3_postgis.py`, `phase4_scoring.py`,
  `phase4_scoring_v3.py`, `phase4_scoring_v3_sensitivity.py`,
  `testing/{test_db,check_defo_distribution,verify_phase4}.py`. Only the API
  (`src/api/database.py`) reads it from `DATABASE_URL` with that value as a
  default. A shared `src/config.py` (or having the scripts also read
  `DATABASE_URL`) would remove the duplication. Left as-is to avoid touching
  every batch script; these run offline by a developer who controls the env.
- **Duplicated EE project id.** `ee.Initialize(project='eudr-forest-risk')`
  appears in all six EE scripts (`phase1`, `phase2`, `phase4_scoring`,
  `phase4_distance`, `phase4_distance_masked`, `phase4_neighborhood_multi`).
  Same recommendation (env var / shared config).
- **Duplicated model/feature constants.**
  - `NEIGHBORHOOD = 256` / `SCALE = 10` / `DIST_CAP_M = 2560` are defined in
    both `phase4_distance.py` and `phase4_distance_masked.py`.
  - `DEFO_MEDIAN_AFFECTED = 5.3755` is defined in both `phase4_scoring.py` and
    `phase4_scoring_v3.py`.
  - The cocoa-probability threshold `> 0.3` is written twice within
    `phase1_aoi_parcels.py` (AOI clustering + parcel vectorization).
  These are stable, well-commented magic numbers; centralizing them is low
  value for a batch pipeline. Documented here instead.
- **Frontend partial-failure states.** `loadFarms()` shows a graceful error
  message if the API is unreachable, but `loadStats()` and `loadEarlyWarning()`
  only `console.error` on failure — their panels would keep showing skeleton
  loaders indefinitely. A small per-panel error state would be an improvement.
- **Frontend selection race.** `/stats` and `/early-warning` render before
  `/farms` finishes; clicking an early-warning row before parcels finish loading
  is a no-op (no `flyTo`/detail) because `layersById` is not yet populated.
  Harmless, but could be guarded by disabling rows until the map layer is ready.
- **API has no explicit DB-down handling.** DB calls are not wrapped in
  try/except, so a DB outage surfaces as a generic 500 (FastAPI default). Fine
  for a demo; a production API would map this to 503 with a clear message.

## Acceptable for a demo (documented as such)

- **CORS `allow_origins=["*"]`** in `src/api/main.py` — hardcoded, intentional
  for the demo so any frontend origin can call the API. Tighten before real
  deployment.
- **Default DB password** (`eudr_dev_password`) in `docker/docker-compose.yml`
  and as the default in `database.py`. It is env-overridable
  (`POSTGRES_PASSWORD` / `DATABASE_URL`) but ships with a known value. Fine for
  a local/portfolio demo; must be set via secrets in any real deployment.
- **`pyproject.toml` is a single flat dependency list** mixing heavy geospatial
  pipeline deps (earthengine, geemap, rasterio, geopandas) with the lightweight
  API runtime deps. The API Dockerfile (Phase 7) therefore installs only the
  API subset rather than the full list, to keep the image lean — noted in that
  Dockerfile.

## Fixes applied directly ✅

- ✅ Added a clear **"SUPERSEDED — documentation only"** header to
  `src/phase4_scoring.py` (the v2 model).
- ✅ Added **`docs/PIPELINE.md`** documenting the canonical run order and
  flagging the diagnostic/superseded scripts.
- ✅ Extended **`.gitignore`** with OS/editor cruft (`.DS_Store`, `Thumbs.db`,
  `*.log`).
- ✅ `.env` / `.env.example` reviewed — `DATABASE_URL` is covered. (The EE
  project id is not env-driven today; noted under "nice to have".)
