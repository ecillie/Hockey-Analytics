from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import date
import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import requests

from app.ScriptingFiles.FullDataScript import ingestion, team_stints


FIXTURES = Path(__file__).parent / "fixtures" / "ingestion"
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


class CsvResponse:
    def __init__(self, text: str):
        self.text = text

    def raise_for_status(self):
        return None


class JsonResponse(CsvResponse):
    def __init__(self, payload):
        self.payload = payload
        self.text = json.dumps(payload)

    def json(self):
        return self.payload


class MoneyPuckSession:
    def __init__(self, skater_games: int = 12, season: int = 2025):
        self.skater_games = skater_games
        self.season = season

    def get(self, url, timeout):
        if "skaters.csv" in url:
            header = (
                "playerId,season,name,team,position,situation,games_played,"
                "icetime,shifts,gameScore,I_F_points,I_F_goals\n"
            )
            old = f"1001,{self.season},Fixture Skater,AAA,C,all,11,1300,160,4.5,9,4\n"
            new = (
                f"1001,{self.season},Fixture Skater,AAA,C,all,"
                f"{self.skater_games},1400,170,5.5,10,5\n"
            )
            return CsvResponse(header + old + new)
        return CsvResponse(
            "playerId,season,name,team,position,situation,games_played,"
            "icetime,xGoals,goals,ongoal\n"
            f"2001,{self.season},Fixture Goalie,BBB,G,all,9,1000,15.5,14,240\n"
        )


class CapWagesSession:
    def __init__(self, cap_hit: str = "$1,000,000", *, fail_profile: bool = False):
        self.cap_hit = cap_hit
        self.fail_profile = fail_profile

    def get(self, url, timeout):
        if url.endswith("/players/active"):
            row = ["Contract Fixture", "contract-fixture", "AAA", "C"] + [None] * 27
            row[7] = "USA"
            row[30] = "98-2-3"
            payload = {"props": {"pageProps": {"playersArray": [row]}}}
        else:
            if self.fail_profile:
                raise requests.ConnectionError("fixture profile failed")
            payload = {"props": {"pageProps": {"player": {"contracts": [{
                "signingTeam": "AAA",
                "value": "$2,000,000",
                "expiryStatus": "UFA",
                "type": "STANDARD",
                "details": [{"season": "2025-26", "capHit": self.cap_hit}],
            }]}}}}
        return CsvResponse(
            '<script id="__NEXT_DATA__" type="application/json">'
            + json.dumps(payload)
            + "</script>"
        )


class ScheduleSession:
    def __init__(self, game_ids=(2025020001, 2025020002)):
        self.game_ids = game_ids

    def get(self, url, timeout):
        games = [
            {
                "id": game_id,
                "gameType": 2,
                "awayTeam": {"abbrev": "AAA", "score": 2},
                "homeTeam": {"abbrev": "BBB", "score": 3},
                "venue": {"default": "Fixture Arena"},
                "gameState": "FINAL",
                "startTimeUTC": "2025-10-01T23:00:00Z",
            }
            for game_id in self.game_ids
        ]
        return JsonResponse({
            "gameWeek": [{"date": "2025-10-01", "games": games}],
            "nextStartDate": None,
        })


class NhlRosterSession:
    def get(self, url, timeout):
        if url.endswith("/standings/now"):
            return JsonResponse({"standings": [{
                "teamAbbrev": {"default": "AAA"},
                "teamName": {"default": "Alphas"},
                "placeName": {"default": "Alpha City"},
            }]})
        return JsonResponse({
            "forwards": [{
                "id": 3001,
                "firstName": {"default": "Roster"},
                "lastName": {"default": "Fixture"},
                "birthDate": "2000-01-01",
                "positionCode": "C",
                "shootsCatches": "L",
                "birthCountry": "CAN",
            }],
            "defensemen": [],
            "goalies": [],
        })


def test_season_and_ordered_team_helpers():
    assert ingestion._season_start_year(date(2026, 6, 30)) == 2025
    assert ingestion._season_start_year(date(2026, 7, 1)) == 2026
    assert ingestion._ordered_team_abbreviations("COL,CAR,DAL") == (
        "COL", "CAR", "DAL"
    )
    assert ingestion._ordered_team_abbreviations(" TOT, bad value,NYR ") == ("NYR",)


