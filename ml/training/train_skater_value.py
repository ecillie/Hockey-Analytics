from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from ml.features.replacement_level import (
    calculate_replacement_level,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
MODEL_DIR = REPO_ROOT / "ml" / "models"

MODEL_PATH = MODEL_DIR / "skater_value_model.joblib"
METADATA_PATH = MODEL_DIR / "skater_value_model_metadata.json"


NUMERIC_FEATURES = [
    "games_played",
    "toi_hours",
    "toi_per_game",

    "goals_per_60",
    "primary_assists_per_60",
    "secondary_assists_per_60",
    "points_per_60",

    "xg_per_60",
    "shots_on_goal_per_60",
    "unblocked_attempts_per_60",

    "game_score_per_60",

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

    "goals_per_60_above_replacement",
    "primary_assists_per_60_above_replacement",
    "secondary_assists_per_60_above_replacement",
    "points_per_60_above_replacement",
    "xg_per_60_above_replacement",
    "game_score_per_60_above_replacement",
    "takeaways_per_60_above_replacement",
    "giveaways_per_60_above_replacement",
    "blocks_per_60_above_replacement",
    "penalties_per_60_above_replacement",
    "penalties_drawn_per_60_above_replacement",
    "penalty_differential_per_60_above_replacement",
    "goals_above_expected_per_60_above_replacement",
    "on_ice_expected_goals_pct_above_replacement",
]

CATEGORICAL_FEATURES = [
    "position_group",
]


def build_training_data() -> pd.DataFrame:
    """
    Create season-t -> season-(t+1) training observations.

    Current-season observations require an established sample.
    Next-season targets use all available NHL performance,
    even if the player played fewer than 20 games.

    No contract information is used.
    """

    all_rows = calculate_replacement_level()

    # Calculate hockey value for EVERY player-season.
    # Do not apply the 20-game filter to target seasons.
    all_rows["hockey_value"] = (
        all_rows["game_score_per_60_above_replacement"]
        * all_rows["toi_hours"]
    )

    # Build next-season targets from all available NHL rows.
    targets = all_rows[
        [
            "player_id",
            "season",
            "hockey_value",
        ]
    ].copy()

    targets = targets.rename(
        columns={
            "season": "target_season",
            "hockey_value": "next_season_hockey_value",
        }
    )

    # Only current-season feature rows need >=20 games.
    df = all_rows[
        all_rows["eligible_for_training"]
        & all_rows["position_group"].notna()
    ].copy()

    df["current_hockey_value"] = (
        df["game_score_per_60_above_replacement"]
        * df["toi_hours"]
    )

    df["target_season"] = df["season"] + 1

    df = df.merge(
        targets,
        how="left",
        on=[
            "player_id",
            "target_season",
        ],
        validate="one_to_one",
    )

    latest_season = int(
        all_rows["season"].max()
    )

    # Only keep observations where the target season exists
    # somewhere in our database.
    df = df[
        df["target_season"] <= latest_season
    ].copy()

    # If the player has no NHL player-season row next year,
    # next-season NHL contribution is zero.
    df["next_season_hockey_value"] = (
        df["next_season_hockey_value"]
        .fillna(0.0)
    )

    df.replace(
        [np.inf, -np.inf],
        np.nan,
        inplace=True,
    )

    return df.reset_index(drop=True)


def build_model() -> Pipeline:
    numeric_pipeline = Pipeline(
        steps=[
            (
                "imputer",
                SimpleImputer(strategy="median"),
            ),
        ]
    )

    categorical_pipeline = Pipeline(
        steps=[
            (
                "imputer",
                SimpleImputer(strategy="most_frequent"),
            ),
            (
                "one_hot",
                OneHotEncoder(
                    handle_unknown="ignore",
                    sparse_output=False,
                ),
            ),
        ]
    )

    preprocessor = ColumnTransformer(
        transformers=[
            (
                "numeric",
                numeric_pipeline,
                NUMERIC_FEATURES,
            ),
            (
                "categorical",
                categorical_pipeline,
                CATEGORICAL_FEATURES,
            ),
        ]
    )

    regressor = HistGradientBoostingRegressor(
        learning_rate=0.05,
        max_iter=300,
        max_leaf_nodes=31,
        l2_regularization=1.0,
        random_state=42,
    )

    return Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            ("model", regressor),
        ]
    )


