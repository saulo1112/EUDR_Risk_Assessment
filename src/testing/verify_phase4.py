import pandas as pd
from sqlalchemy import create_engine

ENGINE_URL = "postgresql://eudr:eudr_dev_password@localhost:5432/eudr_risk"
engine = create_engine(ENGINE_URL)

# 1. Overall check: distribution of risk_class and risk_score
summary = pd.read_sql("""
    SELECT risk_class, COUNT(*) AS n,
           ROUND(AVG(risk_score)::numeric, 4) AS avg_score,
           ROUND(MIN(risk_score)::numeric, 4) AS min_score,
           ROUND(MAX(risk_score)::numeric, 4) AS max_score
    FROM assessments
    GROUP BY risk_class
    ORDER BY avg_score DESC
""", engine)
print("=== Risk class summary ===")
print(summary)

# 2. Sanity checks
total = pd.read_sql("SELECT COUNT(*) AS n FROM assessments WHERE risk_score IS NOT NULL", engine)
print(f"\nTotal scored parcels: {total['n'][0]} (expected: 4170)")

bounds = pd.read_sql("""
    SELECT MIN(risk_score) AS min_s, MAX(risk_score) AS max_s
    FROM assessments
""", engine)
print(f"risk_score range: {bounds['min_s'][0]} - {bounds['max_s'][0]} (expected: within [0, 1])")

# 3. The actual product: early-warning list
# (LOW parcels with elevated risk_score despite no detected deforestation)
early_warning = pd.read_sql("""
    SELECT f.farm_id, f.area_ha, a.defo_pct, a.risk_score
    FROM farms f JOIN assessments a ON f.farm_id = a.farm_id
    WHERE a.risk_class = 'LOW'
    ORDER BY a.risk_score DESC
    LIMIT 10
""", engine)
print("\n=== Top 10 early-warning candidates (LOW, highest risk_score) ===")
print(early_warning)