"""Pydantic response schemas (also drive the OpenAPI docs at /docs).

Geometries are returned as standard GeoJSON. ``geometry`` is kept as a free-form
object because PostGIS ``ST_AsGeoJSON`` may emit Polygon or MultiPolygon shapes.
"""

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class RiskClass(str, Enum):
    """Rule-based ground-truth risk class stored on each assessment."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class FarmProperties(BaseModel):
    """Tabular attributes carried in a GeoJSON Feature's ``properties``."""

    farm_id: int
    area_ha: float | None = None
    defo_pct: float | None = Field(
        default=None, description="% of the parcel deforested post-2020.")
    risk_score: float | None = Field(
        default=None, description="RandomForest P(AFFECTED), 0-1.")
    risk_class: str | None = Field(
        default=None, description="LOW / MEDIUM / HIGH (rule-based).")


class Feature(BaseModel):
    """A single GeoJSON Feature."""

    type: Literal["Feature"] = "Feature"
    geometry: dict[str, Any]
    properties: FarmProperties


class FeatureCollection(BaseModel):
    """A GeoJSON FeatureCollection."""

    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[Feature]


class RiskClassStat(BaseModel):
    """Aggregate risk_score statistics for one risk class."""

    risk_class: str
    count: int
    avg_risk_score: float | None = None
    min_risk_score: float | None = None
    max_risk_score: float | None = None


class StatsResponse(BaseModel):
    """Summary returned by /stats."""

    total_parcels: int
    total_area_ha: float
    by_risk_class: list[RiskClassStat]
