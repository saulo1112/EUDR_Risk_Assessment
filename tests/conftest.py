"""Shared pytest fixtures.

The API fixtures override the ``get_connection`` dependency with an in-memory
stub, so endpoint behaviour (filtering, serialization, 404s, aggregation) is
tested without needing a live PostGIS instance.
"""

import json

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_connection
from src.api.main import app

#: A minimal parcel population covering all three risk classes. Geometries are
#: valid GeoJSON polygons, as PostGIS ST_AsGeoJSON would return them.
SAMPLE_PARCELS = [
    {"farm_id": 1, "area_ha": 0.50, "defo_pct": 0.0,  "risk_score": 0.01,
     "risk_class": "LOW"},
    {"farm_id": 2, "area_ha": 2.25, "defo_pct": 0.0,  "risk_score": 0.29,
     "risk_class": "LOW"},
    {"farm_id": 3, "area_ha": 5.00, "defo_pct": 3.10, "risk_score": 0.80,
     "risk_class": "MEDIUM"},
    {"farm_id": 4, "area_ha": 9.75, "defo_pct": 42.0, "risk_score": 0.95,
     "risk_class": "HIGH"},
]


def _geometry(farm_id: int) -> str:
    """A small square polygon, offset per parcel, as a GeoJSON string."""
    x, y = -76.44 + farm_id * 0.01, 8.52
    ring = [[x, y], [x + 0.005, y], [x + 0.005, y + 0.005], [x, y + 0.005], [x, y]]
    return json.dumps({"type": "Polygon", "coordinates": [ring]})


def _rows():
    return [{**p, "geometry": _geometry(p["farm_id"])} for p in SAMPLE_PARCELS]


class FakeResult:
    """Mimics the slice of SQLAlchemy's Result that the endpoints use."""

    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None

    def scalar(self):
        return self._rows[0] if self._rows else None


class FakeConnection:
    """Executes the API's SQL by pattern-matching, against in-memory rows.

    Deliberately simple: it recognises the shapes the API actually issues rather
    than implementing SQL. Real SQL is exercised by the integration tests.
    """

    def __init__(self, rows):
        self.rows = rows

    def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        params = params or {}

        if "GROUP BY a.risk_class" in sql:
            return FakeResult(self._grouped())
        if "SUM(area_ha)" in sql:
            return FakeResult([{
                "total_parcels": len(self.rows),
                "total_area_ha": sum(r["area_ha"] for r in self.rows),
            }])

        rows = self.rows
        if "f.farm_id = :farm_id" in sql:
            rows = [r for r in rows if r["farm_id"] == params.get("farm_id")]
            return FakeResult(rows)

        if "a.risk_class = 'LOW'" in sql:
            rows = [r for r in rows if r["risk_class"] == "LOW"]
            rows = sorted(rows, key=lambda r: r["risk_score"], reverse=True)
        else:
            if "a.risk_class = :risk_class" in sql:
                rows = [r for r in rows if r["risk_class"] == params["risk_class"]]
            if "a.risk_score >= :min_risk_score" in sql:
                rows = [r for r in rows
                        if r["risk_score"] >= params["min_risk_score"]]
            rows = sorted(rows, key=lambda r: r["farm_id"])

        offset = params.get("offset", 0)
        limit = params.get("limit", len(rows))
        return FakeResult(rows[offset:offset + limit])

    def _grouped(self):
        grouped = {}
        for row in self.rows:
            grouped.setdefault(row["risk_class"], []).append(row["risk_score"])
        return [
            {"risk_class": cls, "count": len(scores),
             "avg_risk_score": sum(scores) / len(scores),
             "min_risk_score": min(scores), "max_risk_score": max(scores)}
            for cls, scores in sorted(
                grouped.items(), key=lambda kv: -sum(kv[1]) / len(kv[1]))
        ]


@pytest.fixture
def sample_rows():
    return _rows()


@pytest.fixture
def client(sample_rows):
    """TestClient with the database dependency replaced by the fake."""
    app.dependency_overrides[get_connection] = lambda: FakeConnection(sample_rows)
    yield TestClient(app)
    app.dependency_overrides.clear()
