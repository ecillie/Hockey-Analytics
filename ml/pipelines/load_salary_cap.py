from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import text


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.database import engine  # noqa: E402


SALARY_CAP_QUERY = text("""
SELECT
    start_year AS season,
    end_year,
    label AS season_label,
    salary_cap_cents,
    salary_cap_cents / 100.0 AS salary_cap_dollars

FROM seasons

WHERE salary_cap_cents IS NOT NULL

ORDER BY start_year;
""")


def load_salary_cap() -> pd.DataFrame:
    """Load NHL salary-cap history by season."""
    with engine.connect() as connection:
        return pd.read_sql(SALARY_CAP_QUERY, connection)


if __name__ == "__main__":
    df = load_salary_cap()

    print("\n=== SALARY CAP DATA ===")
    print(f"Rows: {len(df):,}")

    if not df.empty:
        print(
            f"Seasons: {df['season'].min()} - "
            f"{df['season'].max()}"
        )

        print("\nSalary caps:")
        print(
            df[
                [
                    "season",
                    "season_label",
                    "salary_cap_dollars",
                ]
            ].to_string(index=False)
        )