def nhl_stat_rows(kind, season, game_type, *, goals=5):
    if kind == "skater":
        row = {
            "playerId": 1001,
            "skaterFullName": "Fixture Skater",
            "teamAbbrevs": "AAA,BBB",
            "positionCode": "C",
            "gamesPlayed": 10,
            "goals": goals,
            "assists": 7,
            "points": goals + 7,
            "shots": 40,
        }
    else:
        row = {
            "playerId": 2001,
            "goalieFullName": "Fixture Goalie",
            "teamAbbrevs": "BBB",
            "gamesPlayed": 8,
            "wins": 5,
            "losses": 2,
            "otLosses": 1,
            "shotsAgainst": 220,
            "saves": 207,
            "goalsAgainst": 13,
        }
    return [row, dict(row)]


def test_csv_parser_rejects_duplicate_columns_and_extra_values():
    with pytest.raises(ingestion.IngestionValidationError, match="duplicate CSV columns"):
        ingestion._parse_csv("playerId,playerId\n1,2\n", source="fixture")

    with pytest.raises(ingestion.IngestionValidationError, match="too many values"):
        ingestion._parse_csv("playerId,season\n1,2025,extra\n", source="fixture")


@pytest.mark.parametrize("season", [None, "", "  ", "twenty", "2025.5", "0", "Infinity"])
def test_required_fields_and_season_type_validation(season):
    row = {"playerId": "1", "season": season, "name": "A Player"}
    with pytest.raises(ingestion.IngestionValidationError):
        ingestion.validate_and_deduplicate_rows(
            [row],
            source="fixture",
            required_fields=("playerId", "season", "name"),
            grain_fields=("playerId", "season"),
        )


def test_validation_rejects_empty_inputs_and_schema_drift():
    with pytest.raises(ingestion.IngestionValidationError, match="no rows"):
        ingestion.validate_and_deduplicate_rows(
            [], source="fixture", required_fields=("playerId",), grain_fields=("playerId",)
        )

    with pytest.raises(ingestion.IngestionValidationError, match="games_played must be"):
        ingestion.validate_and_deduplicate_rows(
            [{
                "playerId": "1",
                "season": "2025",
                "name": "A Player",
                "games_played": "10.5",
            }],
            source="fixture",
            required_fields=("playerId", "season", "name", "games_played"),
            grain_fields=("playerId", "season"),
            integer_fields=("playerId", "season", "games_played"),
        )
    with pytest.raises(ingestion.IngestionValidationError, match="missing required columns: name"):
        ingestion.validate_and_deduplicate_rows(
            [{"playerId": "1", "season": "2025"}],
            source="fixture",
            required_fields=("playerId", "season", "name"),
            grain_fields=("playerId", "season"),
        )


def test_validation_deduplicates_at_player_season_stat_grain_and_checks_coverage():
    rows = [
        {"playerId": "1", "season": "2024", "team": "AAA", "situation": "all", "value": "old"},
        {"playerId": "1", "season": "2024", "team": "aaa", "situation": "ALL", "value": "new"},
        {"playerId": "1", "season": "2025", "team": "AAA", "situation": "all", "value": "next"},
    ]
    valid, report = ingestion.validate_and_deduplicate_rows(
        rows,
        source="fixture",
        required_fields=("playerId", "season", "situation"),
        grain_fields=("playerId", "season", "team", "situation"),
        expected_seasons=(2024, 2025),
    )
    assert [row["value"] for row in valid] == ["new", "next"]
    assert report.records_read == 3
    assert report.records_valid == 2
    assert report.duplicate_records == 1
    assert report.seasons == (2024, 2025)

    with pytest.raises(ingestion.IngestionValidationError, match="duplicate ratio"):
        ingestion.enforce_quality_thresholds(
            report, minimum_rows=2, maximum_duplicate_ratio=0.10
        )
    with pytest.raises(ingestion.IngestionValidationError, match="minimum is 3"):
        ingestion.enforce_quality_thresholds(
            report, minimum_rows=3, maximum_duplicate_ratio=1.0
        )

    with pytest.raises(ingestion.IngestionValidationError, match="missing seasons: 2023"):
        ingestion.validate_and_deduplicate_rows(
            rows,
            source="fixture",
            required_fields=("playerId", "season", "situation"),
            grain_fields=("playerId", "season", "team", "situation"),
            expected_seasons=(2023, 2024, 2025),
        )


