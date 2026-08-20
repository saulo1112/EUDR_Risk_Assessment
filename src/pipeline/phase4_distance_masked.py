"""Phase 4 diagnostic: distance to deforestation with parcel self-masking.

``phase4_distance.py`` runs the distance transform over the whole deforestation
image, so for an AFFECTED parcel the nearest pixel may lie *inside* its own
boundary, partially encoding the label. This script recomputes the feature
with each parcel's own pixels erased first, to quantify that leakage.

CLEAN parcels have no own deforestation to mask, so their values are copied
unchanged; only the ~70 AFFECTED parcels need a per-parcel Earth Engine call.

Output: ``data/farms_distance_masked.csv`` (farm_id, dist_to_defo_m_masked)

Not part of the canonical pipeline, see docs/PIPELINE.md.
"""

import ee
import geemap
import geopandas as gpd
import pandas as pd

from src.config import DIST_CAP_M, NEIGHBORHOOD, SCALE
from src.pipeline.earth_engine import deforestation_mask, init


def masked_distance(defo: ee.Image, farm_gdf) -> float:
    """Distance in metres from one parcel's centroid to the nearest *external*
    deforestation pixel."""
    farm_ee = geemap.geopandas_to_ee(farm_gdf)

    # paint(fc, 0) erases this parcel's own pixels from the defo image.
    dist_img = (defo.paint(farm_ee, 0)
                .fastDistanceTransform(neighborhood=NEIGHBORHOOD, units="pixels")
                .sqrt().rename("dist_px"))

    centroid_fc = farm_ee.map(
        lambda f: f.setGeometry(f.geometry().centroid(maxError=1)))

    stats = dist_img.reduceRegions(
        collection=centroid_fc, reducer=ee.Reducer.first(),
        scale=SCALE, tileScale=4)
    stats_no_geom = stats.map(lambda f: ee.Feature(None, f.toDictionary()))
    result = geemap.ee_to_df(stats_no_geom)

    if result.empty or "first" not in result.columns:
        return float(DIST_CAP_M)  # fallback: treat as "far"
    return min(round(float(result["first"].iloc[0]) * SCALE, 1), DIST_CAP_M)


def main() -> None:
    init()

    gdf = gpd.read_file("data/farms.geojson")
    risk = pd.read_csv("data/farms_risk_raw.csv")[["farm_id", "defo_pct"]]
    dist_orig = pd.read_csv("data/farms_distance.csv")

    affected_ids = sorted(risk.loc[risk["defo_pct"] > 0, "farm_id"].astype(int))
    clean_ids = set(risk.loc[risk["defo_pct"] == 0, "farm_id"].astype(int))

    print(f"AFFECTED parcels to recompute: {len(affected_ids)}")
    print(f"CLEAN parcels to copy unchanged: {len(clean_ids)}")

    clean_rows = (dist_orig[dist_orig["farm_id"].isin(clean_ids)]
                  .rename(columns={"dist_to_defo_m": "dist_to_defo_m_masked"})
                  [["farm_id", "dist_to_defo_m_masked"]])

    defo = deforestation_mask()
    affected_results = []
    for i, fid in enumerate(affected_ids, start=1):
        dist_m = masked_distance(defo, gdf[gdf["farm_id"] == fid])
        affected_results.append({"farm_id": fid, "dist_to_defo_m_masked": dist_m})
        if i % 10 == 0 or i == len(affected_ids):
            print(f"AFFECTED processed: {i}/{len(affected_ids)}  "
                  f"(last farm_id={fid}, dist={dist_m} m)")

    affected_rows = pd.DataFrame(affected_results)

    result = pd.concat([clean_rows, affected_rows], ignore_index=True)
    result["farm_id"] = result["farm_id"].astype(int)
    result = result.sort_values("farm_id").reset_index(drop=True)
    result.to_csv("data/farms_distance_masked.csv", index=False)

    # Diagnostics: how much did masking move the affected parcels?
    comparison = (dist_orig[dist_orig["farm_id"].isin(affected_ids)]
                  .merge(affected_rows, on="farm_id"))
    comparison["delta"] = (comparison["dist_to_defo_m_masked"]
                           - comparison["dist_to_defo_m"])

    was_zero = comparison["dist_to_defo_m"] == 0
    print(f"\n--- Summary for AFFECTED parcels (n={len(comparison)}) ---")
    print(comparison[["dist_to_defo_m", "dist_to_defo_m_masked"]].describe())
    print(f"\nHad dist=0 before masking: {was_zero.sum()}")
    print("Now dist>0 after masking:  "
          f"{(was_zero & (comparison['dist_to_defo_m_masked'] > 0)).sum()}")
    print(f"Median delta (masked - original): {comparison['delta'].median():.1f} m")
    print(f"\nTotal rows written: {len(result)}")


if __name__ == "__main__":
    main()
