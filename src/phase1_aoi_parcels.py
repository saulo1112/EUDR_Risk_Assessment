import ee, geemap, geopandas as gpd

ee.Initialize(project='eudr-forest-risk')

# 1. Real boundary of Colombia (not a bounding box)
colombia = (ee.FeatureCollection('USDOS/LSIB_SIMPLE/2017')
    .filter(ee.Filter.eq('country_na', 'Colombia')).geometry())

# 2. Cocoa probability (Forest Data Partnership), year 2023
cocoa_prob = (ee.ImageCollection(
    'projects/forestdatapartnership/assets/cocoa/model_2025a')
    .filterDate('2023-01-01', '2023-12-31')
    .mosaic().clip(colombia))

# 3. Threshold + clustering (connected components) at 1km resolution
mask = cocoa_prob.gt(0.3).selfMask()
vectors = mask.reduceToVectors(
    geometry=colombia, scale=1000, geometryType='polygon',
    eightConnected=True, maxPixels=1e9, tileScale=4)
vectors = vectors.map(lambda f: f.set(
    'area_km2', f.geometry().area(1).divide(1e6)))

# 4. Largest cluster -> centroid -> final AOI (20km buffer)
largest = vectors.sort('area_km2', False).first()
centroid = largest.geometry().centroid(1).coordinates().getInfo()
print('AOI centroid (Alto Sinu):', centroid)
aoi = ee.Geometry.Point(centroid).buffer(20000).bounds(1)

# 5. Vectorize 'parcels' at 10m resolution within the final AOI
cocoa_aoi = cocoa_prob.clip(aoi)
parcels_mask = cocoa_aoi.gt(0.3).selfMask()
parcels_raw = parcels_mask.reduceToVectors(
    geometry=aoi, scale=10, geometryType='polygon',
    eightConnected=True, maxPixels=1e9, tileScale=4)

# Filter to a realistic parcel-size range:
# - Lower bound: 0.5 ha (50 pixels at 10m) -> excludes pixel-level noise
# - Upper bound: 85 ha (8,500 pixels) -> ~99th percentile of observed
#   size distribution (p99 = 83.1 ha); excludes aggregated mega-clusters
#   (>600 ha) that don't represent individual plots
MIN_PIXELS = 50
MAX_PIXELS = 8500
parcels = parcels_raw.filter(
    ee.Filter.And(
        ee.Filter.gte('count', MIN_PIXELS),
        ee.Filter.lte('count', MAX_PIXELS)
    )
)

gdf = geemap.ee_to_gdf(parcels)
gdf['farm_id'] = range(len(gdf))
gdf['area_ha'] = gdf['count'] * 0.01  # 1 pixel (10m) = 100 m2 = 0.01 ha
gdf.to_file('data/farms.geojson', driver='GeoJSON')

print(f'Parcels generated (0.5-85 ha): {len(gdf)}')
print(gdf[['farm_id', 'count', 'area_ha']].describe())
print(gdf.head())