def test_value_coercion_contract_money_and_capwages_player_parsing():
    assert ingestion._number("12.75") == 12.75
    assert ingestion._number("12", integer=True) == 12
    assert ingestion._number("NaN") is None
    assert ingestion._number("bad") is None
    assert ingestion._money_cents("$1,234.56") == 123456
    assert ingestion._money_cents("bad") is None
    assert ingestion._capwages_birth_date("97-1-13") == "1997-01-13"
    assert ingestion._capwages_birth_date("97-99-13") is None

    capwages_row = ["Fixture Player", None, "AAA", "L"] + [None] * 27
    capwages_row[7] = "CAN"
    capwages_row[30] = "97-1-13"
    assert ingestion._parse_capwages_players([capwages_row], minimum_rows=1) == [{
        "name": "Fixture Player",
        "slug": "fixture-player",
        "team": "AAA",
        "position": "L",
        "nationality": "CAN",
        "birth_date": "1997-01-13",
    }]
    with pytest.raises(ingestion.IngestionValidationError, match="minimum is 2"):
        ingestion._parse_capwages_players([capwages_row], minimum_rows=2)


def test_cross_field_stat_invariants_reject_inconsistent_rows():
    with pytest.raises(ingestion.IngestionValidationError, match="points must equal"):
        ingestion.validate_stat_invariants(
            "skater",
            {"playerId": 1, "goals": 2, "assists": 3, "points": 99},
            source="fixture",
        )
    with pytest.raises(ingestion.IngestionValidationError, match="shotsAgainst"):
        ingestion.validate_stat_invariants(
            "goalie",
            {"playerId": 2, "shotsAgainst": 20, "saves": 18, "goalsAgainst": 3},
            source="fixture",
        )


def test_nhl_api_parser_rejects_schema_drift():
    session = Mock()
    session.get.return_value = JsonResponse({"data": {"not": "a list"}})
    with pytest.raises(ingestion.IngestionValidationError, match="data must be a list"):
        ingestion._nhl_stats_pages(session, "skater", 2025, 2)

    session.get.return_value = JsonResponse({"data": [{"goals": 1}]})
    with pytest.raises(ingestion.IngestionValidationError, match="missing playerId"):
        ingestion._nhl_stats_pages(session, "skater", 2025, 2)


def test_run_all_uses_last_good_contract_snapshot_but_not_for_other_failures():
    expected = {"players": 600, "contracts": 500, "contract_seasons": 900, "cached": 1}
    historical = {"total_player_seasons": 100, "covered_player_seasons": 100, "missing_player_seasons": 0, "cached": 1}
    from app.ScriptingFiles.FullDataScript import capspace
    with (
        patch.object(ingestion, "init_db"),
        patch.object(ingestion, "http_session", return_value=Mock()),
        patch.object(ingestion, "ingest_moneypuck", return_value={}),
        patch.object(ingestion, "ingest_nhl_rosters", return_value={}),
        patch.object(ingestion, "ingest_nhl_stats", return_value={}),
        patch.object(ingestion, "ingest_capwages", side_effect=RuntimeError("partial feed")),
        patch.object(ingestion, "existing_capwages_summary", return_value=expected),
        patch.object(capspace, "ingest_historical_contracts", return_value=historical),
        patch.object(ingestion, "ingest_schedule", return_value={"games": 10}),
    ):
        result = ingestion.run_all()
    assert result["capwages"] == expected
    assert result["historical_contracts"] == historical
    assert result["schedule"] == {"games": 10}

    with (
        patch.object(ingestion, "init_db"),
        patch.object(ingestion, "http_session", return_value=Mock()),
        patch.object(ingestion, "ingest_moneypuck", return_value={}),
        patch.object(ingestion, "ingest_nhl_rosters", return_value={}),
        patch.object(ingestion, "ingest_nhl_stats", return_value={}),
        patch.object(ingestion, "ingest_capwages", return_value={}),
        patch.object(capspace, "ingest_historical_contracts", side_effect=RuntimeError("CapSpace down")),
        patch.object(capspace, "existing_historical_contract_summary", return_value=historical),
        patch.object(ingestion, "ingest_schedule", return_value={}),
    ):
        retained = ingestion.run_all()
    assert retained["historical_contracts"] == historical

    with (
        patch.object(ingestion, "init_db"),
        patch.object(ingestion, "http_session", return_value=Mock()),
        patch.object(ingestion, "ingest_moneypuck", side_effect=RuntimeError("bad stats")),
        patch.object(ingestion, "ingest_nhl_rosters") as rosters,
    ):
        with pytest.raises(RuntimeError, match="bad stats"):
            ingestion.run_all()
    rosters.assert_not_called()


