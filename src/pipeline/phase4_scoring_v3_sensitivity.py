"""Phase 4 diagnostic: original vs self-masked distance feature.

Re-evaluates the two distance-bearing variants (C: distance only, F: the
selected full feature set) using the leakage-free ``dist_to_defo_m_masked``
instead of ``dist_to_defo_m``, to check how much of the model's performance
depended on within-parcel deforestation pixels.

Read-only: this script never writes to the database.
Run ``phase4_distance_masked.py`` first.
"""

import pandas as pd
from sqlalchemy import create_engine

from src.config import DATABASE_URL
from src.pipeline.scoring import evaluate_binary

#: Variants C and F, each with the original and the masked distance feature.
VARIANTS = {
    "C  orig   [dist only]":         ["dist_to_defo_m"],
    "C  masked [dist only]":         ["dist_to_defo_m_masked"],
    "F  orig   [area+dist+nb multi]": ["area_ha", "dist_to_defo_m",
                                       "nb_defo_pct_200", "nb_defo_pct_500",
                                       "nb_defo_pct_1000"],
    "F  masked [area+dist+nb multi]": ["area_ha", "dist_to_defo_m_masked",
                                       "nb_defo_pct_200", "nb_defo_pct_500",
                                       "nb_defo_pct_1000"],
}


def main() -> None:
    engine = create_engine(DATABASE_URL)

    own = pd.read_sql("""
        SELECT f.farm_id, f.area_ha, a.defo_pct
        FROM farms f JOIN assessments a ON f.farm_id = a.farm_id
    """, engine)

    df = (own
          .merge(pd.read_csv("data/farms_neighborhood_multi.csv"), on="farm_id")
          .merge(pd.read_csv("data/farms_distance.csv"), on="farm_id")
          .merge(pd.read_csv("data/farms_distance_masked.csv"), on="farm_id"))

    y = (df["defo_pct"] > 0).astype(int).values
    delta = (df["dist_to_defo_m_masked"] - df["dist_to_defo_m"]).abs()

    print(f"Parcels: {len(df)}  | AFFECTED: {y.sum()}")
    print(f"Parcels where dist changed: {(delta > 0).sum()}")
    print(f"Max delta: {delta.max():.1f} m")

    rows = [
        {"model": kind, "variant": name, **evaluate_binary(kind, df[feats].values, y)}
        for kind in ("RF", "LR")
        for name, feats in VARIANTS.items()
    ]

    print("\n========== SENSITIVITY CHECK: original vs masked distance ==========")
    with pd.option_context("display.max_rows", None, "display.width", 160,
                           "display.max_colwidth", None):
        print(pd.DataFrame(rows).to_string(index=False))


if __name__ == "__main__":
    main()
