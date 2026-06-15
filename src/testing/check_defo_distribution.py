import pandas as pd
from sqlalchemy import create_engine

ENGINE_URL = "postgresql://eudr:eudr_dev_password@localhost:5432/eudr_risk"
engine = create_engine(ENGINE_URL)

df = pd.read_sql("""
    SELECT farm_id, defo_pct
    FROM assessments
    WHERE defo_pct > 0
    ORDER BY defo_pct DESC
""", engine)

print(f"Affected parcels: {len(df)}")
print(df['defo_pct'].describe())
print(df['defo_pct'].quantile([0.25, 0.5, 0.75, 0.9]))