def test_roster_command_exit_codes():
    from app.ScriptingFiles.FullDataScript import populate_roster_status

    success = {
        "statuses_updated": 1,
        "active_count": 1,
        "minors_count": 0,
        "ltir_count": 0,
        "unknown_count": 0,
        "preserved_count": 0,
    }
    with (
        patch.object(populate_roster_status, "init_db"),
        patch.object(populate_roster_status, "sync_roster_status", return_value=success),
    ):
        assert populate_roster_status.main() == 0
    with (
        patch.object(populate_roster_status, "init_db"),
        patch.object(
            populate_roster_status,
            "sync_roster_status",
            side_effect=populate_roster_status.IncompleteRosterFeedError("partial"),
        ),
    ):
        assert populate_roster_status.main() == 2
    with (
        patch.object(populate_roster_status, "init_db"),
        patch.object(
            populate_roster_status,
            "sync_roster_status",
            side_effect=RuntimeError("database unavailable"),
        ),
    ):
        assert populate_roster_status.main() == 1


@pytest.fixture()
def migrated_database(monkeypatch):
    if not TEST_DATABASE_URL or "tradevalue_test" not in TEST_DATABASE_URL:
        pytest.skip("a disposable tradevalue_test database is required")
    from sqlalchemy import create_engine, text

    engine = create_engine(TEST_DATABASE_URL)
    with engine.begin() as connection:
        if connection.execute(text("SELECT to_regclass('public.players')")).scalar_one() is None:
            pytest.skip("the test database has not been migrated")
        connection.execute(text(
            "TRUNCATE teams, players, ingestion_runs RESTART IDENTITY CASCADE"
        ))

    @contextmanager
    def test_transaction():
        import psycopg2

        connection = psycopg2.connect(TEST_DATABASE_URL)
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    monkeypatch.setattr(ingestion, "database_transaction", test_transaction)
    monkeypatch.setitem(ingestion.MONEYPUCK_FILES, "skater", FIXTURES / "moneypuck_skaters.csv")
    monkeypatch.setitem(ingestion.MONEYPUCK_FILES, "goalie", FIXTURES / "moneypuck_goalies.csv")
    yield engine
    engine.dispose()


def test_moneypuck_ingestion_is_idempotent_deduplicated_and_updates_typed_values(migrated_database):
    from sqlalchemy import text

    options = {
        "expected_seasons": (2024, 2025),
        "minimum_rows_per_kind": 2,
        "maximum_duplicate_ratio": 0.5,
    }
    first = ingestion.ingest_moneypuck(MoneyPuckSession(skater_games=12), **options)
    second = ingestion.ingest_moneypuck(MoneyPuckSession(skater_games=15), **options)
    expected_common = {
        "players": 2,
        "skater": 2,
        "goalie": 2,
        "records_read": 5,
        "records_skipped": 1,
        "reconciliation_policy": "retain_missing",
    }
    assert {key: first[key] for key in expected_common} == expected_common
    assert {key: second[key] for key in expected_common} == expected_common
    assert (first["records_created"], first["records_updated"]) == (4, 0)
    assert (second["records_created"], second["records_updated"]) == (0, 4)

    with migrated_database.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM players")).scalar_one() == 2
        assert connection.execute(text("SELECT count(*) FROM skater_advanced_season_stats")).scalar_one() == 2
        assert connection.execute(text("SELECT count(*) FROM goalie_advanced_season_stats")).scalar_one() == 2
        games = connection.execute(text(
            "SELECT games_played FROM skater_advanced_season_stats WHERE season_start_year=2025"
        )).scalar_one()
        assert games == 15
        cap = connection.execute(text(
            "SELECT salary_cap_cents FROM seasons WHERE start_year=2025"
        )).scalar_one()
        assert cap == 9_550_000_000


