import ee, geemap, geopandas as gpd
import pandas as pd

ee.Initialize(project='eudr-forest-risk')

gdf = gpd.read_file('data/farms.geojson')

# EUDR reference layers
forest2020 = ee.Image('JRC/GFC2020/V3').select('Map')
hansen = ee.Image('UMD/hansen/global_forest_change_2025_v1_13')
lossyear = hansen.select('lossyear')
defo_post2020 = lossyear.gte(21).And(forest2020.eq(1)).rename('defo')

pixel_area = ee.Image.pixelArea()
defo_area_img = defo_post2020.multiply(pixel_area).rename('defo_m2')
area_img = ee.Image.pixelArea().rename('total_m2')
combined = defo_area_img.addBands(area_img)

BATCH_SIZE = 200
results = []

for start in range(0, len(gdf), BATCH_SIZE):
    chunk = gdf.iloc[start:start + BATCH_SIZE]
    farms_chunk = geemap.geopandas_to_ee(chunk)

    stats = combined.reduceRegions(
        collection=farms_chunk, reducer=ee.Reducer.sum(), scale=10, tileScale=4)
    stats_no_geom = stats.map(lambda f: ee.Feature(None, f.toDictionary()))

    df_chunk = geemap.ee_to_df(stats_no_geom)
    results.append(df_chunk)
    print(f'Processed {min(start + BATCH_SIZE, len(gdf))}/{len(gdf)}')

df = pd.concat(results, ignore_index=True)
df['defo_pct'] = (df['defo_m2'] / df['total_m2'] * 100).round(3)
df.to_csv('data/farms_risk_raw.csv', index=False)

print(f'Parcels processed: {len(df)}')
print(f'Parcels with ANY post-2020 deforestation: {(df["defo_pct"] > 0).sum()}')
print(df[['farm_id', 'area_ha', 'defo_m2', 'defo_pct']]
      .sort_values('defo_pct', ascending=False).head(10))