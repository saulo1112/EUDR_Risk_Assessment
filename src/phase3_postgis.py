import geopandas as gpd
import pandas as pd
from sqlalchemy import create_engine, text

ENGINE_URL = "postgresql://eudr:eudr_dev_password@localhost:5432/eudr_risk"
engine = create_engine(ENGINE_URL)

# 1. Create schema
schema_sql = """
CREATE EXTENSION IF NOT EXISTS postgis;

DROP TABLE IF EXISTS assessments;
DROP TABLE IF EXISTS farms;

CREATE TABLE farms (
    farm_id   INTEGER PRIMARY KEY,
    area_ha   DOUBLE PRECISION,
    commodity TEXT DEFAULT 'cocoa',
    geom      GEOMETRY(Polygon, 4326)
);
CREATE INDEX farms_geom_idx ON farms USING GIST (geom);

CREATE TABLE assessments (
    id          SERIAL PRIMARY KEY,
    farm_id     INTEGER REFERENCES farms(farm_id),
    defo_m2     DOUBLE PRECISION,
    total_m2    DOUBLE PRECISION,
    defo_pct    DOUBLE PRECISION,
    risk_score  DOUBLE PRECISION,
    risk_class  TEXT,
    assessed_at TIMESTAMP DEFAULT now()
);
"""

with engine.begin() as conn:
    conn.execute(text(schema_sql))
print("Schema created.")

# 2. Load farm geometries
farms = gpd.read_file("data/farms.geojson")[["farm_id", "area_ha", "geometry"]]
farms = farms.rename_geometry("geom")  # match the 'geom' column in our schema
farms.to_postgis("farms", engine, if_exists="append", index=False)
print(f"Loaded {len(farms)} farms.")

# 3. Load risk/deforestation results
risk = pd.read_csv("data/farms_risk_raw.csv")[
    ["farm_id", "defo_m2", "total_m2", "defo_pct"]
]
risk.to_sql("assessments", engine, if_exists="append", index=False)
print(f"Loaded {len(risk)} assessment records.")

# 4. Quick check
with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT f.farm_id, f.area_ha, a.defo_pct
        FROM farms f JOIN assessments a ON f.farm_id = a.farm_id
        ORDER BY a.defo_pct DESC LIMIT 5
    """))
    for row in result:
        print(row)