def evaluate(
    name: str,
    model: Pipeline,
    df: pd.DataFrame,
) -> dict[str, float]:

    X = df[
        NUMERIC_FEATURES
        + CATEGORICAL_FEATURES
    ]

    y = df["next_season_hockey_value"]

    predictions = model.predict(X)

    mae = mean_absolute_error(
        y,
        predictions,
    )

    rmse = np.sqrt(
        mean_squared_error(
            y,
            predictions,
        )
    )

    r2 = r2_score(
        y,
        predictions,
    )

    print(f"\n{name}")
    print("-" * len(name))

    print(
        f"Rows: {len(df):,}"
    )

    print(
        f"MAE:  {mae:.4f}"
    )

    print(
        f"RMSE: {rmse:.4f}"
    )

    print(
        f"R²:   {r2:.4f}"
    )

    return {
        "rows": int(len(df)),
        "mae": float(mae),
        "rmse": float(rmse),
        "r2": float(r2),
    }


def train() -> Pipeline:
    print("\n========================================")
    print(" SKATER VALUE MODEL")
    print("========================================")

    print("\nBuilding training dataset...")

    df = build_training_data()

    print(
        f"Observations: {len(df):,}"
    )

    print(
        f"Players: {df['player_id'].nunique():,}"
    )

    print(
        f"Source seasons: "
        f"{df['season'].min()} - "
        f"{df['season'].max()}"
    )

    print(
        f"Target seasons: "
        f"{df['target_season'].min()} - "
        f"{df['target_season'].max()}"
    )

    # ---------------------------------------------------------
    # Chronological split
    # ---------------------------------------------------------

    unique_target_seasons = sorted(
        df["target_season"]
        .dropna()
        .unique()
    )

    if len(unique_target_seasons) < 3:
        raise RuntimeError(
            "Not enough seasons for chronological "
            "train/validation/test splits."
        )

    test_season = int(
        unique_target_seasons[-1]
    )

    validation_season = int(
        unique_target_seasons[-2]
    )

    train_df = df[
        df["target_season"]
        < validation_season
    ].copy()

    validation_df = df[
        df["target_season"]
        == validation_season
    ].copy()

    test_df = df[
        df["target_season"]
        == test_season
    ].copy()

    print("\nChronological split:")

    print(
        f"Train:      target seasons < "
        f"{validation_season}"
    )

    print(
        f"Validation: target season "
        f"{validation_season}"
    )

    print(
        f"Test:       target season "
        f"{test_season}"
    )

    # ---------------------------------------------------------
    # Fit initial model
    # ---------------------------------------------------------

    model = build_model()

    X_train = train_df[
        NUMERIC_FEATURES
        + CATEGORICAL_FEATURES
    ]

    y_train = train_df[
        "next_season_hockey_value"
    ]

    print("\nTraining model...")

    model.fit(
        X_train,
        y_train,
    )

    # ---------------------------------------------------------
    # Evaluation
    # ---------------------------------------------------------

    train_metrics = evaluate(
        "TRAIN",
        model,
        train_df,
    )

    validation_metrics = evaluate(
        "VALIDATION",
        model,
        validation_df,
    )

    test_metrics = evaluate(
        "TEST",
        model,
        test_df,
    )

    # ---------------------------------------------------------
    # Refit on everything except final test season
    # ---------------------------------------------------------

    final_training_df = df[
        df["target_season"]
        < test_season
    ].copy()

    final_model = build_model()

    final_model.fit(
        final_training_df[
            NUMERIC_FEATURES
            + CATEGORICAL_FEATURES
        ],
        final_training_df[
            "next_season_hockey_value"
        ],
    )

    # ---------------------------------------------------------
    # Save model
    # ---------------------------------------------------------

    MODEL_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    joblib.dump(
        final_model,
        MODEL_PATH,
    )

    metadata = {
        "model_type": "HistGradientBoostingRegressor",
        "target": "next_season_hockey_value",
        "target_definition": (
            "next-season game_score_per_60_above_replacement "
            "multiplied by next-season TOI hours"
        ),
        "contract_features_used": False,
        "numeric_features": NUMERIC_FEATURES,
        "categorical_features": CATEGORICAL_FEATURES,
        "validation_target_season": validation_season,
        "test_target_season": test_season,
        "metrics": {
            "train": train_metrics,
            "validation": validation_metrics,
            "test": test_metrics,
        },
    }

    with open(
        METADATA_PATH,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            metadata,
            f,
            indent=2,
            sort_keys=True,
        )

    print("\n========================================")
    print(" MODEL SAVED")
    print("========================================")

    print(
        f"\nModel:    {MODEL_PATH}"
    )

    print(
        f"Metadata: {METADATA_PATH}"
    )

    return final_model


if __name__ == "__main__":
    train()
