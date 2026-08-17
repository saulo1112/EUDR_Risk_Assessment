"""Unit tests for the API's Pydantic response schemas."""

import pytest
from pydantic import ValidationError

from src.api.schemas import (
    FarmProperties,
    Feature,
    FeatureCollection,
    RiskClass,
    RiskClassStat,
    StatsResponse,
)

SQUARE = {"type": "Polygon",
          "coordinates": [[[-76.44, 8.52], [-76.43, 8.52],
                           [-76.43, 8.53], [-76.44, 8.53], [-76.44, 8.52]]]}


class TestRiskClass:
    def test_has_exactly_three_classes(self):
        assert {c.value for c in RiskClass} == {"LOW", "MEDIUM", "HIGH"}

    def test_accepts_valid_value(self):
        assert RiskClass("HIGH") is RiskClass.HIGH

    def test_rejects_unknown_value(self):
        with pytest.raises(ValueError):
            RiskClass("CRITICAL")


class TestFarmProperties:
    def test_farm_id_is_required(self):
        with pytest.raises(ValidationError):
            FarmProperties()

    def test_optional_fields_default_to_none(self):
        props = FarmProperties(farm_id=1)
        assert props.risk_score is None
        assert props.risk_class is None

    def test_coerces_numeric_strings(self):
        props = FarmProperties(farm_id="7", area_ha="2.5")
        assert props.farm_id == 7
        assert props.area_ha == 2.5


class TestFeature:
    def test_type_defaults_to_feature(self):
        feature = Feature(geometry=SQUARE, properties=FarmProperties(farm_id=1))
        assert feature.type == "Feature"

    def test_rejects_wrong_type_literal(self):
        with pytest.raises(ValidationError):
            Feature(type="Point", geometry=SQUARE,
                    properties=FarmProperties(farm_id=1))

    def test_serializes_to_valid_geojson(self):
        feature = Feature(geometry=SQUARE, properties=FarmProperties(farm_id=1))
        dumped = feature.model_dump()
        assert dumped["type"] == "Feature"
        assert dumped["geometry"]["type"] == "Polygon"
        assert dumped["properties"]["farm_id"] == 1


class TestFeatureCollection:
    def test_empty_collection_is_valid(self):
        collection = FeatureCollection(features=[])
        assert collection.type == "FeatureCollection"
        assert collection.features == []

    def test_holds_features(self):
        feature = Feature(geometry=SQUARE, properties=FarmProperties(farm_id=1))
        assert len(FeatureCollection(features=[feature, feature]).features) == 2


class TestStatsResponse:
    def test_full_payload(self):
        stats = StatsResponse(
            total_parcels=4170,
            total_area_ha=12099.52,
            by_risk_class=[
                RiskClassStat(risk_class="HIGH", count=35, avg_risk_score=0.9),
                RiskClassStat(risk_class="LOW", count=4100, avg_risk_score=0.0017),
            ],
        )
        assert stats.total_parcels == 4170
        assert len(stats.by_risk_class) == 2

    def test_score_stats_are_optional(self):
        # A class with no scored parcels yet still has a valid stat row.
        stat = RiskClassStat(risk_class="LOW", count=0)
        assert stat.avg_risk_score is None
