"""Unit tests for the pure scoring logic (no database, no Earth Engine)."""

import numpy as np
import pandas as pd
import pytest

from src.config import DEFO_MEDIAN_AFFECTED
from src.pipeline.scoring import (
    FEATURE_SETS,
    build_labels,
    classify,
    feature_importances,
    make_cv,
    make_model,
)


class TestClassify:
    """The rule-based ground-truth label, including its boundaries."""

    def test_zero_deforestation_is_low(self):
        assert classify(0) == "LOW"

    def test_any_deforestation_leaves_low(self):
        # EUDR is zero-tolerance: even a sliver of loss must not stay LOW.
        assert classify(0.001) == "MEDIUM"

    def test_at_threshold_is_medium(self):
        # The boundary is inclusive on the MEDIUM side.
        assert classify(DEFO_MEDIAN_AFFECTED) == "MEDIUM"

    def test_just_above_threshold_is_high(self):
        assert classify(DEFO_MEDIAN_AFFECTED + 0.001) == "HIGH"

    def test_fully_deforested_is_high(self):
        assert classify(100.0) == "HIGH"

    @pytest.mark.parametrize("pct,expected", [
        (0, "LOW"), (1.5, "MEDIUM"), (5.0, "MEDIUM"), (40.0, "HIGH"),
        (79.9, "HIGH"),
    ])
    def test_representative_values(self, pct, expected):
        assert classify(pct) == expected


class TestBuildLabels:
    def test_adds_both_framings(self):
        df = pd.DataFrame({"farm_id": [1, 2, 3], "defo_pct": [0.0, 2.0, 50.0]})
        out = build_labels(df)

        assert list(out["risk_class"]) == ["LOW", "MEDIUM", "HIGH"]
        assert list(out["risk_binary"]) == ["CLEAN", "AFFECTED", "AFFECTED"]

    def test_does_not_mutate_input(self):
        df = pd.DataFrame({"defo_pct": [0.0, 1.0]})
        build_labels(df)
        assert "risk_class" not in df.columns

    def test_binary_split_matches_multiclass(self):
        # CLEAN must be exactly the LOW set — the two framings agree by design.
        df = pd.DataFrame({"defo_pct": [0.0, 0.0, 3.0, 20.0]})
        out = build_labels(df)
        assert ((out["risk_binary"] == "CLEAN") == (out["risk_class"] == "LOW")).all()


class TestFeatureSets:
    def test_no_variant_leaks_the_label(self):
        # defo_pct (and anything derived from it) is the target, never a feature.
        leaky = {"defo_pct", "defo_m2", "risk_class", "risk_binary"}
        for name, features in FEATURE_SETS.items():
            assert not leaky.intersection(features), f"{name} leaks the label"

    def test_baseline_matches_v2_model(self):
        assert FEATURE_SETS["A: area+nb200 (baseline)"] == [
            "area_ha", "nb_defo_pct_200"]

    def test_selected_variant_has_all_features(self):
        assert set(FEATURE_SETS["F: E + area"]) == {
            "area_ha", "dist_to_defo_m", "nb_defo_pct_200", "nb_defo_pct_500",
            "nb_defo_pct_1000"}

    def test_all_variants_non_empty(self):
        assert all(features for features in FEATURE_SETS.values())


class TestModelFactory:
    @pytest.mark.parametrize("kind", ["RF", "LR"])
    def test_builds_unfitted_model(self, kind):
        model = make_model(kind)
        assert model is not None

    def test_rejects_unknown_kind(self):
        with pytest.raises(ValueError, match="Unknown model kind"):
            make_model("XGB")

    def test_models_are_reproducible(self):
        X = np.array([[1.0, 10.0], [2.0, 0.0], [3.0, 30.0], [4.0, 0.0]])
        y = np.array([1, 0, 1, 0])

        first = make_model("RF").fit(X, y).predict_proba(X)
        second = make_model("RF").fit(X, y).predict_proba(X)
        np.testing.assert_array_equal(first, second)

    def test_cv_is_stratified_and_seeded(self):
        cv = make_cv()
        assert cv.shuffle is True
        assert cv.random_state is not None


class TestFeatureImportances:
    def test_returns_one_value_per_feature(self):
        X = np.array([[1.0, 10.0], [2.0, 0.0], [3.0, 30.0], [4.0, 0.0]])
        y = np.array([1, 0, 1, 0])
        features = ["area_ha", "nb_defo_pct_200"]

        model = make_model("RF").fit(X, y)
        importances = feature_importances("RF", model, features)

        assert set(importances) == set(features)
        assert all(isinstance(v, float) for v in importances.values())

    def test_works_for_logistic_regression(self):
        X = np.array([[1.0, 10.0], [2.0, 0.0], [3.0, 30.0], [4.0, 0.0]])
        y = np.array([1, 0, 1, 0])

        model = make_model("LR").fit(X, y)
        importances = feature_importances("LR", model, ["a", "b"])

        assert set(importances) == {"a", "b"}
        assert all(v >= 0 for v in importances.values())  # absolute coefficients
