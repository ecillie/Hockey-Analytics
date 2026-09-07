from __future__ import annotations

import numpy as np
import pandas as pd

from ml.pipelines.build_model_dataset import build_model_dataset


# Numeric features we currently expect to feed into the skater-value model.
# Salary-cap and contract information are intentionally excluded.
MODEL_FEATURE_COLUMNS = [
    "games_played",
    "toi_hours",
    "goals_per_60",
    "assists_per_60",
    "points_per_60",
    "xg_per_60",
    "shots_on_goal_per_60",
    "unblocked_attempts_per_60",
    "game_score_per_60",
    "primary_assists_per_60",
    "secondary_assists_per_60",
    "takeaways_per_60",
    "giveaways_per_60",
    "net_takeaways_per_60",
    "blocks_per_60",
    "penalties_per_60",
    "penalties_drawn_per_60",
    "penalty_differential_per_60",
    "goals_above_expected_per_60",
    "on_ice_expected_goals_pct",
    "offensive_zone_start_pct",
    "defensive_zone_start_pct",
    "neutral_zone_start_pct",
]


def _per_60(
    values: pd.Series,
    ice_time_seconds: pd.Series,
) -> pd.Series:
    """
    Convert a season total into a per-60-minute rate.

    Returns NaN when ice time is missing or zero.
    """
    valid_toi = ice_time_seconds.where(
        ice_time_seconds > 0
    )

    return (
        values.astype(float)
        * 3600.0
        / valid_toi
    )


def build_features(
    df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Build skater player-season features.

    If no DataFrame is supplied, the base model dataset is
    loaded directly from the ML data pipeline.

    Contract information is intentionally excluded.
    """

    if df is None:
        df = build_model_dataset()

    features = df.copy()

    # ---------------------------------------------------------
    # Ice-time / usage
    # ---------------------------------------------------------

    features["toi_minutes"] = (
        features["ice_time_seconds"] / 60.0
    )

    features["toi_hours"] = (
        features["ice_time_seconds"] / 3600.0
    )

    # ---------------------------------------------------------
    # Offensive production
    # ---------------------------------------------------------

    features["goals_per_60"] = _per_60(
        features["goals"],
        features["ice_time_seconds"],
    )

    features["assists_per_60"] = _per_60(
        features["assists"],
        features["ice_time_seconds"],
    )

    features["points_per_60"] = _per_60(
        features["points"],
        features["ice_time_seconds"],
    )

    features["xg_per_60"] = _per_60(
        features["individual_expected_goals"],
        features["ice_time_seconds"],
    )

    features["shots_on_goal_per_60"] = _per_60(
        features["individual_shots_on_goal"],
        features["ice_time_seconds"],
    )

    features["unblocked_attempts_per_60"] = _per_60(
        features["individual_unblocked_attempts"],
        features["ice_time_seconds"],
    )

    features["game_score_per_60"] = _per_60(
        features["game_score"],
        features["ice_time_seconds"],
    )

    features["primary_assists_per_60"] = _per_60(
        features["individual_primary_assists"],
        features["ice_time_seconds"],
    )

    features["secondary_assists_per_60"] = _per_60(
        features["individual_secondary_assists"],
        features["ice_time_seconds"],
    )

    # ---------------------------------------------------------
    # Defensive / possession events
    # ---------------------------------------------------------

    features["takeaways_per_60"] = _per_60(
        features["takeaways"],
        features["ice_time_seconds"],
    )

    features["giveaways_per_60"] = _per_60(
        features["giveaways"],
        features["ice_time_seconds"],
    )

    features["net_takeaways_per_60"] = (
        features["takeaways_per_60"]
        - features["giveaways_per_60"]
    )

    features["blocks_per_60"] = _per_60(
        features["shots_blocked"],
        features["ice_time_seconds"],
    )

    # ---------------------------------------------------------
    # Penalty impact
    # ---------------------------------------------------------

    features["penalties_per_60"] = _per_60(
        features["penalties"],
        features["ice_time_seconds"],
    )

    features["penalties_drawn_per_60"] = _per_60(
        features["penalties_drawn"],
        features["ice_time_seconds"],
    )

    features["penalty_differential_per_60"] = (
        features["penalties_drawn_per_60"]
        - features["penalties_per_60"]
    )

    # ---------------------------------------------------------
    # Finishing relative to expected goals
    # ---------------------------------------------------------

    features["goals_above_expected"] = (
        features["goals"]
        - features["individual_expected_goals"]
    )

    features["goals_above_expected_per_60"] = _per_60(
        features["goals_above_expected"],
        features["ice_time_seconds"],
    )

    # ---------------------------------------------------------
    # Zone-start deployment
    # ---------------------------------------------------------

    zone_start_total = (
        features["offensive_zone_shift_starts"].fillna(0)
        + features["defensive_zone_shift_starts"].fillna(0)
        + features["neutral_zone_shift_starts"].fillna(0)
    )

    valid_zone_starts = zone_start_total.where(
        zone_start_total > 0
    )

    features["offensive_zone_start_pct"] = (
        features["offensive_zone_shift_starts"]
        / valid_zone_starts
    )

    features["defensive_zone_start_pct"] = (
        features["defensive_zone_shift_starts"]
        / valid_zone_starts
    )

    features["neutral_zone_start_pct"] = (
        features["neutral_zone_shift_starts"]
        / valid_zone_starts
    )

    # ---------------------------------------------------------
    # Training eligibility
    # ---------------------------------------------------------

    # We still calculate features for everyone, but tiny samples
    # should not define the model during training.
    features["eligible_for_training"] = (
        features["games_played"].fillna(0) >= 20
    ) & (
        features["ice_time_seconds"].fillna(0) > 0
    )

    # Convert infinities created by unexpected source data to NaN.
    features.replace(
        [np.inf, -np.inf],
        np.nan,
        inplace=True,
    )

    return features.reset_index(drop=True)


def get_training_dataset(
    df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Return only player-seasons eligible for model training.
    """

    features = build_features(df)

    return features[
        features["eligible_for_training"]
    ].reset_index(drop=True)


def print_feature_diagnostics(
    df: pd.DataFrame,
) -> None:
    print("\n=== SKATER FEATURES ===")
    print(f"Rows: {len(df):,}")

    if df.empty:
        print("No feature rows found.")
        return

    eligible = int(
        df["eligible_for_training"].sum()
    )

    print(
        f"Training-eligible rows: "
        f"{eligible:,} / {len(df):,}"
    )

    print(
        f"Feature columns: "
        f"{len(MODEL_FEATURE_COLUMNS)}"
    )

    print("\nMissing values by model feature:")

    missing = (
        df[MODEL_FEATURE_COLUMNS]
        .isna()
        .sum()
        .sort_values(ascending=False)
    )

    print(missing.to_string())

    print("\nSample:")

    sample_columns = [
        "player_name",
        "season",
        "position",
        "games_played",
        "toi_hours",
        "goals_per_60",
        "assists_per_60",
        "points_per_60",
        "xg_per_60",
        "game_score_per_60",
        "on_ice_expected_goals_pct",
        "eligible_for_training",
    ]

    print(
        df[sample_columns]
        .head(15)
        .to_string(index=False)
    )


if __name__ == "__main__":
    feature_data = build_features()
    print_feature_diagnostics(feature_data)
