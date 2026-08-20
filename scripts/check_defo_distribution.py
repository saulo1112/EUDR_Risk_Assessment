"""Exploratory check: distribution of ``defo_pct`` among affected parcels.

This is where the MEDIUM/HIGH threshold (``DEFO_MEDIAN_AFFECTED = 5.3755``)
comes from: the median of the affected subpopulation.
"""

import pandas as pd
from sqlalchemy import create_engine

from src.config import DATABASE_URL


def main() -> None:
    engine = create_engine(DATABASE_URL)

    df = pd.read_sql("""
        SELECT farm_id, defo_pct
        FROM assessments
        WHERE defo_pct > 0
        ORDER BY defo_pct DESC
    """, engine)

    print(f"Affected parcels: {len(df)}")
    print(df["defo_pct"].describe())
    print(df["defo_pct"].quantile([0.25, 0.5, 0.75, 0.9]))


if __name__ == "__main__":
    main()
