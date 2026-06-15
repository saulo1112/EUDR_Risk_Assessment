"""Phase 4 feature: deforestation share in concentric rings around each parcel.

Extends the original 200 m neighbourhood (src/phase4_scoring.py) to a set of
buffer radii. Each ring excludes the parcel itself, so the feature never encodes
the parcel's own deforestation -- only the pressure in its surroundings.

For each radius R the ring is  buffer(R) \\ parcel  and the feature is
    nb_defo_pct_R = 100 * defo_m2(ring) / total_m2(ring)

Output: data/farms_neighborhood_multi.csv
    (farm_id, nb_defo_pct_200, nb_defo_pct_500, nb_defo_pct_1000)
"""

import ee
import geemap
import geopandas as gpd
import pandas as pd

ee.Initialize(project='eudr-forest-risk')

gdf = gpd.read_file('data/farms.geojson')

# --- Deforestation reference (same EUDR definition as the rest of pipeline) ---
forest2020 = ee.Image('JRC/GFC2020/V3').select('Map')
hansen = ee.Image('UMD/hansen/global_forest_change_2025_v1_13')
lossyear = hansen.select('lossyear')
defo_post2020 = lossyear.gte(21).And(forest2020.eq(1)).rename('defo')

pixel_area = ee.Image.pixelArea()
combined = (defo_post2020.multiply(pixel_area).rename('defo_m2')
            .addBands(pixel_area.rename('total_m2')))

BUFFERS_M = [200, 500, 1000]
BATCH_SIZE = 200

merged = gdf[['farm_id']].copy()
merged['farm_id'] = merged['farm_id'].astype(int)

for buffer_m in BUFFERS_M:
    col = f'nb_defo_pct_{buffer_m}'
    results = []

    for start in range(0, len(gdf), BATCH_SIZE):
        chunk = gdf.iloc[start:start + BATCH_SIZE]
        farms_chunk = geemap.geopandas_to_ee(chunk)

        # Ring = buffer(R) minus the parcel itself.
        rings = farms_chunk.map(lambda f: f.setGeometry(
            f.geometry().buffer(buffer_m).difference(f.geometry())))

        stats = combined.reduceRegions(
            collection=rings, reducer=ee.Reducer.sum(), scale=10, tileScale=4)
        stats_no_geom = stats.map(lambda f: ee.Feature(None, f.toDictionary()))
        results.append(geemap.ee_to_df(stats_no_geom))
        print(f'[{buffer_m}m] {min(start + BATCH_SIZE, len(gdf))}/{len(gdf)}')

    ring = pd.concat(results, ignore_index=True)
    ring[col] = (ring['defo_m2'] / ring['total_m2'] * 100).round(3)
    ring['farm_id'] = ring['farm_id'].astype(int)
    merged = merged.merge(ring[['farm_id', col]], on='farm_id')

merged = merged.sort_values('farm_id').reset_index(drop=True)
merged.to_csv('data/farms_neighborhood_multi.csv', index=False)

print(f'\nParcels processed: {len(merged)}')
print(merged[[f'nb_defo_pct_{b}' for b in BUFFERS_M]].describe())
