"""Integration tests against a live, seeded PostGIS database.

Opt-in, since they need infrastructure:

    docker compose -f docker/docker-compose.yml up -d db
    uv run pytest -m integration

They assert the published dataset invariants, the same numbers quoted in the
README, so a broken seed or a bad scoring run is caught rather than assumed.
"""

import pytest
from sqlalchemy import create_engine, text

from src.config import DATABASE_URL

pytestmark = pytest.mark.integration

EXPECTED_TOTAL = 4170
EXPECTED_BY_CLASS = {"LOW": 4100, "MEDIUM": 35, "HIGH": 35}
EXPECTED_TOP_EARLY_WARNING = 3123


@pytest.fixture(scope="module")
def connection():
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            yield conn
    except Exception as exc:  # pragma: no cover - infrastructure guard
        pytest.skip(f"PostGIS not reachable at {DATABASE_URL}: {exc}")


def test_postgis_extension_available(connection):
    assert connection.execute(text("SELECT postgis_version();")).scalar()


def test_parcel_count(connection):
    count = connection.execute(text("SELECT COUNT(*) FROM farms")).scalar()
    assert count == EXPECTED_TOTAL


def test_every_parcel_has_an_assessment(connection):
    orphans = connection.execute(text("""
        SELECT COUNT(*) FROM farms f
        LEFT JOIN assessments a ON f.farm_id = a.farm_id
        WHERE a.farm_id IS NULL
    """)).scalar()
    assert orphans == 0


def test_risk_class_distribution(connection):
    rows = connection.execute(text("""
        SELECT risk_class, COUNT(*) FROM assessments GROUP BY risk_class
    """)).all()
    assert dict(rows) == EXPECTED_BY_CLASS


def test_every_parcel_is_scored(connection):
    unscored = connection.execute(text(
        "SELECT COUNT(*) FROM assessments WHERE risk_score IS NULL")).scalar()
    assert unscored == 0


def test_risk_scores_are_probabilities(connection):
    lo, hi = connection.execute(text(
        "SELECT MIN(risk_score), MAX(risk_score) FROM assessments")).one()
    assert 0.0 <= lo <= hi <= 1.0


def test_risk_class_agrees_with_defo_pct(connection):
    """LOW must mean zero measured deforestation, the label is rule-based."""
    inconsistent = connection.execute(text("""
        SELECT COUNT(*) FROM assessments
        WHERE (risk_class = 'LOW' AND defo_pct > 0)
           OR (risk_class <> 'LOW' AND defo_pct = 0)
    """)).scalar()
    assert inconsistent == 0


def test_geometries_are_georeferenced_polygons(connection):
    """Every parcel must be a non-empty EPSG:4326 polygon."""
    srids = connection.execute(text(
        "SELECT DISTINCT ST_SRID(geom) FROM farms")).scalars().all()
    assert srids == [4326]

    types = connection.execute(text(
        "SELECT DISTINCT ST_GeometryType(geom) FROM farms")).scalars().all()
    assert types == ["ST_Polygon"]

    unusable = connection.execute(text(
        "SELECT COUNT(*) FROM farms WHERE geom IS NULL OR ST_IsEmpty(geom)")).scalar()
    assert unusable == 0


def test_selfintersecting_rings_are_repairable(connection):
    """Documents a known property of the dataset rather than asserting it away.

    ~87% of parcels (3,655/4,170) fail ST_IsValid with "Ring Self-intersection".
    This is an artefact of vectorizing a 10 m raster: pixel-derived polygons
    touch at diagonal corners. It does not affect this project's results:
    ``area_ha`` comes from the pixel count (not ST_Area), the model features are
    computed in Earth Engine, and ST_AsGeoJSON serializes these geometries fine.

    It *would* matter for spatial overlays (ST_Intersection / ST_Union / spatial
    joins), so the invariant worth guarding is that every such geometry is
    repairable with ST_MakeValid. See docs/CODE_AUDIT.md.
    """
    invalid, repairable = connection.execute(text("""
        SELECT COUNT(*) FILTER (WHERE NOT ST_IsValid(geom)),
               COUNT(*) FILTER (WHERE NOT ST_IsValid(geom)
                                AND ST_IsValid(ST_MakeValid(geom)))
        FROM farms
    """)).one()

    assert invalid == repairable, (
        f"{invalid - repairable} geometries cannot be repaired by ST_MakeValid")


def test_pixel_area_agrees_with_geometry_area(connection):
    """``area_ha`` (from the pixel count) must match the geodesic polygon area.

    A wide divergence would mean the geometries and the attribute disagree about
    what a parcel is. Tolerance is loose because pixel-outline polygons only
    approximate the projected footprint.
    """
    max_diff_pct = connection.execute(text("""
        SELECT MAX(ABS(area_ha - ST_Area(geom::geography) / 10000)
                   / NULLIF(area_ha, 0) * 100)
        FROM farms
    """)).scalar()
    assert max_diff_pct < 5.0, f"areas diverge by up to {max_diff_pct:.2f}%"


def test_top_early_warning_parcel(connection):
    """The flagship result: the highest-risk parcel that is still clean."""
    farm_id, defo_pct = connection.execute(text("""
        SELECT farm_id, defo_pct FROM assessments
        WHERE risk_class = 'LOW'
        ORDER BY risk_score DESC LIMIT 1
    """)).one()

    assert farm_id == EXPECTED_TOP_EARLY_WARNING
    assert defo_pct == 0.0
