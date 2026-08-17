"""Connectivity check: confirm PostgreSQL and PostGIS are reachable."""

from sqlalchemy import create_engine, text

from src.config import DATABASE_URL


def main() -> None:
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        print(conn.execute(text("SELECT version();")).scalar())
        print(conn.execute(text("SELECT postgis_version();")).scalar())


if __name__ == "__main__":
    main()
