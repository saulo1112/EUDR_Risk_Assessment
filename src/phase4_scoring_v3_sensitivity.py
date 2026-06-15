"""Phase 4 v3 sensitivity check: original vs masked distance feature.

Compares variants C and F from phase4_scoring_v3.py using the original
dist_to_defo_m (unmasked, may include within-parcel defo pixels) against
dist_to_defo_m_masked (own-parcel pixels erased before the distance transform).

Only binary framing, RF + LR, same StratifiedKFold(5) as v3.

Run phase4_distance_masked.py first to produce data/farms_distance_masked.csv.
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, f1_score, roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sqlalchemy import create_engine

ENGINE_URL = "postgresql://eudr:eudr_dev_password@localhost:5432/eudr_risk"
engine = create_engine(ENGINE_URL)

RANDOM_STATE = 42

# ------------------------------------------------------------------ #
# Build the modelling frame
# ------------------------------------------------------------------ #
own = pd.read_sql("""
    SELECT f.farm_id, f.area_ha, a.defo_pct
    FROM farms f JOIN assessments a ON f.farm_id = a.farm_id
""", engine)

nb = pd.read_csv('data/farms_neighborhood_multi.csv')
dist_orig = pd.read_csv('data/farms_distance.csv')
dist_masked = pd.read_csv('data/farms_distance_masked.csv')

df = (own
      .merge(nb, on='farm_id')
      .merge(dist_orig, on='farm_id')
      .merge(dist_masked, on='farm_id'))

y_bin = (df['defo_pct'] > 0).astype(int).values

print(f"Parcels: {len(df)}  | AFFECTED: {y_bin.sum()}")
print(f"Parcels where dist changed: "
      f"{(df['dist_to_defo_m'] != df['dist_to_defo_m_masked']).sum()}")
print(f"Max delta: "
      f"{(df['dist_to_defo_m_masked'] - df['dist_to_defo_m']).abs().max():.1f} m")

# ------------------------------------------------------------------ #
# Feature sets: C and F, original vs masked
# ------------------------------------------------------------------ #
VARIANTS = {
    "C  orig  [dist only]":
        ["dist_to_defo_m"],
    "C  masked [dist only]":
        ["dist_to_defo_m_masked"],
    "F  orig  [area+dist+nb multi]":
        ["area_ha", "dist_to_defo_m",
         "nb_defo_pct_200", "nb_defo_pct_500", "nb_defo_pct_1000"],
    "F  masked [area+dist+nb multi]":
        ["area_ha", "dist_to_defo_m_masked",
         "nb_defo_pct_200", "nb_defo_pct_500", "nb_defo_pct_1000"],
}


def make_model(kind):
    if kind == "RF":
        return RandomForestClassifier(
            n_estimators=300, class_weight='balanced',
            random_state=RANDOM_STATE, n_jobs=-1)
    return make_pipeline(
        StandardScaler(),
        LogisticRegression(class_weight='balanced', max_iter=1000,
                           random_state=RANDOM_STATE))


cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)

rows = []
for kind in ("RF", "LR"):
    for name, feats in VARIANTS.items():
        X = df[feats].values
        proba = cross_val_predict(make_model(kind), X, y_bin, cv=cv,
                                  method='predict_proba', n_jobs=-1)[:, 1]
        pred = cross_val_predict(make_model(kind), X, y_bin, cv=cv, n_jobs=-1)
        rows.append({
            "model": kind,
            "variant": name,
            "roc_auc": round(roc_auc_score(y_bin, proba), 3),
            "pr_auc": round(average_precision_score(y_bin, proba), 3),
            "macro_f1": round(f1_score(y_bin, pred, average='macro'), 3),
        })

table = pd.DataFrame(rows)
print("\n========== SENSITIVITY CHECK: original vs masked distance ==========")
with pd.option_context('display.max_rows', None, 'display.width', 160,
                       'display.max_colwidth', None):
    print(table.to_string(index=False))
