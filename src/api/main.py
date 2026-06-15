"""EUDR Forest Risk Assessment — FastAPI backend.

Exposes the PostGIS ``farms`` + ``assessments`` data (4,170 cocoa parcels in the
Alto Sinú / Paramillo AOI, Colombia) as GeoJSON, ready for a future map
dashboard (Phase 6) and Docker deployment (Phase 7).

Run locally:
    uv run uvicorn src.api.main:app --reload
Then open http://localhost:8000/docs
"""

import json

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.engine import Connection

from src.api.database import get_connection
from src.api.schemas import (Feature, FeatureCollection, FarmProperties,
                             RiskClass, RiskClassStat, StatsResponse)

app = FastAPI(
    title="EUDR Forest Risk Assessment API",
    description=(
        "Serves deforestation-risk assessments for cocoa parcels in the "
        "Alto Sinú / Paramillo AOI (Colombia). Geometries are returned as "
        "GeoJSON. The flagship endpoint is **/early-warning**: parcels that are "
        "clean today but carry an elevated modelled risk."
    ),
    version="1.0.0",
)

# Allow any origin so a future Streamlit/Leaflet frontend can call the API
# directly. Fine for this demo; tighten before any real deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Columns shared by every parcel query: tabular attributes + GeoJSON geometry.
_SELECT = """
    SELECT f.farm_id, f.area_ha, a.defo_pct, a.risk_score, a.risk_class,
           ST_AsGeoJSON(f.geom) AS geometry
    FROM farms f
    JOIN assessments a ON f.farm_id = a.farm_id
"""


def _row_to_feature(row) -> Feature:
    """Turn a result row (mapping) into a GeoJSON Feature."""
    return Feature(
        geometry=json.loads(row["geometry"]),
        properties=FarmProperties(
            farm_id=row["farm_id"],
            area_ha=row["area_ha"],
            defo_pct=row["defo_pct"],
            risk_score=row["risk_score"],
            risk_class=row["risk_class"],
        ),
    )


@app.get("/", tags=["meta"])
def root() -> dict:
    """Basic API info and links."""
    return {
        "name": "EUDR Forest Risk Assessment API",
        "version": "1.0.0",
        "description": "Deforestation-risk assessments for cocoa parcels "
                       "(Alto Sinú / Paramillo, Colombia).",
        "endpoints": {
            "GET /farms": "List parcels as a GeoJSON FeatureCollection "
                          "(filter by risk_class, min_risk_score; paginated).",
            "GET /farms/{farm_id}": "Single parcel as a GeoJSON Feature.",
            "GET /stats": "Aggregate risk_score summary per risk_class.",
            "GET /early-warning": "Clean parcels with the highest modelled risk.",
        },
        "docs": "/docs",
        "openapi": "/openapi.json",
    }


@app.get("/farms", response_model=FeatureCollection, tags=["farms"])
def list_farms(
    conn: Connection = Depends(get_connection),
    risk_class: RiskClass | None = Query(
        None, description="Filter by risk class."),
    min_risk_score: float | None = Query(
        None, ge=0, le=1, description="Only parcels with risk_score >= this."),
    limit: int = Query(100, ge=1, le=10000, description="Max features to return."),
    offset: int = Query(0, ge=0, description="Number of features to skip."),
) -> FeatureCollection:
    """List parcels as a GeoJSON FeatureCollection, with optional filtering."""
    clauses, params = [], {"limit": limit, "offset": offset}
    if risk_class is not None:
        clauses.append("a.risk_class = :risk_class")
        params["risk_class"] = risk_class.value
    if min_risk_score is not None:
        clauses.append("a.risk_score >= :min_risk_score")
        params["min_risk_score"] = min_risk_score

    sql = _SELECT
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY f.farm_id LIMIT :limit OFFSET :offset"

    rows = conn.execute(text(sql), params).mappings().all()
    return FeatureCollection(features=[_row_to_feature(r) for r in rows])


@app.get("/farms/{farm_id}", response_model=Feature, tags=["farms"])
def get_farm(
    farm_id: int,
    conn: Connection = Depends(get_connection),
) -> Feature:
    """Single parcel as a GeoJSON Feature. 404 if the farm_id is unknown."""
    sql = _SELECT + " WHERE f.farm_id = :farm_id"
    row = conn.execute(text(sql), {"farm_id": farm_id}).mappings().first()
    if row is None:
        raise HTTPException(status_code=404,
                            detail=f"Farm {farm_id} not found.")
    return _row_to_feature(row)


@app.get("/stats", response_model=StatsResponse, tags=["stats"])
def get_stats(conn: Connection = Depends(get_connection)) -> StatsResponse:
    """Aggregate risk_score summary per risk_class, plus overall totals."""
    by_class = conn.execute(text("""
        SELECT a.risk_class,
               COUNT(*)            AS count,
               AVG(a.risk_score)   AS avg_risk_score,
               MIN(a.risk_score)   AS min_risk_score,
               MAX(a.risk_score)   AS max_risk_score
        FROM assessments a
        GROUP BY a.risk_class
        ORDER BY avg_risk_score DESC NULLS LAST
    """)).mappings().all()

    totals = conn.execute(text("""
        SELECT COUNT(*) AS total_parcels, SUM(area_ha) AS total_area_ha
        FROM farms
    """)).mappings().first()

    return StatsResponse(
        total_parcels=totals["total_parcels"],
        total_area_ha=round(float(totals["total_area_ha"] or 0), 2),
        by_risk_class=[
            RiskClassStat(
                risk_class=r["risk_class"],
                count=r["count"],
                avg_risk_score=(round(float(r["avg_risk_score"]), 4)
                                if r["avg_risk_score"] is not None else None),
                min_risk_score=r["min_risk_score"],
                max_risk_score=r["max_risk_score"],
            )
            for r in by_class
        ],
    )


@app.get("/early-warning", response_model=FeatureCollection, tags=["stats"])
def early_warning(
    conn: Connection = Depends(get_connection),
    limit: int = Query(10, ge=1, le=4100,
                       description="Number of top candidates to return."),
) -> FeatureCollection:
    """The flagship product: LOW-risk_class parcels (clean today) ranked by
    descending modelled risk_score — i.e. clean parcels surrounded by recent
    deforestation that warrant closer monitoring."""
    sql = (_SELECT
           + " WHERE a.risk_class = 'LOW'"
           + " ORDER BY a.risk_score DESC LIMIT :limit")
    rows = conn.execute(text(sql), {"limit": limit}).mappings().all()
    return FeatureCollection(features=[_row_to_feature(r) for r in rows])
