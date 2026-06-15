# Pipeline — canonical run order

The offline pipeline regenerates all data from Earth Engine and repopulates
PostGIS. It is **only** needed to rebuild the dataset from scratch; for a
running demo, use the pre-loaded Docker stack (see the README "Quick start").

## Canonical order (fresh rebuild)

| Step | Script | Reads | Writes |
|------|--------|-------|--------|
| 1 | `src/phase1_aoi_parcels.py` | Earth Engine | `data/farms.geojson` (`farm_id, area_ha, count, geometry`) |
| 2 | `src/phase2_deforestation.py` | `data/farms.geojson` + EE | `data/farms_risk_raw.csv` (`farm_id, defo_m2, total_m2, defo_pct`) |
| 3 | `src/phase3_postgis.py` | `farms.geojson`, `farms_risk_raw.csv` | PostGIS `farms` + `assessments` |
| 4 | `src/phase4_distance.py` | `farms.geojson` + EE | `data/farms_distance.csv` (`farm_id, dist_to_defo_m`) |
| 5 | `src/phase4_neighborhood_multi.py` | `farms.geojson` + EE | `data/farms_neighborhood_multi.csv` (`farm_id, nb_defo_pct_{200,500,1000}`) |
| 6 | `src/phase4_scoring_v3.py` | PostGIS + the two CSVs above | updates `assessments.risk_score`, `assessments.risk_class` |

After step 6 the `assessments` table is fully scored and the API
(`src/api`) + frontend (`src/frontend`) can serve it.

## Diagnostic / superseded scripts (NOT in the run order)

| Script | Status | Notes |
|--------|--------|-------|
| `src/phase4_scoring.py` | **Superseded (v2)** | RF on `[area_ha, nb_defo_pct_200]`, single split, macro-F1 0.43. Kept for documentation. Also writes the now-unused `data/farms_neighborhood.csv`. |
| `src/phase4_distance_masked.py` | **Diagnostic** | Leakage sensitivity check: recomputes distance with each parcel's own pixels masked out. Produces `data/farms_distance_masked.csv`. |
| `src/phase4_scoring_v3_sensitivity.py` | **Diagnostic** | Compares original vs masked distance (variants C & F). Does **not** write to the DB. |
| `src/testing/*` | **Ad-hoc checks** | `test_db.py`, `test_ee.py`, `check_defo_distribution.py`, `verify_phase4.py`. |

> **Note on the distance feature.** The canonical model
> (`phase4_scoring_v3.py`) uses the **unmasked** `data/farms_distance.csv`.
> The masked variant (`phase4_distance_masked.py`) is a diagnostic that
> quantifies a small label-leakage effect (PR-AUC 0.846 → 0.812, within CV
> noise for N=70). See `docs/phase4_model_comparison.md`. If this pipeline is
> productionised, swap step 4 for the masked script and re-run step 6.
