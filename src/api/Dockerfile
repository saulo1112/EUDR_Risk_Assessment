# EUDR Risk API — FastAPI served by uvicorn.
# Build context is the repo root (see docker/docker-compose.yml).
FROM python:3.11-slim

# uv for fast, reproducible installs.
RUN pip install --no-cache-dir uv

WORKDIR /app

# pyproject.toml is copied for reference/provenance. The full project pins
# heavy geospatial/ML deps (earthengine, geemap, rasterio, geopandas) that are
# only used by the OFFLINE pipeline — the API needs none of them at runtime.
# We therefore install just the API subset to keep the image small and fast.
# (Versions mirror the relevant entries in pyproject.toml.)
COPY pyproject.toml ./
RUN uv pip install --system --no-cache \
    "fastapi>=0.110.0" \
    "uvicorn[standard]>=0.29.0" \
    "sqlalchemy>=2.0.0" \
    "geoalchemy2>=0.14.0" \
    "psycopg2-binary>=2.9.0" \
    "python-dotenv>=1.0.0"

# Application code (src.api.main:app imports src.api.*).
COPY src/__init__.py ./src/__init__.py
COPY src/api ./src/api

EXPOSE 8000

# DATABASE_URL is provided by docker-compose (points at the db service).
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
