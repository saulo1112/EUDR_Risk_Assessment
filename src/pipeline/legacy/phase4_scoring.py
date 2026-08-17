"""SUPERSEDED — the Phase 4 "v2" model, kept for documentation only.

RandomForest on ``[area_ha, neighborhood_defo_pct]`` (200 m ring) with a single
train/test split. It scored macro-F1 = 0.43: honest (no target leakage) but
underpowered with only 70 positives out of 4,170 parcels.

Replaced by ``src/pipeline/phase4_scoring_v3.py``, which adds multi-radius
neighbourhood and distance-to-deforestation features and evaluates with
stratified 5-fold cross-validation. This script also writes the now-unused
``data/farms_neighborhood.csv`` (200 m only); v3 reads
``data/farms_neighborhood_multi.csv`` instead.

NOT part of the canonical pipeline — do not run it for a fresh build. See
``docs/PIPELINE.md`` for the run order and ``docs/phase4_model_comparison.md``
for the full v1 -> v2 -> v3 progression.
"""

import ee
import geemap
import geopandas as gpd
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from sqlalchemy import create_engine, text

from src.config import DATABASE_URL, DEFO_MEDIAN_AFFECTED, RANDOM_STATE, SCALE
from src.pipeline.earth_engine import defo_area_bands, init, iter_batches

BUFFER_M = 200


def main() -> None:
    init()
    engine = create_engine(DATABASE_URL)

    # --- Step 1: neighborhood_defo_pct (200 m ring around each parcel) ---
    gdf = gpd.read_file("data/farms.geojson")
    combined = defo_area_bands()

    results = []
    for start, chunk in iter_batches(gdf):
        farms_chunk = geemap.geopandas_to_ee(chunk)

        # Ring = buffer(200 m) minus the parcel itself.
        rings = farms_chunk.map(lambda f: f.setGeometry(
            f.geometry().buffer(BUFFER_M).difference(f.geometry())))

        stats = combined.reduceRegions(
            collection=rings, reducer=ee.Reducer.sum(),
            scale=SCALE, tileScale=4)
        stats_no_geom = stats.map(lambda f: ee.Feature(None, f.toDictionary()))
        results.append(geemap.ee_to_df(stats_no_geom))
        print(f"Neighborhood stats: {min(start + len(chunk), len(gdf))}/{len(gdf)}")

    neighborhood = pd.concat(results, ignore_index=True)
    neighborhood["neighborhood_defo_pct"] = (
        neighborhood["defo_m2"] / neighborhood["total_m2"] * 100).round(3)
    neighborhood = neighborhood[["farm_id", "neighborhood_defo_pct"]]
    neighborhood.to_csv("data/farms_neighborhood.csv", index=False)
    print(neighborhood["neighborhood_defo_pct"].describe())

    # --- Step 2: label from OWN defo_pct, feature from the neighbourhood ---
    own = pd.read_sql("""
        SELECT f.farm_id, f.area_ha, a.defo_pct
        FROM farms f JOIN assessments a ON f.farm_id = a.farm_id
    """, engine)

    df = own.merge(neighborhood, on="farm_id")

    def classify(pct):
        if pct == 0:
            return "LOW"
        elif pct <= DEFO_MEDIAN_AFFECTED:
            return "MEDIUM"
        return "HIGH"

    df["risk_class"] = df["defo_pct"].apply(classify)

    # --- Step 3: train WITHOUT the parcel's own defo_pct as a feature ---
    X = df[["area_ha", "neighborhood_defo_pct"]]
    y = df["risk_class"]

    Xtr, Xte, ytr, yte = train_test_split(
        X, y, stratify=y, test_size=0.25, random_state=RANDOM_STATE)

    clf = RandomForestClassifier(
        n_estimators=300, class_weight="balanced", random_state=RANDOM_STATE)
    clf.fit(Xtr, ytr)

    print(classification_report(yte, clf.predict(Xte)))
    print(confusion_matrix(yte, clf.predict(Xte)))

    # --- Step 4: risk_score = P(HIGH) for all parcels ---
    proba = clf.predict_proba(X)
    high_idx = list(clf.classes_).index("HIGH")
    df["risk_score"] = proba[:, high_idx].round(4)

    early_warning = df[df["risk_class"] == "LOW"].sort_values(
        "risk_score", ascending=False).head(10)
    print("\nTop 10 early-warning candidates (LOW today, elevated risk_score):")
    print(early_warning[["farm_id", "area_ha", "neighborhood_defo_pct",
                         "risk_score"]])

    # --- Step 5: update the assessments table ---
    with engine.begin() as conn:
        for _, row in df.iterrows():
            conn.execute(text("""
                UPDATE assessments
                SET risk_score = :score, risk_class = :cls
                WHERE farm_id = :fid
            """), {"score": float(row["risk_score"]),
                   "cls": row["risk_class"], "fid": int(row["farm_id"])})

    print("Assessments updated with neighborhood-based risk_score.")


if __name__ == "__main__":
    main()
