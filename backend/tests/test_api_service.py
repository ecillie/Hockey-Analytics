from __future__ import annotations

from collections import deque
from datetime import date

import pytest

from app.api.service import ApiProblem, TradeValueService, _identity, _summary, _team


class Result:
    def __init__(self, *, scalar=None, rows=()):
        self.scalar = scalar
        self.rows = list(rows)

    def scalar_one(self):
        return self.scalar

    def scalar_one_or_none(self):
        return self.scalar

    def mappings(self):
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def __iter__(self):
        return iter(self.rows)


class ScriptedSession:
    def __init__(self, *results: Result):
        self.results = deque(results)
        self.calls = []

    def execute(self, statement, params=None):
        self.calls.append((str(statement), params or {}))
        if not self.results:
            raise AssertionError(f"Unexpected SQL: {statement}")
        return self.results.popleft()


TEAM_ROW = {
    "team_id": 10,
    "nhl_team_id": 20,
    "abbreviation": "TST",
    "team_name": "Testers",
    "team_city": "Test City",
    "team_active": True,
}


def summary_row(**overrides):
    row = {
        "id": 7,
        "first_name": "Test",
        "last_name": "Skater",
        "full_name": "Test Skater",
        "birth_date": date(2000, 1, 1),
        "age": 26,
        "primary_position": "C",
        "shoots_catches": "L",
        "nationality": "CAN",
        "active": True,
        "roster_status": "ACTIVE",
        **TEAM_ROW,
        "season": 2025,
        "games_played": 82,
        "goals": 30,
        "assists": 50,
        "points": 80,
        "plus_minus": 10,
        "penalty_minutes": 20,
        "power_play_goals": 8,
        "power_play_points": 20,
        "short_handed_goals": 1,
        "shots": 200,
        "shooting_percentage": 0.15,
        "ice_time_seconds": 3600.4,
        "shifts": 100,
        "game_score": 2.0,
        "game_score_per_60": 2.0,
        "individual_expected_goals": 18.5,
        "expected_goals_per_60": 1.1,
        "on_ice_expected_goals_pct": 0.55,
        "takeaways": 12,
        "giveaways": 8,
        "shots_blocked": 6,
        "penalties": 5,
        "penalties_drawn": 9,
        "hockey_value": 1.5,
        "projected_hockey_value": 2.25,
        "gs60_above_replacement": 1.5,
        "model_version": "test-v1",
        "cap_hit_cents": 800_000_000,
    }
    row.update(overrides)
    return row


def test_mapping_helpers_preserve_nulls_and_round_time():
    row = summary_row(team_id=None, ice_time_seconds=10.6, goals=None)

    assert _team(row) is None
    assert _identity(row)["team"] is None
    assert _summary(row)["toiSeconds"] == 11
    assert _summary(row)["goals"] is None


def test_season_validation_and_unavailable_current_season():
    service = TradeValueService(ScriptedSession(Result(scalar=None)))
    with pytest.raises(ApiProblem) as unavailable:
        service.current_season()
    assert (unavailable.value.status, unavailable.value.code) == (
        503,
        "SEASONS_UNAVAILABLE",
    )

    service = TradeValueService(ScriptedSession(Result(scalar=False)))
    with pytest.raises(ApiProblem) as invalid:
        service.require_season(1900)
    assert invalid.value.code == "INVALID_SEASON"
    assert invalid.value.details == {"season": ["Unknown season."]}


def test_seasons_and_missing_identity_errors():
    session = ScriptedSession(
        Result(rows=[{"start_year": 2025, "end_year": 2026, "label": "2025-26", "salary_cap_cents": 9_550_000_000}]),
        Result(scalar=2025),
        Result(rows=[]),
        Result(rows=[]),
    )
    service = TradeValueService(session)

    assert service.seasons()["currentSeason"] == 2025
    with pytest.raises(ApiProblem, match="Player not found"):
        service.player_identity(999)
    with pytest.raises(ApiProblem, match="Team not found"):
        service.team_summary(999)


