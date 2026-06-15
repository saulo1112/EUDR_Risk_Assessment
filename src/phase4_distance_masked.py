"""Phase 4 sensitivity check: distance to deforestation with parcel self-masking.

The original phase4_distance.py computes a global fastDistanceTransform over the
entire defo_post2020 image and samples each parcel's centroid. For AFFECTED
parcels (defo_pct > 0), the "nearest defo pixel" may be within the parcel's own
boundary — i.e., the parcel's own deforestation inadvertently pulls the feature
toward 0, encoding the label indirectly.

This script produces a corrected version:
  - CLEAN parcels (defo_pct == 0): no own deforestation to mask out, so their
    distance is identical to the original — values are copied directly.
  - AFFECTED parcels (~70): each is processed individually. The parcel's own
    geometry is painted to 0 in defo_post2020 before computing the distance
    transform, so only deforestation *outside* the parcel boundary counts.

Output: data/farms_distance_masked.csv  (farm_id, dist_to_defo_m_masked)
"""

import ee
import geemap
import geopandas as gpd
import pandas as pd

ee.Initialize(project='eudr-forest-risk')

NEIGHBORHOOD = 256   # pixels; same cap as phase4_distance.py
SCALE = 10           # metres / pixel
DIST_CAP_M = NEIGHBORHOOD * SCALE  # 2560 m

# --- EUDR deforestation reference (identical to rest of pipeline) ---
forest2020 = ee.Image('JRC/GFC2020/V3').select('Map')
hansen = ee.Image('UMD/hansen/global_forest_change_2025_v1_13')
lossyear = hansen.select('lossyear')
defo_post2020 = lossyear.gte(21).And(forest2020.eq(1)).rename('defo')

gdf = gpd.read_file('data/farms.geojson')
risk = pd.read_csv('data/farms_risk_raw.csv')[['farm_id', 'defo_pct']]
dist_orig = pd.read_csv('data/farms_distance.csv')  # farm_id, dist_to_defo_m

affected_ids = set(risk.loc[risk['defo_pct'] > 0, 'farm_id'].astype(int))
clean_ids = set(risk.loc[risk['defo_pct'] == 0, 'farm_id'].astype(int))

print(f"AFFECTED parcels to recompute: {len(affected_ids)}")
print(f"CLEAN parcels to copy unchanged: {len(clean_ids)}")

# ------------------------------------------------------------------ #
# CLEAN parcels: copy from original CSV unchanged
# ------------------------------------------------------------------ #
clean_rows = (dist_orig[dist_orig['farm_id'].isin(clean_ids)]
              .rename(columns={'dist_to_defo_m': 'dist_to_defo_m_masked'})
              [['farm_id', 'dist_to_defo_m_masked']])

# ------------------------------------------------------------------ #
# AFFECTED parcels: per-parcel masked distance (one EE call each)
# ------------------------------------------------------------------ #
def sample_masked_distance(fid: int) -> float:
    """Return dist_to_defo_m_masked (metres) for one AFFECTED parcel."""
    farm_gdf = gdf[gdf['farm_id'] == fid]
    farm_ee = geemap.geopandas_to_ee(farm_gdf)

    # Erase this parcel's own pixels from the defo image.
    # paint(fc, value) writes `value` into the image inside the features.
    defo_masked = defo_post2020.paint(farm_ee, 0)

    dist_img = (defo_masked
                .fastDistanceTransform(neighborhood=NEIGHBORHOOD, units='pixels')
                .sqrt()
                .rename('dist_px'))

    centroid_fc = farm_ee.map(
        lambda f: f.setGeometry(f.geometry().centroid(maxError=1)))

    stats = dist_img.reduceRegions(
        collection=centroid_fc,
        reducer=ee.Reducer.first(),
        scale=SCALE,
        tileScale=4)
    stats_no_geom = stats.map(lambda f: ee.Feature(None, f.toDictionary()))
    df_result = geemap.ee_to_df(stats_no_geom)

    if df_result.empty or 'first' not in df_result.columns:
        return DIST_CAP_M  # fallback: treat as "far"
    raw_px = float(df_result['first'].iloc[0])
    return min(round(raw_px * SCALE, 1), DIST_CAP_M)


affected_results = []
affected_list = sorted(affected_ids)

for i, fid in enumerate(affected_list):
    dist_m = sample_masked_distance(fid)
    affected_results.append({'farm_id': fid, 'dist_to_defo_m_masked': dist_m})
    if (i + 1) % 10 == 0 or (i + 1) == len(affected_list):
        print(f'AFFECTED processed: {i + 1}/{len(affected_list)}  '
              f'(last farm_id={fid}, dist={dist_m} m)')

affected_rows = pd.DataFrame(affected_results)

# ------------------------------------------------------------------ #
# Merge, sort, save
# ------------------------------------------------------------------ #
result = pd.concat([clean_rows, affected_rows], ignore_index=True)
result['farm_id'] = result['farm_id'].astype(int)
result = result.sort_values('farm_id').reset_index(drop=True)
result.to_csv('data/farms_distance_masked.csv', index=False)

# ------------------------------------------------------------------ #
# Diagnostics
# ------------------------------------------------------------------ #
affected_orig = dist_orig[dist_orig['farm_id'].isin(affected_ids)].copy()
affected_orig = affected_orig.merge(affected_rows, on='farm_id')
affected_orig['delta'] = (affected_orig['dist_to_defo_m_masked']
                          - affected_orig['dist_to_defo_m'])

n_was_zero = (affected_orig['dist_to_defo_m'] == 0).sum()
n_now_positive = ((affected_orig['dist_to_defo_m'] == 0)
                  & (affected_orig['dist_to_defo_m_masked'] > 0)).sum()

print(f'\n--- Summary for AFFECTED parcels (n={len(affected_orig)}) ---')
print(affected_orig[['dist_to_defo_m', 'dist_to_defo_m_masked']].describe())
print(f'\nHad dist=0 before masking: {n_was_zero}')
print(f'Now dist>0 after masking:  {n_now_positive}')
print(f'Median delta (masked - original): {affected_orig["delta"].median():.1f} m')
print(f'\nTotal rows written: {len(result)}')
