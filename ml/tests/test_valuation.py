from __future__ import annotations

import json

import joblib
import numpy as np
import pytest

from ml.evaluation.evaluate_skater_model import metrics
from ml.evaluation.gate import check_metric_regression, prediction_frame, stable_metadata_json, temporal_splits, validate_metadata
from ml.training.train_skater_value import CATEGORICAL_FEATURES, NUMERIC_FEATURES, build_model, build_training_data


def _patch_training_data(monkeypatch, player_seasons):
    from ml.training import train_skater_value as module
    from ml.features.replacement_level import calculate_replacement_level
    monkeypatch.setattr(module, "calculate_replacement_level", lambda: calculate_replacement_level(player_seasons))


def test_season_join_has_no_future_leakage(monkeypatch, player_seasons):
    _patch_training_data(monkeypatch, player_seasons)
    result = build_training_data()
    assert (result["target_season"] == result["season"] + 1).all()
    assert result["target_season"].max() <= player_seasons["season"].max()
    assert not (result["season"] >= result["target_season"]).any()


def test_missing_next_season_is_zero_target(monkeypatch, player_seasons):
    reduced = player_seasons[~((player_seasons["player_id"] == 4) & (player_seasons["season"] == 2022))]
    _patch_training_data(monkeypatch, reduced)
    result = build_training_data()
    row = result[(result["player_id"] == 4) & (result["season"] == 2021)].iloc[0]
    assert row["target_season"] == 2022
    assert row["next_season_hockey_value"] == 0.0


def test_training_rows_are_eligible_and_model_columns_exclude_contracts(monkeypatch, player_seasons):
    _patch_training_data(monkeypatch, player_seasons)
    result = build_training_data()
    assert result["eligible_for_training"].all()
    assert not {"cap_hit_cents", "aav", "contract_id"}.intersection(NUMERIC_FEATURES + CATEGORICAL_FEATURES)


def test_temporal_train_validation_test_splits(monkeypatch, player_seasons):
    _patch_training_data(monkeypatch, player_seasons)
    splits = temporal_splits(build_training_data())
    assert splits["train"]["target_season"].max() < splits["validation"]["target_season"].min()
    assert splits["validation"]["target_season"].max() < splits["test"]["target_season"].min()
    assert set(splits) == {"train", "validation", "test"}
    assert sum(len(part) for part in splits.values()) == len(build_training_data())


def test_training_is_deterministic_and_predictions_are_safe(monkeypatch, player_seasons):
    _patch_training_data(monkeypatch, player_seasons)
    data = build_training_data()
    split = temporal_splits(data)
    columns = NUMERIC_FEATURES + ["position_group"]
    first = build_model().fit(split["train"][columns], split["train"]["next_season_hockey_value"])
    second = build_model().fit(split["train"][columns], split["train"]["next_season_hockey_value"])
    first_predictions = first.predict(split["test"][columns])
    assert np.array_equal(first_predictions, second.predict(split["test"][columns]))
    frame = prediction_frame(split["test"], first_predictions)
    assert list(frame.columns) == ["player_id", "season", "prediction"]
    assert np.isfinite(frame["prediction"]).all()
    assert (frame["prediction"] >= 0).all()


def test_model_seed_is_explicit_and_serialization_round_trips(monkeypatch, player_seasons, tmp_path):
    _patch_training_data(monkeypatch, player_seasons)
    data = build_training_data()
    split = temporal_splits(data)
    columns = NUMERIC_FEATURES + CATEGORICAL_FEATURES
    model = build_model()
    model.fit(split["train"][columns], split["train"]["next_season_hockey_value"])

    assert model.named_steps["model"].random_state == 42
    before = model.predict(split["test"][columns])

    path = tmp_path / "model.joblib"
    joblib.dump(model, path)
    after = joblib.load(path).predict(split["test"][columns])

    assert np.array_equal(before, after)


def test_prediction_invariants_reject_bad_values(player_seasons):
    with pytest.raises(ValueError):
        prediction_frame(player_seasons.head(1).assign(target_season=2022), np.array([np.nan]))
    with pytest.raises(ValueError):
        prediction_frame(player_seasons.head(1).assign(target_season=2022), np.array([1.0, 2.0]))


def test_prediction_frame_clips_negative_values(player_seasons):
    frame = prediction_frame(player_seasons.head(2).assign(target_season=2022), np.array([-3.0, 2.0]))
    assert frame["prediction"].tolist() == [0.0, 2.0]


def test_metrics_and_regression_thresholds():
    values = metrics(np.array([1.0, 2.0, 3.0]), np.array([1.0, 2.0, 2.0]))
    assert values["mae"] == pytest.approx(1 / 3)
    assert values["rmse"] == pytest.approx((1 / 3) ** 0.5)
    assert values["r2"] == pytest.approx(0.5)
    check_metric_regression(values, {"mae": 1.0, "rmse": 1.0, "r2": -1.0})
    with pytest.raises(AssertionError):
        check_metric_regression({"mae": 2.0, "rmse": 1.0, "r2": 0.0}, {"mae": 1.0, "rmse": 1.0, "r2": 0.0}, {"mae": .1, "rmse": .1, "r2": .1})


def test_metric_regression_uses_worse_direction_for_r2():
    check_metric_regression(
        {"mae": 1.0, "rmse": 1.0, "r2": 0.5},
        {"mae": 1.0, "rmse": 1.0, "r2": 0.5},
        {"mae": 0.0, "rmse": 0.0, "r2": 0.0},
    )
    with pytest.raises(AssertionError, match="r2"):
        check_metric_regression(
            {"mae": 1.0, "rmse": 1.0, "r2": 0.49},
            {"mae": 1.0, "rmse": 1.0, "r2": 0.5},
            {"mae": 0.0, "rmse": 0.0, "r2": 0.01},
        )


def test_metadata_is_stable_and_valid():
    from pathlib import Path
    path = Path(__file__).parents[1] / "models" / "skater_value_model_metadata.json"
    metadata = json.loads(path.read_text(encoding="utf-8"))
    validate_metadata(metadata)
    assert stable_metadata_json(metadata) == stable_metadata_json(json.loads(stable_metadata_json(metadata)))


def test_metadata_validation_rejects_leakage_and_bad_split_order():
    valid = {"model_type": "model", "target": "value", "contract_features_used": False, "numeric_features": NUMERIC_FEATURES, "categorical_features": ["position_group"], "validation_target_season": 2024, "test_target_season": 2025, "metrics": {}}
    with pytest.raises(ValueError, match="Contract"):
        validate_metadata({**valid, "contract_features_used": True})
    with pytest.raises(ValueError, match="Validation"):
        validate_metadata({**valid, "validation_target_season": 2025, "test_target_season": 2024})


def test_metadata_validation_rejects_incomplete_or_nonfinite_metrics():
    path = __import__("pathlib").Path(__file__).parents[1] / "models" / "skater_value_model_metadata.json"
    valid = json.loads(path.read_text(encoding="utf-8"))

    incomplete = json.loads(json.dumps(valid))
    del incomplete["metrics"]["test"]["rmse"]
    with pytest.raises(ValueError, match="Incomplete metrics"):
        validate_metadata(incomplete)

    nonfinite = json.loads(json.dumps(valid))
    nonfinite["metrics"]["validation"]["r2"] = float("nan")
    with pytest.raises(ValueError, match="Non-finite"):
        validate_metadata(nonfinite)


def test_temporal_split_requires_three_seasons():
    import pandas as pd
    with pytest.raises(ValueError, match="three"):
        temporal_splits(pd.DataFrame({"target_season": [2024, 2025]}))
