from __future__ import annotations

import pandas as pd

from ml.pipelines.load_player_stats import load_player_stats
from ml.pipelines.load_salary_cap import load_salary_cap


FORBIDDEN_CONTRACT_COLUMNS = {
    "contract_id",
    "contract_type",
    "average_value_cents",
    "cap_hit_cents",
    "cap_percentage",
    "actual_cap_hit",
    "aav",
}

# Fixed unit keeps cap context comparable across seasons without learning a
# scale from contracts or from the evaluation/test rows.
SALARY_CAP_NORMALIZATION_DOLLARS = 100_000_000.0


def build_model_dataset(
    min_games: int = 1,
) -> pd.DataFrame:
    """
    Build the base skater player-season dataset used by the ML pipeline.

    Includes:
      - player performance
      - position
      - season
      - NHL salary-cap environment

    Contract information is intentionally excluded.
    """

    players = load_player_stats(min_games=min_games)
    salary_cap = load_salary_cap()

    # Add salary-cap environment by season.
    df = players.merge(
        salary_cap[
            [
                "season",
                "season_label",
                "salary_cap_cents",
                "salary_cap_dollars",
            ]
        ],
        how="left",
        on="season",
        validate="many_to_one",
    )

    # Simplified position grouping.
    df["position_group"] = df["position"].map(
        {
            "C": "forward",
            "LW": "forward",
            "RW": "forward",
            "F": "forward",
            "D": "defense",
        }
    )
    df["salary_cap_fraction"] = (
        df["salary_cap_dollars"] / SALARY_CAP_NORMALIZATION_DOLLARS
    )

    # Ensure one observation per player-season.
    duplicate_count = df.duplicated(
        subset=["player_id", "season"]
    ).sum()

    if duplicate_count:
        raise RuntimeError(
            f"Model dataset contains {duplicate_count} "
            "duplicate player-season rows."
        )

    # Prevent accidental contract leakage.
    leaked_columns = FORBIDDEN_CONTRACT_COLUMNS.intersection(
        df.columns
    )

    if leaked_columns:
        raise RuntimeError(
            "Contract data leaked into model dataset: "
            f"{sorted(leaked_columns)}"
        )

    return df.reset_index(drop=True)


def print_model_dataset_diagnostics(
    df: pd.DataFrame,
) -> None:
    print("\n=== MODEL DATASET ===")
    print(f"Rows: {len(df):,}")

    if df.empty:
        print("No model rows found.")
        return

    print(f"Players: {df['player_id'].nunique():,}")

    print(
        f"Seasons: {df['season'].min()} - "
        f"{df['season'].max()}"
    )

    print(f"Columns: {len(df.columns)}")

    duplicates = df.duplicated(
        ["player_id", "season"]
    ).sum()

    print(
        f"Duplicate player-seasons: "
        f"{duplicates:,}"
    )

    advanced_count = (
        df["ice_time_seconds"]
        .notna()
        .sum()
    )

    salary_cap_count = (
        df["salary_cap_cents"]
        .notna()
        .sum()
    )

    print(
        "Advanced stats coverage: "
        f"{advanced_count:,} / {len(df):,}"
    )

    print(
        "Salary cap coverage: "
        f"{salary_cap_count:,} / {len(df):,}"
    )

    print("\nRows by position group:")

    print(
        df["position_group"]
        .value_counts(dropna=False)
        .to_string()
    )

    print("\nRows by season:")

    print(
        df.groupby("season")
        .size()
        .sort_index()
        .to_string()
    )

    sample_columns = [
        "player_name",
        "season",
        "position",
        "games_played",
        "goals",
        "assists",
        "points",
        "individual_expected_goals",
        "on_ice_expected_goals_pct",
        "game_score",
        "salary_cap_dollars",
    ]

    print("\nSample:")

    print(
        df[sample_columns]
        .head(15)
        .to_string(index=False)
    )


if __name__ == "__main__":
    dataset = build_model_dataset()
    print_model_dataset_diagnostics(dataset)
