# Pipeline — canonical run order

The offline pipeline regenerates all data from Earth Engine and repopulates
PostGIS. It is **only** needed to rebuild the dataset from scratch; for a
running demo use the pre-seeded Docker stack (see the README "Quick start").

Scripts are run as **modules** (`python -m src.pipeline.…`) so their absolute
imports resolve from the repo root.

## Canonical order (fresh rebuild)

| Step | Module | Reads | Writes |
|------|--------|-------|--------|
| 1 | `src.pipeline.phase1_aoi_parcels` | Earth Engine | `data/farms.geojson` (`farm_id, area_ha, count, geometry`) |
| 2 | `src.pipeline.phase2_deforestation` | `farms.geojson` + EE | `data/farms_risk_raw.csv` (`farm_id, defo_m2, total_m2, defo_pct`) |
| 3 | `src.pipeline.phase3_postgis` | `farms.geojson`, `farms_risk_raw.csv` | PostGIS `farms` + `assessments` |
| 4 | `src.pipeline.phase4_distance` | `farms.geojson` + EE | `data/farms_distance.csv` (`farm_id, dist_to_defo_m`) |
| 5 | `src.pipeline.phase4_neighborhood_multi` | `farms.geojson` + EE | `data/farms_neighborhood_multi.csv` (`farm_id, nb_defo_pct_{200,500,1000}`) |
| 6 | `src.pipeline.phase4_scoring_v3` | PostGIS + the two CSVs above | updates `assessments.risk_score`, `assessments.risk_class` |

```bash
uv run python -m src.pipeline.phase1_aoi_parcels
uv run python -m src.pipeline.phase2_deforestation
uv run python -m src.pipeline.phase3_postgis
uv run python -m src.pipeline.phase4_distance
uv run python -m src.pipeline.phase4_neighborhood_multi
uv run python -m src.pipeline.phase4_scoring_v3
```

After step 6 the `assessments` table is fully scored and the API (`src/api`) and
dashboard (`src/frontend`) can serve it. Verify with
`uv run pytest -m integration`.

## Shared modules

| Module | Purpose |
|--------|---------|
| [`src/config.py`](../src/config.py) | Single source of truth: `DATABASE_URL`, `EE_PROJECT`, reference-layer ids, thresholds (`DEFO_MEDIAN_AFFECTED`, `DIST_CAP_M`, `COCOA_PROB_THRESHOLD`, …). |
| [`src/pipeline/earth_engine.py`](../src/pipeline/earth_engine.py) | `init()`, the EUDR `deforestation_mask()` defined once, and `iter_batches()` for the 10 MB payload limit. |
| [`src/pipeline/scoring.py`](../src/pipeline/scoring.py) | Pure, side-effect-free model logic: `classify()`, `build_labels()`, `FEATURE_SETS`, `make_model()`, `evaluate_binary()`. Unit-tested in `tests/test_scoring.py`. |

## Diagnostic / superseded scripts (NOT in the run order)

| Module | Status | Notes |
|--------|--------|-------|
| `src.pipeline.legacy.phase4_scoring` | **Superseded (v2)** | RF on `[area_ha, nb_defo_pct_200]`, single split, macro-F1 0.43. Kept as a record of the iteration. Also writes the now-unused `data/farms_neighborhood.csv`. |
| `src.pipeline.phase4_distance_masked` | **Diagnostic** | Leakage sensitivity check: recomputes distance with each parcel's own pixels masked out → `data/farms_distance_masked.csv`. |
| `src.pipeline.phase4_scoring_v3_sensitivity` | **Diagnostic** | Compares original vs masked distance (variants C & F). Never writes to the database. |
| `scripts/` | **Ad-hoc checks** | `check_db.py`, `check_ee_auth.py`, `check_defo_distribution.py`, `verify_phase4.py`. |

> **Note on the distance feature.** The canonical model
> (`phase4_scoring_v3`) uses the **unmasked** `data/farms_distance.csv`. The
> masked variant quantifies a small label-leakage effect (PR-AUC 0.846 → 0.812,
> within CV noise for N=70) — see
> [`phase4_model_comparison.md`](phase4_model_comparison.md). If this pipeline is
> productionised, swap step 4 for the masked script and re-run step 6.
