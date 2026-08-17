"""Phase 4 feature — deforestation share in concentric rings around each parcel.

For each radius R the ring is ``buffer(R) \\ parcel``, so the feature measures
surrounding deforestation pressure and never encodes the parcel's own loss:

    nb_defo_pct_R = 100 * defo_m2(ring) / total_m2(ring)

Output: ``data/farms_neighborhood_multi.csv``
    (farm_id, nb_defo_pct_200, nb_defo_pct_500, nb_defo_pct_1000)
"""

import ee
import geemap
import geopandas as gpd
import pandas as pd

from src.config import BUFFERS_M, SCALE
from src.pipeline.earth_engine import defo_area_bands, init, iter_batches


def ring_stats(combined: ee.Image, gdf, buffer_m: int) -> pd.DataFrame:
    """Deforestation share within a ring of ``buffer_m`` around each parcel."""
    results = []
    for start, chunk in iter_batches(gdf):
        farms_chunk = geemap.geopandas_to_ee(chunk)

        # Ring = buffer(R) minus the parcel itself.
        rings = farms_chunk.map(lambda f: f.setGeometry(
            f.geometry().buffer(buffer_m).difference(f.geometry())))

        stats = combined.reduceRegions(
            collection=rings, reducer=ee.Reducer.sum(),
            scale=SCALE, tileScale=4)
        stats_no_geom = stats.map(lambda f: ee.Feature(None, f.toDictionary()))
        results.append(geemap.ee_to_df(stats_no_geom))
        print(f"[{buffer_m}m] {min(start + len(chunk), len(gdf))}/{len(gdf)}")

    ring = pd.concat(results, ignore_index=True)
    column = f"nb_defo_pct_{buffer_m}"
    ring[column] = (ring["defo_m2"] / ring["total_m2"] * 100).round(3)
    ring["farm_id"] = ring["farm_id"].astype(int)
    return ring[["farm_id", column]]


def main() -> None:
    init()

    gdf = gpd.read_file("data/farms.geojson")
    combined = defo_area_bands()

    merged = gdf[["farm_id"]].copy()
    merged["farm_id"] = merged["farm_id"].astype(int)

    for buffer_m in BUFFERS_M:
        merged = merged.merge(ring_stats(combined, gdf, buffer_m), on="farm_id")

    merged = merged.sort_values("farm_id").reset_index(drop=True)
    merged.to_csv("data/farms_neighborhood_multi.csv", index=False)

    print(f"\nParcels processed: {len(merged)}")
    print(merged[[f"nb_defo_pct_{b}" for b in BUFFERS_M]].describe())


if __name__ == "__main__":
    main()
