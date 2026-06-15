"""Phase 4 v3 -- non-leaky risk model with cross-validated model selection.

Improves on src/phase4_scoring.py (single train/test split, X=[area_ha,
neighborhood_defo_pct], poor & unstable macro-F1=0.43) by:

  * adding spatial-context features that never encode a parcel's own
    deforestation: multi-radius neighbourhood deforestation (200/500/1000 m)
    and distance from the parcel centroid to the nearest post-2020 loss pixel;
  * evaluating every feature set with stratified 5-fold cross-validation
    instead of one noisy split (only ~70 positives out of 4,170);
  * comparing a binary (AFFECTED/CLEAN) and a 3-class (LOW/MEDIUM/HIGH) framing,
    and two model families (RandomForest, scaled LogisticRegression).

The chosen BINARY model drives the deliverable: risk_score = P(AFFECTED) for
every parcel. risk_class stays the rule-based ground-truth label (as before).

Run the feature scripts first:
    uv run python src/phase4_distance.py
    uv run python src/phase4_neighborhood_multi.py
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (average_precision_score, f1_score,
                             roc_auc_score)
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sqlalchemy import create_engine, text

ENGINE_URL = "postgresql://eudr:eudr_dev_password@localhost:5432/eudr_risk"
engine = create_engine(ENGINE_URL)

RANDOM_STATE = 42
DEFO_MEDIAN_AFFECTED = 5.3755  # median defo_pct among affected parcels (v2)


# --------------------------------------------------------------------------- #
# 1. Build the modelling frame
# --------------------------------------------------------------------------- #
def classify(pct):
    """Rule-based 3-class label from the parcel's OWN defo_pct (ground truth)."""
    if pct == 0:
        return "LOW"
    elif pct <= DEFO_MEDIAN_AFFECTED:
        return "MEDIUM"
    return "HIGH"


own = pd.read_sql("""
    SELECT f.farm_id, f.area_ha, a.defo_pct
    FROM farms f JOIN assessments a ON f.farm_id = a.farm_id
""", engine)

nb = pd.read_csv('data/farms_neighborhood_multi.csv')
dist = pd.read_csv('data/farms_distance.csv')

df = own.merge(nb, on='farm_id').merge(dist, on='farm_id')

# Labels (both framings) derived from the parcel's own deforestation.
df['risk_class'] = df['defo_pct'].apply(classify)              # 3-class
df['risk_binary'] = np.where(df['defo_pct'] > 0, 'AFFECTED', 'CLEAN')

print(f"Parcels: {len(df)}  | AFFECTED: {(df['risk_binary'] == 'AFFECTED').sum()}"
      f"  | 3-class: {df['risk_class'].value_counts().to_dict()}")


