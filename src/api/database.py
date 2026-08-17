"""Database access for the EUDR risk API.

A single SQLAlchemy engine backed by a connection pool is created at import time
and shared across all requests, rather than opening a new connection per
request. GeoAlchemy2 is imported so its geometry types are registered with
SQLAlchemy, even though the read endpoints fetch geometries as GeoJSON text via
PostGIS ``ST_AsGeoJSON``.
"""

import geoalchemy2  # noqa: F401  (registers PostGIS geometry types)
from sqlalchemy import create_engine
from sqlalchemy.engine import Connection

from src.config import DATABASE_URL

# Pooled engine shared by the whole app. pool_pre_ping transparently recycles
# stale connections, e.g. after the Docker database restarts.
engine = create_engine(
    DATABASE_URL,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    future=True,
)


def get_connection() -> Connection:
    """FastAPI dependency: yield a pooled connection, returned on completion."""
    with engine.connect() as conn:
        yield conn