def test_players_builds_filters_sort_and_pagination(monkeypatch):
    service = TradeValueService(ScriptedSession(Result(scalar=True), Result(scalar=3)))
    captured = {}

    def rows(season, where, params, order, limit, offset):
        captured.update(season=season, where=where, params=params, order=order, limit=limit, offset=offset)
        return [summary_row()]

    monkeypatch.setattr(service, "_summary_rows", rows)
    result = service.players(2025, "tst", "C", "ACTIVE", " Test ", "points", "asc", 2, 2)

    assert result["pagination"] == {"page": 2, "pageSize": 2, "totalItems": 3, "totalPages": 2}
    assert result["data"][0]["fullName"] == "Test Skater"
    assert captured["params"] == {"team": "tst", "position": "C", "roster_status": "ACTIVE", "search": "%Test%"}
    assert captured["order"] == "points ASC NULLS LAST, id ASC"
    assert captured["offset"] == 2


def test_skater_and_goalie_stats_branches(monkeypatch):
    service = TradeValueService(ScriptedSession())
    monkeypatch.setattr(service, "require_season", lambda _season: None)
    monkeypatch.setattr(service, "player_identity", lambda _player_id: {})
    monkeypatch.setattr(service, "summary_for_player", lambda *_args: summary_row())

    skater = service.player_stats(7, 2025)
    assert skater["traditional"]["shootingPercentage"] == 0.15
    assert skater["advanced"]["iceTimeSeconds"] == 3600
    assert skater["goalie"] is None

    goalie_row = summary_row(primary_position="G", games_played=22, ice_time_seconds=None)
    monkeypatch.setattr(service, "summary_for_player", lambda *_args: goalie_row)
    monkeypatch.setattr(service, "_goalie_stats", lambda *_args: {"gamesPlayed": 22})
    goalie = service.player_stats(8, 2025)
    assert goalie["traditional"] is None
    assert goalie["advanced"] is None
    assert goalie["goalie"] == {"gamesPlayed": 22}

    monkeypatch.setattr(service, "summary_for_player", lambda *_args: None)
    with pytest.raises(ApiProblem, match="Player not found"):
        service.player_stats(7, 2025)


def test_skater_stats_preserve_missing_traditional_and_advanced_data(monkeypatch):
    service = TradeValueService(ScriptedSession())
    monkeypatch.setattr(service, "require_season", lambda _season: None)
    monkeypatch.setattr(service, "player_identity", lambda _player_id: {})
    monkeypatch.setattr(
        service,
        "summary_for_player",
        lambda *_args: summary_row(games_played=None, ice_time_seconds=None),
    )

    result = service.player_stats(7, 2025)

    assert result["traditional"] is None
    assert result["advanced"] is None
    assert result["goalie"] is None


def test_goalie_stats_handles_missing_and_calculated_rows():
    service = TradeValueService(
        ScriptedSession(
            Result(rows=[{"games_played": None}]),
            Result(rows=[{
                "games_played": 20, "wins": 12, "losses": 6, "overtime_losses": 2,
                "shots_against": 600, "saves": 550, "save_percentage": 550 / 600,
                "goals_against": 50, "time_on_ice_seconds": 72_000, "gaa": 2.5,
                "shutouts": 2, "xga": 55.0, "ga": 50.0, "gsae": 5.0,
            }]),
        )
    )
    assert service._goalie_stats(8, 2025) is None
    assert service._goalie_stats(8, 2025)["goalsSavedAboveExpected"] == 5.0


