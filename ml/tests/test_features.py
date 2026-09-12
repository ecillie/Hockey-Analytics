from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ml.features.build_features import (
    MODEL_FEATURE_COLUMNS,
    build_features,
    get_training_dataset,
)
from ml.features.replacement_level import calculate_replacement_level
from ml.pipelines.build_model_dataset import FORBIDDEN_CONTRACT_COLUMNS, build_model_dataset


def test_features_preserve_nulls_and_make_zero_toi_safe(player_seasons):
    result = build_features(player_seasons)
    assert pd.isna(result.loc[0, "goals_per_60"])
    assert pd.isna(result.loc[1, "points_per_60"])
    assert not np.isinf(result.select_dtypes("number").to_numpy()).any()


def test_per_60_features_use_seconds_and_preserve_expected_rates(player_seasons):
    row = player_seasons.iloc[[2]].copy()
    row["ice_time_seconds"] = 3600
    row["goals"] = 12
    row["assists"] = 18
    row["points"] = 30

    result = build_features(row).iloc[0]

    assert result["toi_minutes"] == pytest.approx(60.0)
    assert result["toi_hours"] == pytest.approx(1.0)
    assert result["goals_per_60"] == pytest.approx(12.0)
    assert result["assists_per_60"] == pytest.approx(18.0)
    assert result["points_per_60"] == pytest.approx(30.0)
    assert result["goals_above_expected"] == pytest.approx(
        12 - result["individual_expected_goals"]
    )


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


def test_zero_toi_is_not_training_eligible_even_with_enough_games(player_seasons):
    player_seasons.loc[1, "games_played"] = 82
    result = build_features(player_seasons)

    assert not result.loc[1, "eligible_for_training"]
    assert len(get_training_dataset(player_seasons)) == len(player_seasons) - 1


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


def test_replacement_calculation_does_not_use_contract_data(player_seasons):
    baseline = calculate_replacement_level(player_seasons)
    with_contracts = player_seasons.assign(
        cap_hit_cents=np.arange(len(player_seasons)) * 1000,
        contract_id=np.arange(len(player_seasons)),
    )

    result = calculate_replacement_level(with_contracts)

    comparable = [
        "replacement_toi_per_game_threshold",
        "replacement_points_per_60",
        "points_per_60_above_replacement",
    ]
    pd.testing.assert_frame_equal(
        baseline[comparable], result[comparable], check_dtype=False
    )


def test_replacement_levels_are_isolated_by_season(player_seasons):
    baseline = calculate_replacement_level(player_seasons)
    future_changed = player_seasons.copy()
    future_changed.loc[future_changed["season"] == 2025, "game_score"] = 10_000
    changed = calculate_replacement_level(future_changed)

    prior = baseline["season"] < 2025
    columns = [
        "replacement_points_per_60",
        "points_per_60_above_replacement",
        "replacement_toi_per_game_threshold",
    ]
    pd.testing.assert_frame_equal(
        baseline.loc[prior, columns].reset_index(drop=True),
        changed.loc[prior, columns].reset_index(drop=True),
        check_dtype=False,
    )


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
    assert result["salary_cap_fraction"].iloc[0] == pytest.approx(10 / 100_000_000)


def test_salary_cap_normalization_uses_fixed_scale_not_dataset_max(monkeypatch, player_seasons):
    from ml.pipelines import build_model_dataset as module

    caps = pd.DataFrame({
        "season": [2021, 2022],
        "season_label": ["2021-22", "2022-23"],
        "salary_cap_cents": [10_000, 20_000],
        "salary_cap_dollars": [100, 200],
    })
    rows = player_seasons[player_seasons["season"].isin([2021, 2022])]
    monkeypatch.setattr(module, "load_player_stats", lambda min_games=1: rows.copy())
    monkeypatch.setattr(module, "load_salary_cap", lambda: caps)

    result = build_model_dataset()

    expected = {2021: 100 / 100_000_000, 2022: 200 / 100_000_000}
    assert result.groupby("season")["salary_cap_fraction"].first().to_dict() == expected


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
