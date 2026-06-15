"""Phase 4 feature: distance from each parcel centroid to the nearest
post-2020 deforestation pixel.

This is a non-leaky spatial-context feature: it never reads the parcel's own
deforestation status directly, only how far the parcel sits from the nearest
recent forest loss. Parcels embedded in actively cleared areas should score a
small distance; isolated parcels score a large one.

Deforestation reference (same EUDR definition used elsewhere in the pipeline):
    defo_post2020 = Hansen lossyear >= 21  AND  JRC GFC2020 forest == 1

Output: data/farms_distance.csv  (farm_id, dist_to_defo_m)
"""

import math

import ee
import geemap
import geopandas as gpd
import pandas as pd

ee.Initialize(project='eudr-forest-risk')

gdf = gpd.read_file('data/farms.geojson')

# --- Deforestation mask (post-2020 loss on land that was forest in 2020) ---
forest2020 = ee.Image('JRC/GFC2020/V3').select('Map')
hansen = ee.Image('UMD/hansen/global_forest_change_2025_v1_13')
lossyear = hansen.select('lossyear')
defo_post2020 = lossyear.gte(21).And(forest2020.eq(1)).rename('defo')

# fastDistanceTransform returns the SQUARED distance to the nearest non-zero
# pixel, in pixel units, capped at the neighborhood size. With a 10 m scale:
#     dist_m = sqrt(value_in_pixels^2) * 10
# NEIGHBORHOOD px sets the search radius / saturation cap. 256 px = 2.56 km;
# any parcel farther than that from deforestation is clamped to the cap and is
# treated simply as "far" (the exact value past a few km is not informative).
NEIGHBORHOOD = 256          # pixels
SCALE = 10                  # metres / pixel
DIST_CAP_M = NEIGHBORHOOD * SCALE

# Squared distance (pixels^2) -> distance in metres.
dist_px2 = defo_post2020.fastDistanceTransform(
    neighborhood=NEIGHBORHOOD, units='pixels').sqrt().rename('dist_px')

BATCH_SIZE = 200
results = []

for start in range(0, len(gdf), BATCH_SIZE):
    chunk = gdf.iloc[start:start + BATCH_SIZE]
    farms_chunk = geemap.geopandas_to_ee(chunk)

    # Sample the distance image at each parcel centroid.
    centroids = farms_chunk.map(
        lambda f: f.setGeometry(f.geometry().centroid(maxError=1)))

    stats = dist_px2.reduceRegions(
        collection=centroids, reducer=ee.Reducer.first(),
        scale=SCALE, tileScale=4)
    stats_no_geom = stats.map(lambda f: ee.Feature(None, f.toDictionary()))

    results.append(geemap.ee_to_df(stats_no_geom))
    print(f'Distance sampled: {min(start + BATCH_SIZE, len(gdf))}/{len(gdf)}')

dist = pd.concat(results, ignore_index=True)

# 'first' holds the sampled distance in pixels; convert to metres and cap.
dist['dist_to_defo_m'] = (dist['first'] * SCALE).clip(upper=DIST_CAP_M).round(1)
dist = dist[['farm_id', 'dist_to_defo_m']]
dist['farm_id'] = dist['farm_id'].astype(int)
dist = dist.sort_values('farm_id').reset_index(drop=True)
dist.to_csv('data/farms_distance.csv', index=False)

print(f'\nParcels processed: {len(dist)}  (cap = {DIST_CAP_M} m)')
print(dist['dist_to_defo_m'].describe())
print(f'Parcels at 0 m (on a defo pixel): {(dist["dist_to_defo_m"] == 0).sum()}')
