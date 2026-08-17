"""Phase 1 — select the study area and derive parcel polygons.

The AOI is chosen programmatically rather than by hand: threshold the Forest
Data Partnership cocoa-probability raster over Colombia, cluster connected
components, take the largest cluster's centroid and buffer it by 20 km. Parcels
are then vectorized at 10 m within that AOI.

Output: ``data/farms.geojson`` (farm_id, area_ha, count, geometry)
"""

import ee
import geemap

from src.config import COCOA_PROB_THRESHOLD, MAX_PARCEL_PIXELS, MIN_PARCEL_PIXELS, SCALE
from src.pipeline.earth_engine import init

#: Forest Data Partnership cocoa probability model (2023 mosaic).
COCOA_MODEL = "projects/forestdatapartnership/assets/cocoa/model_2025a"

#: Radius around the largest cluster's centroid that defines the AOI.
AOI_BUFFER_M = 20_000


def main() -> None:
    init()

    # 1. Colombia's real administrative boundary (not a bounding box).
    colombia = (ee.FeatureCollection("USDOS/LSIB_SIMPLE/2017")
                .filter(ee.Filter.eq("country_na", "Colombia")).geometry())

    # 2. Cocoa probability for 2023, clipped to the country.
    cocoa_prob = (ee.ImageCollection(COCOA_MODEL)
                  .filterDate("2023-01-01", "2023-12-31")
                  .mosaic().clip(colombia))

    # 3. Threshold and cluster connected components at 1 km resolution.
    mask = cocoa_prob.gt(COCOA_PROB_THRESHOLD).selfMask()
    vectors = mask.reduceToVectors(
        geometry=colombia, scale=1000, geometryType="polygon",
        eightConnected=True, maxPixels=1e9, tileScale=4)
    vectors = vectors.map(lambda f: f.set(
        "area_km2", f.geometry().area(1).divide(1e6)))

    # 4. Largest cluster -> centroid -> AOI.
    largest = vectors.sort("area_km2", False).first()
    centroid = largest.geometry().centroid(1).coordinates().getInfo()
    print(f"AOI centroid (Alto Sinu): {centroid}")
    aoi = ee.Geometry.Point(centroid).buffer(AOI_BUFFER_M).bounds(1)

    # 5. Vectorize parcels at native resolution within the AOI.
    parcels_mask = cocoa_prob.clip(aoi).gt(COCOA_PROB_THRESHOLD).selfMask()
    parcels_raw = parcels_mask.reduceToVectors(
        geometry=aoi, scale=SCALE, geometryType="polygon",
        eightConnected=True, maxPixels=1e9, tileScale=4)

    # Keep a realistic parcel-size range:
    #   lower bound 0.5 ha  (50 px)   -> excludes pixel-level noise
    #   upper bound  85 ha (8,500 px) -> ~99th percentile of observed sizes;
    #                                    excludes aggregated mega-clusters
    #                                    (>600 ha) that are not single plots
    parcels = parcels_raw.filter(ee.Filter.And(
        ee.Filter.gte("count", MIN_PARCEL_PIXELS),
        ee.Filter.lte("count", MAX_PARCEL_PIXELS),
    ))

    gdf = geemap.ee_to_gdf(parcels)
    gdf["farm_id"] = range(len(gdf))
    gdf["area_ha"] = gdf["count"] * 0.01  # one 10 m pixel = 100 m² = 0.01 ha
    gdf.to_file("data/farms.geojson", driver="GeoJSON")

    print(f"Parcels generated (0.5-85 ha): {len(gdf)}")
    print(gdf[["farm_id", "count", "area_ha"]].describe())


if __name__ == "__main__":
    main()
