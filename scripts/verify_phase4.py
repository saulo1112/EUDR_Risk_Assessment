"""Post-run sanity check for phase 4 scoring.

Prints the risk-class distribution, verifies scores are populated and in range,
and shows the early-warning list. Complements ``tests/test_integration_db.py``,
which asserts the same invariants automatically.
"""

import pandas as pd
from sqlalchemy import create_engine

from src.config import DATABASE_URL

EXPECTED_PARCELS = 4170


def main() -> None:
    engine = create_engine(DATABASE_URL)

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
    print(summary.to_string(index=False))

    scored = pd.read_sql(
        "SELECT COUNT(*) AS n FROM assessments WHERE risk_score IS NOT NULL",
        engine)["n"][0]
    print(f"\nTotal scored parcels: {scored} (expected: {EXPECTED_PARCELS})")

    bounds = pd.read_sql(
        "SELECT MIN(risk_score) AS lo, MAX(risk_score) AS hi FROM assessments",
        engine)
    print(f"risk_score range: {bounds['lo'][0]} - {bounds['hi'][0]} "
          "(expected: within [0, 1])")

    early_warning = pd.read_sql("""
        SELECT f.farm_id, f.area_ha, a.defo_pct, a.risk_score
        FROM farms f JOIN assessments a ON f.farm_id = a.farm_id
        WHERE a.risk_class = 'LOW'
        ORDER BY a.risk_score DESC
        LIMIT 10
    """, engine)
    print("\n=== Top 10 early-warning candidates (LOW, highest risk_score) ===")
    print(early_warning.to_string(index=False))


if __name__ == "__main__":
    main()