def test_set_based_team_stint_backfill_is_idempotent(migrated_database):
    import psycopg2
    from sqlalchemy import text

    ingestion.ingest_moneypuck(
        MoneyPuckSession(),
        expected_seasons=(2024, 2025),
        minimum_rows_per_kind=2,
        maximum_duplicate_ratio=0.5,
    )

    connection = psycopg2.connect(TEST_DATABASE_URL)
    try:
        assert team_stints.plan_team_stint_backfill(connection) == {
            "canonical_assignments": 4,
            "missing_assignments": 4,
        }
        assert team_stints.apply_team_stint_backfill(connection) == {
            "canonical_assignments": 4,
            "missing_assignments": 4,
            "inserted_assignments": 4,
        }
        connection.commit()
        assert team_stints.apply_team_stint_backfill(connection) == {
            "canonical_assignments": 4,
            "missing_assignments": 0,
            "inserted_assignments": 0,
        }
        connection.commit()
    finally:
        connection.close()

    with migrated_database.connect() as connection:
        rows = connection.execute(text(
            """SELECT pts.season_start_year, t.abbreviation
               FROM player_team_stints pts
               JOIN teams t ON t.id = pts.team_id
               ORDER BY pts.season_start_year, t.abbreviation"""
        )).all()
        assert rows == [(2024, "AAA"), (2024, "BBB"), (2025, "AAA"), (2025, "BBB")]


def test_failed_ingestion_rolls_back_players_teams_and_stats(migrated_database):
    from psycopg2.errors import ForeignKeyViolation
    from sqlalchemy import text

    with pytest.raises(ForeignKeyViolation):
        ingestion.ingest_moneypuck(
            MoneyPuckSession(season=2199),
            expected_seasons=(2024, 2199),
            minimum_rows_per_kind=2,
            maximum_duplicate_ratio=0.5,
        )
    with migrated_database.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM players")).scalar_one() == 0
        assert connection.execute(text("SELECT count(*) FROM teams")).scalar_one() == 0
        assert connection.execute(text("SELECT count(*) FROM skater_advanced_season_stats")).scalar_one() == 0


def test_contract_and_salary_cap_ingestion_is_idempotent_and_upserts(migrated_database):
    from sqlalchemy import text

    first = ingestion.ingest_capwages(CapWagesSession(), minimum_players=1)
    second = ingestion.ingest_capwages(CapWagesSession("$1,250,000"), minimum_players=1)
    expected_common = {
        "players": 1,
        "contracts": 1,
        "contract_seasons": 1,
        "profile_failures": 0,
        "records_read": 3,
        "records_skipped": 0,
        "reconciliation_policy": "retain_missing",
    }
    assert {key: first[key] for key in expected_common} == expected_common
    assert {key: second[key] for key in expected_common} == expected_common
    assert (first["records_created"], first["records_updated"]) == (2, 0)
    assert (second["records_created"], second["records_updated"]) == (0, 2)

    with migrated_database.connect() as connection:
        result = connection.execute(text("""
            SELECT count(*) OVER (), cs.cap_hit_cents, cs.cap_percentage,
                   c.total_value_cents, c.average_value_cents
            FROM contracts c JOIN contract_seasons cs ON cs.contract_id = c.id
        """)).one()
        assert result[0] == 1
        assert result[1] == 125_000_000
        assert float(result[2]) == pytest.approx(125_000_000 / 9_550_000_000)
        assert result[3] == 200_000_000
        assert result[4] == 125_000_000


def test_partial_contract_profile_refresh_is_rejected_before_database_writes(migrated_database):
    from sqlalchemy import text

    with pytest.raises(ingestion.IngestionValidationError, match="refusing partial refresh"):
        ingestion.ingest_capwages(
            CapWagesSession(fail_profile=True),
            minimum_players=1,
            minimum_profile_success_ratio=1.0,
        )
    with migrated_database.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM contracts")).scalar_one() == 0
        run = connection.execute(text("""
            SELECT status, error_message FROM ingestion_runs
            WHERE job_name='ingest_capwages' ORDER BY id DESC LIMIT 1
        """)).one()
        assert run[0] == "failed"
        assert "refusing partial refresh" in run[1]


def test_contract_rejects_noncontiguous_years_and_impossible_cap_hit(
    migrated_database
):
    from sqlalchemy import text

    class InvalidContract(CapWagesSession):
        def __init__(self, mode):
            super().__init__()
            self.mode = mode

        def get(self, url, timeout):
            response = super().get(url, timeout)
            if not url.endswith("/players/active"):
                payload = json.loads(response.text.split(">", 1)[1].rsplit("<", 1)[0])
                details = payload["props"]["pageProps"]["player"]["contracts"][0]["details"]
                if self.mode == "gap":
                    details.append({"season": "2027-28", "capHit": "$1,000,000"})
                else:
                    details[0]["capHit"] = "$100,000,000"
                response.text = (
                    '<script id="__NEXT_DATA__" type="application/json">'
                    + json.dumps(payload)
                    + "</script>"
                )
            return response

    with pytest.raises(ingestion.IngestionValidationError, match="non-contiguous"):
        ingestion.ingest_capwages(InvalidContract("gap"), minimum_players=1)
    with pytest.raises(ingestion.IngestionValidationError, match="exceeds the season salary cap"):
        ingestion.ingest_capwages(InvalidContract("cap"), minimum_players=1)
    with migrated_database.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM contracts")).scalar_one() == 0