def test_value_history_leaders_and_overview(monkeypatch):
    service = TradeValueService(ScriptedSession())
    monkeypatch.setattr(service, "require_season", lambda _season: None)
    monkeypatch.setattr(service, "player_identity", lambda _player_id: {})
    monkeypatch.setattr(service, "summary_for_player", lambda *_args: summary_row())
    monkeypatch.setattr(service, "current_season", lambda: 2025)

    value = service.hockey_value(7, None)
    assert value == {
        "playerId": 7, "season": 2025, "hockeyValue": 1.5,
        "projectedNextSeasonHockeyValue": 2.25,
        "gameScorePer60AboveReplacement": 1.5, "toiHours": pytest.approx(1.000111),
        "modelVersion": "test-v1",
    }

    monkeypatch.setattr(service, "_all", lambda *_args, **_kwargs: [{"season": 2025}])
    history = service.player_seasons(7)
    assert history[0]["season"] == 2025
    assert service.value_history(7) == [{"season": 2025, "hockeyValue": 1.5}]

    monkeypatch.setattr(service, "_summary_rows", lambda *_args, **_kwargs: [summary_row()])
    assert service.leaders(2025, "C", "TST", 5)[0]["id"] == 7

    rows = [summary_row(), summary_row(id=8, full_name="Goalie", primary_position="G", goals=None, points=None, hockey_value=None)]
    monkeypatch.setattr(service, "_summary_rows", lambda *_args, **_kwargs: rows)
    overview = service.overview(2025)
    assert overview["league"] == {"players": 2, "goals": 30, "gamesPlayed": 164, "averageHockeyValue": 1.5}
    assert overview["leaders"]["points"][0]["id"] == 7


def test_history_skips_missing_summary_and_leaders_allow_no_filters(monkeypatch):
    service = TradeValueService(ScriptedSession())
    monkeypatch.setattr(service, "player_identity", lambda _player_id: {})
    monkeypatch.setattr(service, "_all", lambda *_args, **_kwargs: [{"season": 2025}])
    monkeypatch.setattr(service, "summary_for_player", lambda *_args: None)

    assert service.player_seasons(7) == []

    monkeypatch.setattr(service, "require_season", lambda _season: None)
    monkeypatch.setattr(service, "_summary_rows", lambda *_args, **_kwargs: [summary_row()])
    assert service.leaders(2025, None, None, 5)[0]["id"] == 7


def test_contract_team_contracts_and_cap(monkeypatch):
    contract_row = {
        "id": 30, "player_id": 7, "signing_team_id": 10, "signing_nhl_team_id": 20,
        "signing_abbreviation": "TST", "signing_team_name": "Testers",
        "signing_team_city": "Test City", "signing_team_active": True,
        "signed_on": date(2025, 7, 1), "start_season": 2025, "end_season": 2026,
        "term_years": 2, "contract_type": "STANDARD", "expiry_status": "UFA",
        "total_value_cents": 1_600_000_000, "average_value_cents": 800_000_000,
        "is_entry_level": False,
    }
    contract_season = {
        **TEAM_ROW, "season_start_year": 2025, "base_salary_cents": 700_000_000,
        "signing_bonus_cents": 100_000_000, "performance_bonus_cents": None,
        "total_cash_cents": 800_000_000, "cap_hit_cents": 800_000_000,
        "cap_percentage": "0.08376963", "is_slide": False,
    }
    service = TradeValueService(ScriptedSession(Result(rows=[contract_row]), Result(rows=[contract_season])))
    monkeypatch.setattr(service, "player_identity", lambda player_id: {"id": player_id})
    monkeypatch.setattr(service, "current_season", lambda: 2025)
    contract = service.contract(7)
    assert contract["signingTeam"]["id"] == 10
    assert contract["seasons"][0]["capPercentage"] == pytest.approx(0.08376963)

    team = {"id": 10}
    monkeypatch.setattr(service, "require_season", lambda _season: None)
    monkeypatch.setattr(service, "team_summary", lambda _team_id: team)
    monkeypatch.setattr(service, "_all", lambda *_args, **_kwargs: [{"player_id": 7}])
    monkeypatch.setattr(service, "contract", lambda *_args: contract)
    result = service.team_contracts(10, 2025)
    assert result["contracts"][0]["season"]["capHitCents"] == 800_000_000

    monkeypatch.setattr(service, "_one", lambda *_args, **_kwargs: {
        "salary_cap_cents": 9_550_000_000, "active_cap": 800_000_000,
        "ltir_cap": 200_000_000, "minors_cap": 100_000_000, "total_cap": 1_100_000_000,
    })
    cap = service.team_cap(10, 2025)
    assert cap["capSpaceCents"] == 8_750_000_000
    assert cap["calculationStatus"] == "ESTIMATE"


