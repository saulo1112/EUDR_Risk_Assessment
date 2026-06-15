"""Database access for the EUDR risk API.

A single SQLAlchemy engine backed by a connection pool is created at import
time and shared across all requests (rather than opening a new connection per
request). GeoAlchemy2 is imported so its geometry types are registered with
SQLAlchemy, even though the read endpoints fetch geometries as GeoJSON text via
PostGIS ``ST_AsGeoJSON``.
"""

import os

import geoalchemy2  # noqa: F401  (registers PostGIS geometry types with SQLAlchemy)
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Connection

load_dotenv()

DEFAULT_DATABASE_URL = (
    "postgresql://eudr:eudr_dev_password@localhost:5432/eudr_risk"
)
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)

# Pooled engine shared by the whole app. pool_pre_ping recycles stale
# connections (e.g. after the Docker DB restarts) transparently.
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