def test_nhl_stats_are_deduplicated_idempotent_and_retain_missing_rows(
    migrated_database, monkeypatch
):
    from sqlalchemy import text

    monkeypatch.setattr(
        ingestion,
        "_nhl_stats_pages",
        lambda session, kind, season, game_type: nhl_stat_rows(
            kind, season, game_type, goals=5
        ),
    )
    first = ingestion.ingest_nhl_stats(Mock(), first_season=2025, last_season=2025)
    monkeypatch.setattr(
        ingestion,
        "_nhl_stats_pages",
        lambda session, kind, season, game_type: nhl_stat_rows(
            kind, season, game_type, goals=8
        ),
    )
    second = ingestion.ingest_nhl_stats(Mock(), first_season=2025, last_season=2025)
    expected_common = {
        "skater": 2,
        "goalie": 2,
        "records_read": 8,
        "records_skipped": 4,
        "reconciliation_policy": "retain_missing",
    }
    assert {key: first[key] for key in expected_common} == expected_common
    assert {key: second[key] for key in expected_common} == expected_common
    assert (first["records_created"], first["records_updated"]) == (4, 0)
    assert (second["records_created"], second["records_updated"]) == (0, 4)
    with migrated_database.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM skater_season_stats")).scalar_one() == 2
        assert connection.execute(text("SELECT count(*) FROM goalie_season_stats")).scalar_one() == 2
        assert connection.execute(text("""
            SELECT goals FROM skater_season_stats WHERE game_type=2
        """)).scalar_one() == 8
        assert connection.execute(text("""
            SELECT count(*) FROM skater_season_stats WHERE stat_scope='TOTAL' AND team_id IS NULL
        """)).scalar_one() == 2
        stint_teams = connection.execute(text("""
            SELECT DISTINCT t.abbreviation
            FROM player_team_stints pts JOIN teams t ON t.id=pts.team_id
            WHERE pts.season_start_year=2025
        """)).scalars().all()
        assert stint_teams == ["BBB"]


def test_nhl_roster_loader_enforces_completeness_and_upserts(migrated_database):
    from sqlalchemy import text

    with pytest.raises(ingestion.IngestionValidationError, match="minimum is 2"):
        ingestion.ingest_nhl_rosters(
            NhlRosterSession(), minimum_teams=2, minimum_active_players=1
        )
    first = ingestion.ingest_nhl_rosters(
        NhlRosterSession(), minimum_teams=1, minimum_active_players=1
    )
    second = ingestion.ingest_nhl_rosters(
        NhlRosterSession(), minimum_teams=1, minimum_active_players=1
    )
    assert first == second == {"teams": 1, "active_players": 1}
    with migrated_database.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM players")).scalar_one() == 1
        assert connection.execute(text("SELECT count(*) FROM player_team_stints")).scalar_one() == 1
        statuses = connection.execute(text("""
            SELECT status FROM ingestion_runs WHERE job_name='ingest_nhl_rosters' ORDER BY id
        """)).scalars().all()
        assert statuses == ["failed", "succeeded", "succeeded"]


def test_schedule_upsert_retains_games_missing_from_a_later_snapshot(migrated_database):
    from sqlalchemy import text

    first = ingestion.ingest_schedule(ScheduleSession(), season=2025, minimum_games=1)
    second = ingestion.ingest_schedule(
        ScheduleSession((2025020001,)), season=2025, minimum_games=1
    )
    assert first["games"] == 2
    assert second == {
        "games": 1,
        "records_read": 1,
        "records_created": 0,
        "records_updated": 1,
        "records_skipped": 0,
        "reconciliation_policy": "retain_missing",
    }
    with migrated_database.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM games")).scalar_one() == 2


