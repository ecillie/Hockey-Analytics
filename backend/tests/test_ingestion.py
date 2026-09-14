from __future__ import annotations

import os
from contextlib import contextmanager
import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from app.ScriptingFiles.FullDataScript import ingestion


FIXTURES = Path(__file__).parent / "fixtures" / "ingestion"
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


class CsvResponse:
    def __init__(self, text: str):
        self.text = text

    def raise_for_status(self):
        return None


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
    def __init__(self, cap_hit: str = "$1,000,000"):
        self.cap_hit = cap_hit

    def get(self, url, timeout):
        if url.endswith("/players/active"):
            row = ["Contract Fixture", "contract-fixture", "AAA", "C"] + [None] * 27
            row[7] = "USA"
            row[30] = "98-2-3"
            payload = {"props": {"pageProps": {"playersArray": [row]}}}
        else:
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


def test_run_all_uses_last_good_contract_snapshot_but_not_for_other_failures():
    expected = {"players": 600, "contracts": 500, "contract_seasons": 900, "cached": 1}
    with (
        patch.object(ingestion, "init_db"),
        patch.object(ingestion, "http_session", return_value=Mock()),
        patch.object(ingestion, "ingest_moneypuck", return_value={}),
        patch.object(ingestion, "ingest_nhl_rosters", return_value={}),
        patch.object(ingestion, "ingest_nhl_stats", return_value={}),
        patch.object(ingestion, "ingest_capwages", side_effect=RuntimeError("partial feed")),
        patch.object(ingestion, "existing_capwages_summary", return_value=expected),
        patch.object(ingestion, "ingest_schedule", return_value={"games": 10}),
    ):
        result = ingestion.run_all()
    assert result["capwages"] == expected
    assert result["schedule"] == {"games": 10}

    with (
        patch.object(ingestion, "init_db"),
        patch.object(ingestion, "http_session", return_value=Mock()),
        patch.object(ingestion, "ingest_moneypuck", side_effect=RuntimeError("bad stats")),
        patch.object(ingestion, "ingest_nhl_rosters") as rosters,
    ):
        with pytest.raises(RuntimeError, match="bad stats"):
            ingestion.run_all()
    rosters.assert_not_called()


@pytest.fixture()
def migrated_database(monkeypatch):
    if not TEST_DATABASE_URL or "tradevalue_test" not in TEST_DATABASE_URL:
        pytest.skip("a disposable tradevalue_test database is required")
    from sqlalchemy import create_engine, text

    engine = create_engine(TEST_DATABASE_URL)
    with engine.begin() as connection:
        if connection.execute(text("SELECT to_regclass('public.players')")).scalar_one() is None:
            pytest.skip("the test database has not been migrated")
        connection.execute(text("TRUNCATE teams, players RESTART IDENTITY CASCADE"))

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

    first = ingestion.ingest_moneypuck(MoneyPuckSession(skater_games=12))
    second = ingestion.ingest_moneypuck(MoneyPuckSession(skater_games=15))
    assert first == second == {"players": 2, "skater": 2, "goalie": 2}

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


def test_failed_ingestion_rolls_back_players_teams_and_stats(migrated_database):
    from psycopg2.errors import ForeignKeyViolation
    from sqlalchemy import text

    with pytest.raises(ForeignKeyViolation):
        ingestion.ingest_moneypuck(MoneyPuckSession(season=2199))
    with migrated_database.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM players")).scalar_one() == 0
        assert connection.execute(text("SELECT count(*) FROM teams")).scalar_one() == 0
        assert connection.execute(text("SELECT count(*) FROM skater_advanced_season_stats")).scalar_one() == 0


def test_contract_and_salary_cap_ingestion_is_idempotent_and_upserts(migrated_database):
    from sqlalchemy import text

    first = ingestion.ingest_capwages(CapWagesSession(), minimum_players=1)
    second = ingestion.ingest_capwages(CapWagesSession("$1,250,000"), minimum_players=1)
    assert first == second == {"players": 1, "contracts": 1, "contract_seasons": 1}

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
