"""Pure scoring logic for the phase 4 risk model.

Deliberately free of side effects: importing this module never opens a database
connection nor initialises Earth Engine, so the logic can be unit-tested in
isolation. The orchestration (reading PostGIS, writing back risk scores) lives
in ``phase4_scoring_v3.py``.

None of the features defined here encode a parcel's own ``defo_pct`` — that is
the label. See ``docs/phase4_model_comparison.md`` for the leakage analysis.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, f1_score, roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from src.config import CV_FOLDS, DEFO_MEDIAN_AFFECTED, RANDOM_STATE

#: Feature sets compared during model selection. Ordered from the v2 baseline
#: (A) to the full feature set (F).
FEATURE_SETS: dict[str, list[str]] = {
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


def classify(pct: float) -> str:
    """Rule-based 3-class label from a parcel's OWN ``defo_pct``.

    This is the ground-truth label, not a model output: any post-2020
    deforestation moves a parcel out of LOW, and the MEDIUM/HIGH boundary is the
    median ``defo_pct`` among affected parcels.

    >>> classify(0)
    'LOW'
    >>> classify(1.5)
    'MEDIUM'
    >>> classify(40.0)
    'HIGH'
    """
    if pct == 0:
        return "LOW"
    if pct <= DEFO_MEDIAN_AFFECTED:
        return "MEDIUM"
    return "HIGH"


def build_labels(df: pd.DataFrame) -> pd.DataFrame:
    """Add both label framings to a frame that has a ``defo_pct`` column.

    Returns a copy with ``risk_class`` (LOW/MEDIUM/HIGH) and ``risk_binary``
    (AFFECTED/CLEAN). EUDR compliance is zero-tolerance, so the binary framing
    splits on *any* post-2020 deforestation.
    """
    out = df.copy()
    out["risk_class"] = out["defo_pct"].apply(classify)
    out["risk_binary"] = np.where(out["defo_pct"] > 0, "AFFECTED", "CLEAN")
    return out


def make_model(kind: str):
    """Build an unfitted classifier.

    ``kind`` is ``"RF"`` (RandomForest) or ``"LR"`` (scaled LogisticRegression,
    used as a simpler baseline to check the forest is not merely overfitting).
    Both are class-weighted, since positives are ~1.7% of the sample.
    """
    if kind == "RF":
        return RandomForestClassifier(
            n_estimators=300, class_weight="balanced",
            random_state=RANDOM_STATE, n_jobs=-1)
    if kind == "LR":
        return make_pipeline(
            StandardScaler(),
            LogisticRegression(class_weight="balanced", max_iter=1000,
                               random_state=RANDOM_STATE))
    raise ValueError(f"Unknown model kind: {kind!r} (expected 'RF' or 'LR')")


def make_cv() -> StratifiedKFold:
    """Stratified k-fold used for every variant, so results are comparable."""
    return StratifiedKFold(n_splits=CV_FOLDS, shuffle=True,
                           random_state=RANDOM_STATE)


def feature_importances(kind: str, model, features: list[str]) -> dict[str, float]:
    """Return ``{feature: importance}`` for a model already fitted on all rows.

    Uses impurity importances for the forest and absolute standardized
    coefficients for logistic regression.
    """
    if kind == "RF":
        values = model.feature_importances_
    else:  # LR pipeline -> the estimator is the last step
        values = np.abs(model[-1].coef_).mean(axis=0)
    # strict=True: a length mismatch means the model was fitted on a different
    # feature set than the one being reported, which is a bug worth surfacing.
    return {f: round(float(v), 3) for f, v in zip(features, values, strict=True)}


def evaluate_binary(kind: str, X: np.ndarray, y: np.ndarray) -> dict[str, float]:
    """Cross-validated binary metrics for one model/feature-set combination.

    PR-AUC is the headline metric: with 70 positives against 4,100 negatives,
    ROC-AUC is inflated by the trivially-ranked majority class.
    """
    cv = make_cv()
    proba = cross_val_predict(make_model(kind), X, y, cv=cv,
                              method="predict_proba", n_jobs=-1)[:, 1]
    pred = cross_val_predict(make_model(kind), X, y, cv=cv, n_jobs=-1)
    return {
        "roc_auc": round(roc_auc_score(y, proba), 3),
        "pr_auc": round(average_precision_score(y, proba), 3),
        "macro_f1": round(f1_score(y, pred, average="macro"), 3),
    }


def evaluate_multiclass(kind: str, X: np.ndarray, y: np.ndarray) -> dict[str, float]:
    """Cross-validated macro-F1 for the 3-class framing."""
    pred = cross_val_predict(make_model(kind), X, y, cv=make_cv(), n_jobs=-1)
    return {"macro_f1": round(f1_score(y, pred, average="macro"), 3)}