def test_cross_source_identity_uses_external_id_and_avoids_ambiguous_names(
    migrated_database, monkeypatch
):
    from sqlalchemy import text

    options = {
        "expected_seasons": (2024, 2025),
        "minimum_rows_per_kind": 2,
        "maximum_duplicate_ratio": 0.5,
    }
    ingestion.ingest_moneypuck(MoneyPuckSession(), **options)
    monkeypatch.setattr(
        ingestion,
        "_nhl_stats_pages",
        lambda session, kind, season, game_type: nhl_stat_rows(kind, season, game_type),
    )
    ingestion.ingest_nhl_stats(Mock(), first_season=2025, last_season=2025)
    with migrated_database.begin() as connection:
        assert connection.execute(text("SELECT count(*) FROM players")).scalar_one() == 2
        linked = connection.execute(text("""
            SELECT count(DISTINCT player_id) FROM player_external_ids
            WHERE external_id='1001' AND source_id IN (
                SELECT id FROM data_sources WHERE code IN ('nhl','moneypuck')
            )
        """)).scalar_one()
        assert linked == 1
        connection.execute(text("""
            INSERT INTO players (first_name,last_name) VALUES ('Fixture','Skater')
        """))
    # An ambiguous name must not steal either existing player's identity.
    class AmbiguousCapWages(CapWagesSession):
        def get(self, url, timeout):
            response = super().get(url, timeout)
            if url.endswith("/players/active"):
                payload = json.loads(response.text.split(">", 1)[1].rsplit("<", 1)[0])
                payload["props"]["pageProps"]["playersArray"][0][0] = "Fixture Skater"
                response.text = (
                    '<script id="__NEXT_DATA__" type="application/json">'
                    + json.dumps(payload)
                    + "</script>"
                )
            return response

    ingestion.ingest_capwages(AmbiguousCapWages(), minimum_players=1)
    with migrated_database.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM players")).scalar_one() == 4


def test_ingestion_foreign_keys_and_grain_indexes_match_loader_contract(migrated_database):
    from sqlalchemy import text

    with migrated_database.connect() as connection:
        constraints = connection.execute(text("""
            SELECT conname, confdeltype
            FROM pg_constraint
            WHERE conname IN (
                'player_external_ids_player_id_fkey',
                'contracts_player_id_fkey',
                'contract_seasons_contract_id_fkey'
            )
        """)).all()
        assert dict(constraints) == {
            "player_external_ids_player_id_fkey": "c",
            "contracts_player_id_fkey": "r",
            "contract_seasons_contract_id_fkey": "c",
        }
        indexes = connection.execute(text("""
            SELECT indexname FROM pg_indexes
            WHERE indexname IN (
                'skater_season_stats_grain_idx',
                'goalie_season_stats_grain_idx',
                'skater_advanced_stats_grain_idx',
                'goalie_advanced_stats_grain_idx',
                'contracts_source_external_id_idx'
            )
        """)).scalars().all()
        assert len(indexes) == 5


def test_roster_repository_persists_statuses_ltir_and_ahl_identity(migrated_database):
    from datetime import date
    from sqlalchemy import text

    from app.ScriptingFiles.FullDataScript.roster_status.roster_models import (
        ExternalRosterPlayer,
        FetchResult,
    )
    from app.ScriptingFiles.FullDataScript.roster_status.roster_repository import (
        PostgresRosterRepository,
    )
    from app.ScriptingFiles.FullDataScript.roster_status.roster_status_service import (
        RosterStatusService,
    )

    with migrated_database.begin() as connection:
        connection.execute(text("""
            INSERT INTO players (id,first_name,last_name,birth_date,roster_status) VALUES
                (11,'Active','Fixture','1990-01-01','UNKNOWN'),
                (12,'Minor','Fixture','1991-02-02','ACTIVE'),
                (13,'Injured','Fixture','1992-03-03','ACTIVE');
            INSERT INTO player_external_ids (player_id,source_id,external_id)
            SELECT 11,id,'11' FROM data_sources WHERE code='nhl';
            INSERT INTO player_external_ids (player_id,source_id,external_id)
            SELECT 12,id,'12' FROM data_sources WHERE code='nhl';
            INSERT INTO player_external_ids (player_id,source_id,external_id)
            SELECT 13,id,'13' FROM data_sources WHERE code='nhl';
            INSERT INTO ltir_overrides (player_id,start_date) VALUES (13,'2025-01-01');
        """))

    class Feed:
        def __init__(self, result):
            self.result = result

        def fetch_current_rosters(self):
            return self.result

    with ingestion.database_transaction() as connection:
        summary = RosterStatusService(
            PostgresRosterRepository(connection),
            Feed(FetchResult(
                items={"11": ExternalRosterPlayer("11", "Renamed Active")},
                complete=True,
            )),
            Feed(FetchResult(
                items=[ExternalRosterPlayer("ahl-12", "Minor Fixture", date(1991, 2, 2))],
                complete=True,
            )),
        ).sync(date(2025, 10, 1))
    assert (summary.active_count, summary.minors_count, summary.ltir_count) == (1, 1, 1)

    with migrated_database.begin() as connection:
        statuses = dict(connection.execute(text(
            "SELECT id,roster_status::text FROM players ORDER BY id"
        )).all())
        assert statuses == {11: "ACTIVE", 12: "MINORS", 13: "LTIR"}
        assert connection.execute(text("""
            SELECT count(*) FROM player_external_ids external
            JOIN data_sources source ON source.id=external.source_id
            WHERE source.code='ahl' AND external.player_id=12 AND external.external_id='ahl-12'
        """)).scalar_one() == 1
        connection.execute(text("DELETE FROM players WHERE id=12"))
        assert connection.execute(text("""
            SELECT count(*) FROM player_external_ids WHERE player_id=12
        """)).scalar_one() == 0


