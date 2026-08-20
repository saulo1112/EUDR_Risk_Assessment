"""Phase 4 feature: distance from each parcel centroid to the nearest
post-2020 deforestation pixel.

A non-leaky spatial-context feature: it never reads a parcel's own
deforestation status, only how far the parcel sits from recent forest loss.
Parcels embedded in actively cleared areas score a small distance; isolated
parcels score a large one.

Output: ``data/farms_distance.csv`` (farm_id, dist_to_defo_m)

Note: this computes distance over the *unmasked* deforestation image, so for an
affected parcel the nearest pixel may lie inside its own boundary. See
``phase4_distance_masked.py`` for the sensitivity check that quantifies the
resulting leakage.
"""

import ee
import geemap
import geopandas as gpd
import pandas as pd

from src.config import DIST_CAP_M, NEIGHBORHOOD, SCALE
from src.pipeline.earth_engine import deforestation_mask, init, iter_batches


def main() -> None:
    init()

    gdf = gpd.read_file("data/farms.geojson")

    # fastDistanceTransform returns squared distance in pixel units, capped at
    # the neighbourhood size; sqrt then scale to metres. Parcels beyond the cap
    # are simply "far": the exact value past a few km is not informative.
    dist_px = (deforestation_mask()
               .fastDistanceTransform(neighborhood=NEIGHBORHOOD, units="pixels")
               .sqrt().rename("dist_px"))

    results = []
    for start, chunk in iter_batches(gdf):
        farms_chunk = geemap.geopandas_to_ee(chunk)
        centroids = farms_chunk.map(
            lambda f: f.setGeometry(f.geometry().centroid(maxError=1)))

        stats = dist_px.reduceRegions(
            collection=centroids, reducer=ee.Reducer.first(),
            scale=SCALE, tileScale=4)
        stats_no_geom = stats.map(lambda f: ee.Feature(None, f.toDictionary()))

        results.append(geemap.ee_to_df(stats_no_geom))
        print(f"Distance sampled: {min(start + len(chunk), len(gdf))}/{len(gdf)}")

    dist = pd.concat(results, ignore_index=True)
    dist["dist_to_defo_m"] = (dist["first"] * SCALE).clip(upper=DIST_CAP_M).round(1)
    dist = dist[["farm_id", "dist_to_defo_m"]]
    dist["farm_id"] = dist["farm_id"].astype(int)
    dist = dist.sort_values("farm_id").reset_index(drop=True)
    dist.to_csv("data/farms_distance.csv", index=False)

    print(f"\nParcels processed: {len(dist)}  (cap = {DIST_CAP_M} m)")
    print(dist["dist_to_defo_m"].describe())
    print(f"Parcels at 0 m (on a defo pixel): {(dist['dist_to_defo_m'] == 0).sum()}")


if __name__ == "__main__":
    main()