def test_contract_without_signing_team_and_unmatched_team_contracts(monkeypatch):
    unsigned_contract_row = {
        "id": 31,
        "player_id": 7,
        "signing_team_id": None,
        "signed_on": None,
        "start_season": 2025,
        "end_season": 2025,
        "term_years": 1,
        "contract_type": None,
        "expiry_status": None,
        "total_value_cents": None,
        "average_value_cents": None,
        "is_entry_level": False,
    }
    service = TradeValueService(
        ScriptedSession(Result(rows=[unsigned_contract_row]), Result(rows=[]))
    )
    monkeypatch.setattr(service, "player_identity", lambda player_id: {"id": player_id})

    contract = service.contract(7, 2025)
    assert contract["signingTeam"] is None
    assert contract["seasons"] == []

    monkeypatch.setattr(service, "require_season", lambda _season: None)
    monkeypatch.setattr(service, "team_summary", lambda team_id: {"id": team_id})
    monkeypatch.setattr(
        service,
        "_all",
        lambda *_args, **_kwargs: [{"player_id": 7}, {"player_id": 8}],
    )
    contracts = {
        7: None,
        8: {"seasons": [{"season": 2024, "owningTeam": {"id": 10}}]},
    }
    monkeypatch.setattr(
        service,
        "contract",
        lambda player_id, _season: contracts[player_id],
    )

    assert service.team_contracts(10, 2025)["contracts"] == []


def test_team_roster_search_and_compare(monkeypatch):
    service = TradeValueService(ScriptedSession())
    monkeypatch.setattr(service, "require_season", lambda _season: None)
    monkeypatch.setattr(service, "team_summary", lambda team_id: {"id": team_id})
    monkeypatch.setattr(service, "_summary_rows", lambda *_args, **_kwargs: [summary_row()])
    roster = service.roster(10, 2025, "ACTIVE")
    assert roster["status"] == "ACTIVE"
    assert roster["players"][0]["id"] == 7

    monkeypatch.setattr(service, "_all", lambda sql, _params=None: (
        [{"id": 7}] if "FROM players" in sql else [{
            "id": 10, "nhl_team_id": 20, "abbreviation": "TST",
            "team_name": "Testers", "team_city": "Test City", "team_active": True,
        }]
    ))
    monkeypatch.setattr(service, "player_identity", lambda player_id: {"id": player_id})
    found = service.search("test", ["player", "team"], 8)
    assert found["players"] == [{"id": 7}]
    assert found["teams"][0]["abbreviation"] == "TST"

    monkeypatch.setattr(service, "player_stats", lambda player_id, season: {"playerId": player_id, "season": season})
    monkeypatch.setattr(service, "hockey_value", lambda player_id, season: {"playerId": player_id, "season": season})
    monkeypatch.setattr(service, "contract", lambda *_args: None)
    compared = service.compare([7, 8], 2025)
    assert [row["player"]["id"] for row in compared["players"]] == [7, 8]


def test_search_can_request_each_entity_type_independently(monkeypatch):
    service = TradeValueService(ScriptedSession())
    team_row = {
        "id": 10,
        "nhl_team_id": 20,
        "abbreviation": "TST",
        "team_name": "Testers",
        "team_city": "Test City",
        "team_active": True,
    }
    monkeypatch.setattr(service, "_all", lambda *_args, **_kwargs: [team_row])

    teams_only = service.search("test", ["team"], 8)
    assert teams_only["players"] == []
    assert teams_only["teams"][0]["id"] == 10

    monkeypatch.setattr(service, "_all", lambda *_args, **_kwargs: [{"id": 7}])
    monkeypatch.setattr(service, "player_identity", lambda player_id: {"id": player_id})
    players_only = service.search("test", ["player"], 8)
    assert players_only == {"players": [{"id": 7}], "teams": []}