def test_ingestion_run_tracking_and_concurrent_run_lock(migrated_database):
    import psycopg2
    from sqlalchemy import text

    from app.ScriptingFiles.FullDataScript import ingestion_tracking

    @ingestion_tracking.tracked_ingestion("nhl", "overlap_fixture")
    def fixture_stage():
        return {"rows": 1}

    lock_connection = psycopg2.connect(TEST_DATABASE_URL)
    try:
        with lock_connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_lock(%s)",
                (ingestion_tracking.advisory_lock_key("overlap_fixture"),),
            )
        lock_connection.commit()
        with pytest.raises(ingestion_tracking.ConcurrentIngestionError, match="already running"):
            fixture_stage()
    finally:
        with lock_connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_unlock(%s)",
                (ingestion_tracking.advisory_lock_key("overlap_fixture"),),
            )
        lock_connection.commit()
        lock_connection.close()

    assert fixture_stage() == {"rows": 1}
    with migrated_database.connect() as connection:
        runs = connection.execute(text("""
            SELECT status,records_read,records_updated,error_message
            FROM ingestion_runs WHERE job_name='overlap_fixture' ORDER BY id
        """)).all()
        assert [row[0] for row in runs] == ["cancelled", "succeeded"]
        assert runs[1][1:3] == (1, 1)
        assert "already holds" in runs[0][3]


def test_incomplete_roster_feed_rolls_back_detected_status_changes(
    migrated_database, monkeypatch
):
    from sqlalchemy import text

    from app.ScriptingFiles.FullDataScript import populate_roster_status
    from app.ScriptingFiles.FullDataScript.roster_status.roster_models import (
        ExternalRosterPlayer,
        FetchResult,
    )

    with migrated_database.begin() as connection:
        connection.execute(text("""
            INSERT INTO players (id,first_name,last_name,roster_status)
            VALUES (21,'Partial','Fixture','MINORS');
            INSERT INTO player_external_ids (player_id,source_id,external_id)
            SELECT 21,id,'21' FROM data_sources WHERE code='nhl';
        """))

    class Feed:
        def __init__(self, result=None):
            self.result = result

        def fetch_current_rosters(self):
            return self.result

    monkeypatch.setattr(
        populate_roster_status,
        "NhlRosterService",
        lambda: Feed(FetchResult(
            items={"21": ExternalRosterPlayer("21", "Partial Fixture")},
            complete=False,
            errors=("one NHL team failed",),
        )),
    )
    monkeypatch.setattr(
        populate_roster_status,
        "AhlRosterService",
        lambda: Feed(FetchResult(items=[], complete=True)),
    )
    with pytest.raises(populate_roster_status.IncompleteRosterFeedError):
        populate_roster_status.sync_roster_status()

    with migrated_database.connect() as connection:
        assert connection.execute(text(
            "SELECT roster_status::text FROM players WHERE id=21"
        )).scalar_one() == "MINORS"
        assert connection.execute(text("""
            SELECT status FROM ingestion_runs
            WHERE job_name='populate_roster_status' ORDER BY id DESC LIMIT 1
        """)).scalar_one() == "failed"
