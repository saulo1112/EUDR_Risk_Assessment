# EUDR Risk API: FastAPI served by uvicorn.
# Build context is the repo root (see docker/docker-compose.yml).
FROM python:3.11-slim

# uv for fast, reproducible installs.
RUN pip install --no-cache-dir uv

WORKDIR /app

# pyproject.toml is copied for reference/provenance. The full project pins
# heavy geospatial/ML deps (earthengine, geemap, rasterio, geopandas) that are
# only used by the OFFLINE pipeline; the API needs none of them at runtime.
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

# Application code. src.api.database reads its settings from src.config, so
# that module is required too; the pipeline packages are not.
COPY src/__init__.py ./src/__init__.py
COPY src/config.py ./src/config.py
COPY src/api ./src/api

EXPOSE 8000

# DATABASE_URL is provided by docker-compose (points at the db service) or by
# the hosting platform (e.g. Render's fromDatabase binding). PORT is injected
# by platforms like Render, which assign the listen port at deploy time; the
# shell form lets ${PORT} expand, falling back to 8000 for local/compose use
# where PORT is unset.
CMD ["sh", "-c", "uvicorn src.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
