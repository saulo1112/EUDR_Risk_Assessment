"""Phase 2: per-parcel post-2020 deforestation.

For every parcel, sum the area of pixels that Hansen GFC flags as lost in 2021
or later and that JRC GFC2020 classified as forest at the EUDR cutoff date.

Output: ``data/farms_risk_raw.csv`` (farm_id, defo_m2, total_m2, defo_pct)
"""

import ee
import geemap
import geopandas as gpd
import pandas as pd

from src.config import SCALE
from src.pipeline.earth_engine import defo_area_bands, init, iter_batches


def main() -> None:
    init()

    gdf = gpd.read_file("data/farms.geojson")
    combined = defo_area_bands()

    results = []
    for start, chunk in iter_batches(gdf):
        farms_chunk = geemap.geopandas_to_ee(chunk)

        stats = combined.reduceRegions(
            collection=farms_chunk, reducer=ee.Reducer.sum(),
            scale=SCALE, tileScale=4)
        stats_no_geom = stats.map(lambda f: ee.Feature(None, f.toDictionary()))

        results.append(geemap.ee_to_df(stats_no_geom))
        print(f"Processed {min(start + len(chunk), len(gdf))}/{len(gdf)}")

    df = pd.concat(results, ignore_index=True)
    df["defo_pct"] = (df["defo_m2"] / df["total_m2"] * 100).round(3)
    df.to_csv("data/farms_risk_raw.csv", index=False)

    print(f"Parcels processed: {len(df)}")
    print(f"Parcels with ANY post-2020 deforestation: {(df['defo_pct'] > 0).sum()}")
    print(df[["farm_id", "area_ha", "defo_m2", "defo_pct"]]
          .sort_values("defo_pct", ascending=False).head(10))


if __name__ == "__main__":
    main()
