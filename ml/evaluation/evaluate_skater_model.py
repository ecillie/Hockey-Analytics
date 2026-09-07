from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score,
)

from ml.training.train_skater_value import (
    CATEGORICAL_FEATURES,
    METADATA_PATH,
    MODEL_PATH,
    NUMERIC_FEATURES,
    build_training_data,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = REPO_ROOT / "ml" / "evaluation" / "outputs"
OUTPUT_PATH = OUTPUT_DIR / "skater_model_test_predictions.csv"


def metrics(
    actual: pd.Series,
    predicted: pd.Series,
) -> dict[str, float]:
    return {
        "mae": float(
            mean_absolute_error(actual, predicted)
        ),
        "rmse": float(
            np.sqrt(
                mean_squared_error(
                    actual,
                    predicted,
                )
            )
        ),
        "r2": float(
            r2_score(
                actual,
                predicted,
            )
        ),
    }


def print_metrics(
    label: str,
    values: dict[str, float],
) -> None:
    print(f"\n{label}")
    print("-" * len(label))
    print(f"MAE:  {values['mae']:.4f}")
    print(f"RMSE: {values['rmse']:.4f}")
    print(f"R²:   {values['r2']:.4f}")


def evaluate_model() -> pd.DataFrame:
    print("\n========================================")
    print(" SKATER VALUE MODEL EVALUATION")
    print("========================================")

    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            f"Model not found: {MODEL_PATH}"
        )

    if not METADATA_PATH.exists():
        raise FileNotFoundError(
            f"Metadata not found: {METADATA_PATH}"
        )

    with open(
        METADATA_PATH,
        "r",
        encoding="utf-8",
    ) as f:
        metadata = json.load(f)

    test_season = int(
        metadata["test_target_season"]
    )

    print(
        f"\nEvaluating target season: "
        f"{test_season}"
    )

    model = joblib.load(MODEL_PATH)

    df = build_training_data()

    test_df = df[
        df["target_season"] == test_season
    ].copy()

    if test_df.empty:
        raise RuntimeError(
            f"No rows found for test season "
            f"{test_season}."
        )

    feature_columns = (
        NUMERIC_FEATURES
        + CATEGORICAL_FEATURES
    )

    test_df["ml_prediction"] = model.predict(
        test_df[feature_columns]
    )

    # ---------------------------------------------------------
    # Naive benchmark
    #
    # Assume next season looks exactly like this season.
    # ---------------------------------------------------------

    test_df["naive_prediction"] = (
        test_df["current_hockey_value"]
    )

    actual = test_df[
        "next_season_hockey_value"
    ]

    ml_metrics = metrics(
        actual,
        test_df["ml_prediction"],
    )

    naive_metrics = metrics(
        actual,
        test_df["naive_prediction"],
    )

    print_metrics(
        "ML MODEL",
        ml_metrics,
    )

    print_metrics(
        "NAIVE CURRENT-VALUE BENCHMARK",
        naive_metrics,
    )

    # ---------------------------------------------------------
    # Improvement over naive benchmark
    # ---------------------------------------------------------

    mae_improvement = (
        naive_metrics["mae"]
        - ml_metrics["mae"]
    ) / naive_metrics["mae"]

    rmse_improvement = (
        naive_metrics["rmse"]
        - ml_metrics["rmse"]
    ) / naive_metrics["rmse"]

    print("\nBENCHMARK IMPROVEMENT")
    print("---------------------")

    print(
        f"MAE improvement:  "
        f"{mae_improvement:.2%}"
    )

    print(
        f"RMSE improvement: "
        f"{rmse_improvement:.2%}"
    )

    # ---------------------------------------------------------
    # Position breakdown
    # ---------------------------------------------------------

    print("\nPERFORMANCE BY POSITION GROUP")
    print("-----------------------------")

    for position_group, group in test_df.groupby(
        "position_group"
    ):
        group_metrics = metrics(
            group["next_season_hockey_value"],
            group["ml_prediction"],
        )

        print(
            f"\n{position_group.upper()} "
            f"({len(group):,} rows)"
        )

        print(
            f"MAE:  "
            f"{group_metrics['mae']:.4f}"
        )

        print(
            f"RMSE: "
            f"{group_metrics['rmse']:.4f}"
        )

        print(
            f"R²:   "
            f"{group_metrics['r2']:.4f}"
        )

    # ---------------------------------------------------------
    # Calibration
    #
    # Compare average prediction with actual outcome across
    # predicted-value quintiles.
    # ---------------------------------------------------------

    test_df["prediction_tier"] = pd.qcut(
        test_df["ml_prediction"],
        q=5,
        labels=[
            "Very Low",
            "Low",
            "Middle",
            "High",
            "Very High",
        ],
        duplicates="drop",
    )

    calibration = (
        test_df
        .groupby(
            "prediction_tier",
            observed=True,
        )
        .agg(
            players=("player_id", "count"),
            avg_prediction=(
                "ml_prediction",
                "mean",
            ),
            avg_actual=(
                "next_season_hockey_value",
                "mean",
            ),
        )
        .reset_index()
    )

    calibration["bias"] = (
        calibration["avg_prediction"]
        - calibration["avg_actual"]
    )

    print("\nCALIBRATION BY PREDICTED VALUE")
    print("------------------------------")

    print(
        calibration.to_string(
            index=False,
            float_format=lambda x: f"{x:.3f}",
        )
    )

    # ---------------------------------------------------------
    # Prediction errors
    # ---------------------------------------------------------

    test_df["prediction_error"] = (
        test_df["ml_prediction"]
        - test_df["next_season_hockey_value"]
    )

    test_df["absolute_error"] = (
        test_df["prediction_error"].abs()
    )

    display_columns = [
        "player_name",
        "position",
        "season",
        "target_season",
        "current_hockey_value",
        "next_season_hockey_value",
        "ml_prediction",
        "naive_prediction",
        "prediction_error",
        "absolute_error",
    ]

    print("\nBIGGEST MISSES")
    print("--------------")

    biggest_misses = (
        test_df
        .sort_values(
            "absolute_error",
            ascending=False,
        )
        [display_columns]
        .head(20)
    )

    print(
        biggest_misses.to_string(
            index=False,
            float_format=lambda x: f"{x:.3f}",
        )
    )

    # ---------------------------------------------------------
    # Biggest model successes vs naive benchmark
    # ---------------------------------------------------------

    test_df["ml_absolute_error"] = (
        test_df["ml_prediction"]
        - test_df["next_season_hockey_value"]
    ).abs()

    test_df["naive_absolute_error"] = (
        test_df["naive_prediction"]
        - test_df["next_season_hockey_value"]
    ).abs()

    test_df["improvement_vs_naive"] = (
        test_df["naive_absolute_error"]
        - test_df["ml_absolute_error"]
    )

    print("\nBIGGEST IMPROVEMENTS OVER NAIVE")
    print("-------------------------------")

    improvement_columns = [
        "player_name",
        "position",
        "season",
        "target_season",
        "next_season_hockey_value",
        "ml_prediction",
        "naive_prediction",
        "improvement_vs_naive",
    ]

    print(
        test_df
        .sort_values(
            "improvement_vs_naive",
            ascending=False,
        )
        [improvement_columns]
        .head(20)
        .to_string(
            index=False,
            float_format=lambda x: f"{x:.3f}",
        )
    )

    # ---------------------------------------------------------
    # Save test predictions
    # ---------------------------------------------------------

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    test_df.to_csv(
        OUTPUT_PATH,
        index=False,
    )

    print("\n========================================")
    print(" EVALUATION COMPLETE")
    print("========================================")

    print(
        f"\nPredictions saved to:\n"
        f"{OUTPUT_PATH}"
    )

    return test_df


if __name__ == "__main__":
    evaluate_model()
