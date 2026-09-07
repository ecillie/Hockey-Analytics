from __future__ import annotations

import pandas as pd

from ml.features.build_features import build_features


REPLACEMENT_PERCENTILE = 0.20


# Features where higher performance is better.
HIGHER_IS_BETTER = [
    "goals_per_60",
    "primary_assists_per_60",
    "secondary_assists_per_60",
    "points_per_60",
    "xg_per_60",
    "shots_on_goal_per_60",
    "unblocked_attempts_per_60",
    "game_score_per_60",
    "takeaways_per_60",
    "blocks_per_60",
    "penalties_drawn_per_60",
    "penalty_differential_per_60",
    "goals_above_expected_per_60",
    "on_ice_expected_goals_pct",
]

# Features where a lower number is better.
LOWER_IS_BETTER = [
    "giveaways_per_60",
    "penalties_per_60",
]

REPLACEMENT_FEATURES = (
    HIGHER_IS_BETTER
    + LOWER_IS_BETTER
)


def calculate_replacement_level(
    df: pd.DataFrame | None = None,
    replacement_percentile: float = REPLACEMENT_PERCENTILE,
) -> pd.DataFrame:
    """
    Calculate position- and season-specific replacement level.

    Replacement players are defined as the bottom specified
    percentile of training-eligible skaters by TOI per game.

    No contract information is used.
    """

    if df is None:
        df = build_features()

    result = df.copy()

    # ---------------------------------------------------------
    # TOI per game
    # ---------------------------------------------------------

    valid_games = result["games_played"].where(
        result["games_played"] > 0
    )

    result["toi_per_game"] = (
        result["toi_minutes"]
        / valid_games
    )

    # Only established NHL samples should define replacement level.
    eligible = result[
        result["eligible_for_training"]
        & result["position_group"].notna()
        & result["toi_per_game"].notna()
    ].copy()

    # ---------------------------------------------------------
    # Replacement TOI threshold
    # ---------------------------------------------------------

    thresholds = (
        eligible
        .groupby(
            ["season", "position_group"]
        )["toi_per_game"]
        .quantile(replacement_percentile)
        .rename(
            "replacement_toi_per_game_threshold"
        )
        .reset_index()
    )

    eligible = eligible.merge(
        thresholds,
        on=["season", "position_group"],
        how="left",
        validate="many_to_one",
    )

    # Bottom 20% by TOI/game becomes the replacement pool.
    replacement_pool = eligible[
        eligible["toi_per_game"]
        <= eligible[
            "replacement_toi_per_game_threshold"
        ]
    ].copy()

    # ---------------------------------------------------------
    # Replacement performance baselines
    # ---------------------------------------------------------

    baselines = (
        replacement_pool
        .groupby(
            ["season", "position_group"]
        )[REPLACEMENT_FEATURES]
        .median()
        .reset_index()
    )

    baselines = baselines.rename(
        columns={
            feature: f"replacement_{feature}"
            for feature in REPLACEMENT_FEATURES
        }
    )

    result = result.merge(
        thresholds,
        on=["season", "position_group"],
        how="left",
        validate="many_to_one",
    )

    result = result.merge(
        baselines,
        on=["season", "position_group"],
        how="left",
        validate="many_to_one",
    )

    # ---------------------------------------------------------
    # Flag replacement-pool players
    # ---------------------------------------------------------

    replacement_keys = set(
        zip(
            replacement_pool["player_id"],
            replacement_pool["season"],
        )
    )

    result["is_replacement_pool"] = [
        (player_id, season)
        in replacement_keys
        for player_id, season
        in zip(
            result["player_id"],
            result["season"],
        )
    ]

    # ---------------------------------------------------------
    # Above-replacement features
    #
    # Positive value always means better than replacement.
    # ---------------------------------------------------------

    for feature in HIGHER_IS_BETTER:
        result[f"{feature}_above_replacement"] = (
            result[feature]
            - result[f"replacement_{feature}"]
        )

    for feature in LOWER_IS_BETTER:
        result[f"{feature}_above_replacement"] = (
            result[f"replacement_{feature}"]
            - result[feature]
        )

    return result.reset_index(drop=True)


def print_replacement_diagnostics(
    df: pd.DataFrame,
) -> None:
    print("\n=== REPLACEMENT LEVEL ===")

    print(f"Player-season rows: {len(df):,}")

    replacement_count = int(
        df["is_replacement_pool"].sum()
    )

    print(
        f"Replacement-pool rows: "
        f"{replacement_count:,}"
    )

    print(
        f"Replacement percentile: "
        f"{REPLACEMENT_PERCENTILE:.0%}"
    )

    print("\nReplacement players by position:")

    print(
        df.loc[
            df["is_replacement_pool"],
            "position_group",
        ]
        .value_counts()
        .to_string()
    )

    print("\nReplacement TOI thresholds:")

    thresholds = (
        df[
            [
                "season",
                "position_group",
                "replacement_toi_per_game_threshold",
            ]
        ]
        .drop_duplicates()
        .sort_values(
            ["season", "position_group"]
        )
    )

    print(
        thresholds.tail(12).to_string(
            index=False
        )
    )

    print("\nSample above-replacement values:")

    sample_columns = [
        "player_name",
        "season",
        "position",
        "games_played",
        "toi_per_game",
        "game_score_per_60",
        "game_score_per_60_above_replacement",
        "points_per_60",
        "points_per_60_above_replacement",
        "xg_per_60",
        "xg_per_60_above_replacement",
        "on_ice_expected_goals_pct",
        "on_ice_expected_goals_pct_above_replacement",
        "is_replacement_pool",
    ]

    sample = (
        df[
            df["eligible_for_training"]
        ][sample_columns]
        .sort_values(
            "game_score_per_60_above_replacement",
            ascending=False,
        )
        .head(15)
    )

    print(
        sample.to_string(index=False)
    )


if __name__ == "__main__":
    replacement_data = calculate_replacement_level()
    print_replacement_diagnostics(
        replacement_data
    )
