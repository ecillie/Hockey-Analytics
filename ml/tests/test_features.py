from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ml.features.build_features import MODEL_FEATURE_COLUMNS, build_features, get_training_dataset
from ml.features.replacement_level import calculate_replacement_level
from ml.pipelines.build_model_dataset import FORBIDDEN_CONTRACT_COLUMNS, build_model_dataset


def test_features_preserve_nulls_and_make_zero_toi_safe(player_seasons):
    result = build_features(player_seasons)
    assert pd.isna(result.loc[0, "goals_per_60"])
    assert pd.isna(result.loc[1, "points_per_60"])
    assert not np.isinf(result.select_dtypes("number").to_numpy()).any()


def test_features_handle_missing_zone_starts_and_unmapped_positions(player_seasons):
    player_seasons.loc[0, ["offensive_zone_shift_starts", "defensive_zone_shift_starts", "neutral_zone_shift_starts"]] = None
    player_seasons.loc[1, "position"] = "X"
    result = build_features(player_seasons)
    assert pd.isna(result.loc[0, "offensive_zone_start_pct"])
    assert pd.isna(result.loc[1, "position_group"])
    assert result.loc[0, "eligible_for_training"]


def test_feature_columns_are_finite_when_defined(player_seasons):
    result = build_features(player_seasons)
    for column in MODEL_FEATURE_COLUMNS:
        assert np.isfinite(result[column].dropna().to_numpy()).all(), column


def test_minimum_games_eligibility(player_seasons):
    player_seasons.loc[player_seasons.index[0], "games_played"] = 19
    result = get_training_dataset(player_seasons)
    assert result["games_played"].min() >= 20


def test_position_grouping_and_replacement_level(player_seasons):
    result = calculate_replacement_level(player_seasons)
    assert set(result["position_group"].dropna()) == {"forward", "defense"}
    assert result["replacement_toi_per_game_threshold"].notna().any()
    assert (result["game_score_per_60_above_replacement"].dropna() >= 0).any()


def test_replacement_baselines_are_position_and_season_specific(player_seasons):
    result = calculate_replacement_level(player_seasons)
    grouped = result.dropna(subset=["replacement_points_per_60"])
    assert grouped.groupby(["season", "position_group"])["replacement_points_per_60"].nunique().eq(1).all()
    assert grouped["replacement_points_per_60"].notna().all()


def test_model_dataset_rejects_duplicate_player_seasons(monkeypatch, player_seasons):
    from ml.pipelines import build_model_dataset as module
    caps = pd.DataFrame({"season": [2021], "season_label": ["2021-22"], "salary_cap_cents": [1000], "salary_cap_dollars": [10]})
    duplicate = pd.concat([player_seasons.head(1), player_seasons.head(1)], ignore_index=True)
    monkeypatch.setattr(module, "load_player_stats", lambda min_games=1: duplicate)
    monkeypatch.setattr(module, "load_salary_cap", lambda: caps)
    with pytest.raises(RuntimeError, match="duplicate"):
        build_model_dataset()


def test_model_dataset_joins_cap_by_season_without_contract_columns(monkeypatch, player_seasons):
    from ml.pipelines import build_model_dataset as module
    caps = pd.DataFrame({"season": range(2021, 2026), "season_label": [f"{x}-{x+1}" for x in range(2021, 2026)], "salary_cap_cents": [1000, 1100, 1200, 1300, 1400], "salary_cap_dollars": [10, 11, 12, 13, 14]})
    monkeypatch.setattr(module, "load_player_stats", lambda min_games=1: player_seasons.copy())
    monkeypatch.setattr(module, "load_salary_cap", lambda: caps)
    result = build_model_dataset()
    assert result.groupby("season")["salary_cap_dollars"].first().to_dict() == {2021: 10, 2022: 11, 2023: 12, 2024: 13, 2025: 14}
    assert result.groupby("season")["salary_cap_fraction"].first().to_dict() == {2021: 0.0000001, 2022: 0.00000011, 2023: 0.00000012, 2024: 0.00000013, 2025: 0.00000014}
    assert not FORBIDDEN_CONTRACT_COLUMNS.intersection(result.columns)


def test_model_dataset_rejects_contract_leakage(monkeypatch, player_seasons):
    from ml.pipelines import build_model_dataset as module
    caps = pd.DataFrame({"season": [2021], "season_label": ["2021-22"], "salary_cap_cents": [1000], "salary_cap_dollars": [10]})
    leaked = player_seasons.head(1).assign(cap_hit_cents=123)
    monkeypatch.setattr(module, "load_player_stats", lambda min_games=1: leaked)
    monkeypatch.setattr(module, "load_salary_cap", lambda: caps)
    with pytest.raises(RuntimeError, match="Contract data leaked"):
        build_model_dataset()


def test_missing_cap_history_remains_null_and_does_not_create_infinity(monkeypatch, player_seasons):
    from ml.pipelines import build_model_dataset as module
    caps = pd.DataFrame({"season": [2021], "season_label": ["2021-22"], "salary_cap_cents": [1000], "salary_cap_dollars": [10]})
    missing_cap_rows = pd.concat([player_seasons.head(1), player_seasons[player_seasons["season"] == 2022].head(1)])
    monkeypatch.setattr(module, "load_player_stats", lambda min_games=1: missing_cap_rows)
    monkeypatch.setattr(module, "load_salary_cap", lambda: caps)
    result = build_model_dataset()
    assert result.loc[result["season"] == 2022, "salary_cap_fraction"].isna().all()
    assert not np.isinf(result["salary_cap_fraction"].dropna()).any()
