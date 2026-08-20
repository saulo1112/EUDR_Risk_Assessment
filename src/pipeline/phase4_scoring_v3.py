"""Phase 4 v3: non-leaky risk model with cross-validated model selection.

Improves on the v2 model (``legacy/phase4_scoring.py``: single train/test split,
X=[area_ha, neighborhood_defo_pct], unstable macro-F1 = 0.43) by:

  * adding spatial-context features that never encode a parcel's own
    deforestation: multi-radius neighbourhood loss (200/500/1000 m) and
    distance from the parcel centroid to the nearest post-2020 loss pixel;
  * evaluating every feature set with stratified 5-fold cross-validation
    instead of one noisy split (only ~70 positives out of 4,170);
  * comparing binary (AFFECTED/CLEAN) and 3-class (LOW/MEDIUM/HIGH) framings
    across two model families (RandomForest, scaled LogisticRegression).

The selected binary model drives the deliverable: ``risk_score`` = P(AFFECTED)
for every parcel. ``risk_class`` remains the rule-based ground-truth label.

Prerequisites (see docs/PIPELINE.md):
    uv run python -m src.pipeline.phase4_distance
    uv run python -m src.pipeline.phase4_neighborhood_multi
"""

import pandas as pd
from sqlalchemy import create_engine, text

from src.config import DATABASE_URL
from src.pipeline.scoring import (
    FEATURE_SETS,
    build_labels,
    evaluate_binary,
    evaluate_multiclass,
    feature_importances,
    make_model,
)


def load_dataset(engine) -> pd.DataFrame:
    """Join parcel attributes from PostGIS with the engineered feature CSVs."""
    own = pd.read_sql("""
        SELECT f.farm_id, f.area_ha, a.defo_pct
        FROM farms f JOIN assessments a ON f.farm_id = a.farm_id
    """, engine)

    neighbourhood = pd.read_csv("data/farms_neighborhood_multi.csv")
    distance = pd.read_csv("data/farms_distance.csv")

    df = own.merge(neighbourhood, on="farm_id").merge(distance, on="farm_id")
    return build_labels(df)


def compare_variants(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Cross-validate every model x feature-set x framing combination."""
    y_binary = (df["risk_binary"] == "AFFECTED").astype(int).values
    y_multi = df["risk_class"].values

    rows, importances = [], {}
    for kind in ("RF", "LR"):
        for name, features in FEATURE_SETS.items():
            X = df[features].values

            rows.append({"model": kind, "framing": "binary", "features": name,
                         **evaluate_binary(kind, X, y_binary)})
            rows.append({"model": kind, "framing": "3-class", "features": name,
                         "roc_auc": None, "pr_auc": None,
                         **evaluate_multiclass(kind, X, y_multi)})

            fitted = make_model(kind).fit(X, y_binary)
            importances[f"{kind} | {name}"] = feature_importances(
                kind, fitted, features)

    return pd.DataFrame(rows), importances


def select_best_binary(table: pd.DataFrame) -> pd.Series:
    """Pick the best binary variant by PR-AUC, tie-broken on ROC-AUC."""
    binary = table[table["framing"] == "binary"]
    return binary.sort_values(["pr_auc", "roc_auc"], ascending=False).iloc[0]


def update_assessments(engine, df: pd.DataFrame) -> None:
    """Write the rule-based class and the modelled score back to PostGIS."""
    with engine.begin() as conn:
        for _, row in df.iterrows():
            conn.execute(text("""
                UPDATE assessments
                SET risk_score = :score, risk_class = :cls
                WHERE farm_id = :fid
            """), {"score": float(row["risk_score"]),
                   "cls": row["risk_class"], "fid": int(row["farm_id"])})


def main() -> None:
    engine = create_engine(DATABASE_URL)

    df = load_dataset(engine)
    print(f"Parcels: {len(df)}  | "
          f"AFFECTED: {(df['risk_binary'] == 'AFFECTED').sum()}  | "
          f"3-class: {df['risk_class'].value_counts().to_dict()}")

    table, importances = compare_variants(df)

    print("\n================ MODEL COMPARISON ================")
    with pd.option_context("display.max_rows", None, "display.width", 160):
        print(table.to_string(index=False))

    print("\n=========== FEATURE IMPORTANCES (binary, fit-all) ===========")
    for variant, importance in importances.items():
        print(f"{variant}: {importance}")

    best = select_best_binary(table)
    best_features = FEATURE_SETS[best["features"]]
    print(f"\n>>> SELECTED: {best['model']} | {best['features']} "
          f"| PR-AUC={best['pr_auc']} ROC-AUC={best['roc_auc']} "
          f"macro-F1={best['macro_f1']}")

    # Refit the winner on every parcel and score the full population.
    y_binary = (df["risk_binary"] == "AFFECTED").astype(int).values
    final_model = make_model(best["model"]).fit(df[best_features].values, y_binary)
    positive_idx = list(final_model.classes_).index(1)
    df["risk_score"] = final_model.predict_proba(
        df[best_features].values)[:, positive_idx].round(4)

    # The product output: parcels that are clean today but sit in actively
    # cleared surroundings.
    early = (df[df["risk_binary"] == "CLEAN"]
             .sort_values("risk_score", ascending=False)
             .head(10))
    print("\nTop 10 early-warning candidates (CLEAN today, elevated risk_score):")
    print(early[["farm_id", "area_ha", "dist_to_defo_m",
                 "nb_defo_pct_200", "nb_defo_pct_500", "risk_score"]]
          .to_string(index=False))

    update_assessments(engine, df)
    print(f"\nUpdated {len(df)} assessment rows "
          f"(risk_class=rule-based, risk_score=P(AFFECTED)).")


if __name__ == "__main__":
    main()