# --------------------------------------------------------------------------- #
# 2. Feature sets (none encodes the parcel's own defo_pct)
# --------------------------------------------------------------------------- #
FEATURE_SETS = {
    "A: area+nb200 (baseline)": ["area_ha", "nb_defo_pct_200"],
    "B: nb200 only":            ["nb_defo_pct_200"],
    "C: distance only":         ["dist_to_defo_m"],
    "D: nb 200+500+1000":       ["nb_defo_pct_200", "nb_defo_pct_500",
                                 "nb_defo_pct_1000"],
    "E: dist + nb multi":       ["dist_to_defo_m", "nb_defo_pct_200",
                                 "nb_defo_pct_500", "nb_defo_pct_1000"],
    "F: E + area":              ["area_ha", "dist_to_defo_m", "nb_defo_pct_200",
                                 "nb_defo_pct_500", "nb_defo_pct_1000"],
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


def importances(kind, model, feats):
    """Return a feature->importance dict for the refit-on-all model."""
    if kind == "RF":
        vals = model.feature_importances_
    else:  # standardized LR coefficients (binary -> 1 row)
        coef = model[-1].coef_
        vals = np.abs(coef).mean(axis=0)
    return {f: round(float(v), 3) for f, v in zip(feats, vals)}


# --------------------------------------------------------------------------- #
# 3. Cross-validated comparison
# --------------------------------------------------------------------------- #
rows = []          # comparison table
importance_log = {}  # variant -> {feature: importance}

for kind in ("RF", "LR"):
    for name, feats in FEATURE_SETS.items():
        X = df[feats].values

        # ---- Binary framing: AUC-ROC + PR-AUC + macro-F1 ----
        y_bin = (df['risk_binary'] == 'AFFECTED').astype(int).values
        proba = cross_val_predict(make_model(kind), X, y_bin, cv=cv,
                                  method='predict_proba', n_jobs=-1)[:, 1]
        pred = cross_val_predict(make_model(kind), X, y_bin, cv=cv, n_jobs=-1)
        rows.append({
            "model": kind, "framing": "binary", "features": name,
            "roc_auc": round(roc_auc_score(y_bin, proba), 3),
            "pr_auc": round(average_precision_score(y_bin, proba), 3),
            "macro_f1": round(f1_score(y_bin, pred, average='macro'), 3),
        })

        # ---- 3-class framing: macro-F1 ----
        y_multi = df['risk_class'].values
        pred_m = cross_val_predict(make_model(kind), X, y_multi, cv=cv,
                                   n_jobs=-1)
        rows.append({
            "model": kind, "framing": "3-class", "features": name,
            "roc_auc": np.nan, "pr_auc": np.nan,
            "macro_f1": round(f1_score(y_multi, pred_m, average='macro'), 3),
        })

        # ---- feature importances (fit on all rows, binary) ----
        m = make_model(kind)
        m.fit(X, y_bin)
        importance_log[f"{kind} | {name}"] = importances(kind, m, feats)

table = pd.DataFrame(rows)
print("\n================ MODEL COMPARISON ================")
with pd.option_context('display.max_rows', None, 'display.width', 160):
    print(table.to_string(index=False))

print("\n================ FEATURE IMPORTANCES (binary, fit-all) ================")
for variant, imp in importance_log.items():
    print(f"{variant}: {imp}")


# --------------------------------------------------------------------------- #
# 4. Select best non-leaky BINARY variant (by PR-AUC, tie-break: fewer feats)
# --------------------------------------------------------------------------- #
bin_tbl = table[table['framing'] == 'binary'].copy()
bin_tbl['n_feats'] = bin_tbl['features'].map(
    lambda n: len(FEATURE_SETS[n]))
bin_tbl = bin_tbl.sort_values(
    ['pr_auc', 'roc_auc'], ascending=False)

best = bin_tbl.iloc[0]
best_feats = FEATURE_SETS[best['features']]
print(f"\n>>> SELECTED: {best['model']} | {best['features']} "
      f"| PR-AUC={best['pr_auc']} ROC-AUC={best['roc_auc']} "
      f"macro-F1={best['macro_f1']}")

# Refit on all parcels and score everyone.
final_model = make_model(best['model'])
y_bin_all = (df['risk_binary'] == 'AFFECTED').astype(int).values
final_model.fit(df[best_feats].values, y_bin_all)
pos_idx = list(final_model.classes_).index(1)
df['risk_score'] = final_model.predict_proba(
    df[best_feats].values)[:, pos_idx].round(4)


# --------------------------------------------------------------------------- #
# 5. Early-warning output: CLEAN parcels with the highest modelled risk
# --------------------------------------------------------------------------- #
early = (df[df['risk_binary'] == 'CLEAN']
         .sort_values('risk_score', ascending=False)
         .head(10))
print("\nTop 10 early-warning candidates (CLEAN today, elevated risk_score):")
print(early[['farm_id', 'area_ha', 'dist_to_defo_m',
             'nb_defo_pct_200', 'nb_defo_pct_500', 'risk_score']]
      .to_string(index=False))


# --------------------------------------------------------------------------- #
# 6. Update the assessments table (rule-based class + modelled score)
# --------------------------------------------------------------------------- #
with engine.begin() as conn:
    for _, row in df.iterrows():
        conn.execute(text("""
            UPDATE assessments
            SET risk_score = :score, risk_class = :cls
            WHERE farm_id = :fid
        """), {"score": float(row["risk_score"]),
               "cls": row["risk_class"], "fid": int(row["farm_id"])})

print(f"\nUpdated {len(df)} assessment rows "
      f"(risk_class=rule-based, risk_score=P(AFFECTED)).")
