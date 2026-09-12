"""Small, data-independent correctness gate for the skater value model."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from ml.training.train_skater_value import CATEGORICAL_FEATURES, NUMERIC_FEATURES

PREDICTION_COLUMNS = ["player_id", "season", "prediction"]
METRIC_TOLERANCE = {"mae": 0.25, "rmse": 0.35, "r2": 0.05}
METRICS = ("mae", "rmse", "r2")
SPLITS = ("train", "validation", "test")


def temporal_splits(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Split observations by target season, never by a random row split."""
    if "target_season" not in df.columns:
        raise ValueError("target_season is required for temporal splits")
    seasons = sorted(df["target_season"].dropna().unique())
    if len(seasons) < 3:
        raise ValueError("At least three target seasons are required")
    validation_season, test_season = seasons[-2:]
    return {
        "train": df[df["target_season"] < validation_season].copy(),
        "validation": df[df["target_season"] == validation_season].copy(),
        "test": df[df["target_season"] == test_season].copy(),
    }


def prediction_frame(df: pd.DataFrame, predictions: np.ndarray) -> pd.DataFrame:
    """Return the public prediction shape with finite, nonnegative values."""
    values = np.asarray(predictions, dtype=float)
    if len(values) != len(df) or not np.isfinite(values).all():
        raise ValueError("Predictions must be finite and match the input rows")
    return pd.DataFrame({
        "player_id": df["player_id"].to_numpy(),
        "season": df["target_season"].to_numpy(),
        "prediction": np.maximum(values, 0.0),
    })[PREDICTION_COLUMNS]


def validate_metadata(metadata: dict) -> None:
    required = {"model_type", "target", "contract_features_used", "numeric_features", "categorical_features", "validation_target_season", "test_target_season", "metrics"}
    missing = required - metadata.keys()
    if missing:
        raise ValueError(f"Missing model metadata: {sorted(missing)}")
    if metadata["contract_features_used"] is not False:
        raise ValueError("Contract features must not be used by the model")
    if set(metadata["numeric_features"]) != set(NUMERIC_FEATURES):
        raise ValueError("Metadata numeric feature list is out of sync")
    if metadata["categorical_features"] != CATEGORICAL_FEATURES:
        raise ValueError("Metadata categorical feature list is out of sync")
    if not metadata["validation_target_season"] < metadata["test_target_season"]:
        raise ValueError("Validation must precede test")
    if set(metadata["metrics"]) != set(SPLITS):
        raise ValueError("Metadata must contain train, validation, and test metrics")
    for split in SPLITS:
        values = metadata["metrics"][split]
        if set(values) != {"rows", *METRICS}:
            raise ValueError(f"Incomplete metrics for {split} split")
        if not isinstance(values["rows"], int) or values["rows"] <= 0:
            raise ValueError(f"Invalid row count for {split} split")
        if not all(np.isfinite(float(values[metric])) for metric in METRICS):
            raise ValueError(f"Non-finite metrics for {split} split")


def check_metric_regression(current: dict[str, float], baseline: dict[str, float], tolerance: dict[str, float] | None = None) -> None:
    """Fail when current metrics move beyond the agreed absolute tolerance."""
    tolerance = tolerance or METRIC_TOLERANCE
    for metric in METRICS:
        if metric not in current or metric not in baseline:
            raise ValueError(f"Missing metric: {metric}")
        regression = current[metric] - baseline[metric] if metric != "r2" else baseline[metric] - current[metric]
        if regression > tolerance[metric]:
            raise AssertionError(f"{metric} regressed by {regression:.4f}; allowed {tolerance[metric]:.4f}")


def validate_committed_model_metadata(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        metadata = json.load(handle)
    validate_metadata(metadata)
    return metadata


def stable_metadata_json(metadata: dict) -> str:
    """Canonical JSON representation for reproducible metadata diffs."""
    validate_metadata(metadata)
    return json.dumps(metadata, indent=2, sort_keys=True) + "\n"


def main() -> None:
    path = Path(__file__).resolve().parents[1] / "models" / "skater_value_model_metadata.json"
    metadata = validate_committed_model_metadata(path)
    # These are the accepted ceilings/floor for the currently published model.
    limits = {
        "train": {"mae": 7.6307295257, "rmse": 10.3311876346, "r2": 0.6501067487},
        "validation": {"mae": 8.2497447023, "rmse": 11.3177165668, "r2": 0.6429673612},
        "test": {"mae": 9.3361370822, "rmse": 13.2279709137, "r2": 0.5664511622},
    }
    for split in SPLITS:
        check_metric_regression(
            metadata["metrics"][split],
            limits[split],
            {"mae": 0.0, "rmse": 0.0, "r2": 0.0},
        )
    print("ML correctness and metric gate passed")


if __name__ == "__main__":
    main()
