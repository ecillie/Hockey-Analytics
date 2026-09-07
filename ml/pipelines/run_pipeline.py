from __future__ import annotations

import argparse

from ml.pipelines.build_model_dataset import (
    build_model_dataset,
    print_model_dataset_diagnostics,
)
from ml.pipelines.load_player_stats import load_player_stats
from ml.pipelines.load_salary_cap import load_salary_cap


def run_pipeline(
    min_games: int = 1,
):
    print("\n========================================")
    print(" HOCKEY ANALYTICS ML DATA PIPELINE")
    print("========================================")

    print("\n[1/3] Loading player stats...")

    players = load_player_stats(
        min_games=min_games
    )

    print(
        f"      {len(players):,} "
        "player-seasons"
    )

    print("\n[2/3] Loading salary caps...")

    salary_caps = load_salary_cap()

    print(
        f"      {len(salary_caps):,} "
        "salary-cap seasons"
    )

    print("\n[3/3] Building model dataset...")

    dataset = build_model_dataset(
        min_games=min_games
    )

    print_model_dataset_diagnostics(
        dataset
    )

    print("\n========================================")
    print(" PIPELINE COMPLETE")
    print("========================================")

    return dataset


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build the Hockey Analytics "
            "skater ML dataset."
        )
    )

    parser.add_argument(
        "--min-games",
        type=int,
        default=1,
        help=(
            "Minimum games played required "
            "for a player-season."
        ),
    )

    args = parser.parse_args()

    run_pipeline(
        min_games=args.min_games
    )


if __name__ == "__main__":
    main()
