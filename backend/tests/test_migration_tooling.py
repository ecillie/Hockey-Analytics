from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from backend.database import migration_preflight, schema_snapshot, verify_migrations


ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_CONFIG = ROOT / "backend" / "alembic.ini"
INITIAL_REVISION = (
    ROOT
    / "backend"
    / "migrations"
    / "versions"
    / "20260910_0001_initial_schema.py"
)
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


def load_initial_revision():
    spec = importlib.util.spec_from_file_location("tradevalue_initial_revision", INITIAL_REVISION)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_frozen_initial_schema_checksum_and_transaction_stripping():
    revision = load_initial_revision()

    body = revision._schema_body()

    assert "CREATE TYPE roster_status" in body
    assert "CREATE TABLE predictions" in body
    assert "\nBEGIN;" not in body
    assert "\nCOMMIT;" not in body


def test_frozen_initial_schema_rejects_edits(tmp_path):
    revision = load_initial_revision()
    changed_schema = tmp_path / "schema.sql"
    changed_schema.write_text("BEGIN;\nSELECT 1;\nCOMMIT;\n", encoding="utf-8")

    with patch.object(revision, "SCHEMA_PATH", changed_schema):
        with pytest.raises(RuntimeError, match="frozen initial-schema snapshot"):
            revision._schema_body()


def test_initial_revision_emits_raw_sql_in_offline_mode():
    revision = load_initial_revision()
    context = Mock(as_sql=True)

    with patch.object(revision.op, "get_context", return_value=context):
        revision._execute_script("SELECT 1;")

    context.impl.static_output.assert_called_once_with("SELECT 1;\n")


def test_initial_revision_executes_raw_sql_and_closes_cursor_online():
    revision = load_initial_revision()
    context = Mock(as_sql=False)
    bind = Mock()
    cursor = bind.connection.cursor.return_value

    with (
        patch.object(revision.op, "get_context", return_value=context),
        patch.object(revision.op, "get_bind", return_value=bind),
    ):
        revision._execute_script("SELECT 100 % 9;")

    cursor.execute.assert_called_once_with("SELECT 100 % 9;")
    cursor.close.assert_called_once_with()


def migration_scripts(*revisions, heads=("head",)):
    scripts = Mock()
    scripts.get_heads.return_value = list(heads)
    scripts.walk_revisions.return_value = list(revisions)
    return scripts


def revision(name="revision", *, doc="description", merge=False):
    return SimpleNamespace(revision=name, doc=doc, is_merge_point=merge)


def test_migration_history_accepts_one_documented_linear_head():
    scripts = migration_scripts(revision("one"))

    with patch.object(verify_migrations.ScriptDirectory, "from_config", return_value=scripts):
        assert verify_migrations.validate(ALEMBIC_CONFIG) == []


@pytest.mark.parametrize(
    ("scripts", "message"),
    [
        (migration_scripts(revision(), heads=()), "exactly one migration head"),
        (migration_scripts(revision(), heads=("one", "two")), "exactly one migration head"),
        (migration_scripts(heads=("one",)), "migration history is empty"),
        (migration_scripts(revision(doc="")), "has no description"),
        (migration_scripts(revision(merge=True)), "unapproved merge point"),
    ],
)
def test_migration_history_rejects_invalid_graphs(scripts, message):
    with patch.object(verify_migrations.ScriptDirectory, "from_config", return_value=scripts):
        assert any(message in error for error in verify_migrations.validate(ALEMBIC_CONFIG))


def test_database_url_prefers_primary_url():
    with patch.dict(
        os.environ,
        {"DATABASE_URL": "postgresql://primary/db", "TEST_DATABASE_URL": "postgresql://test/db"},
        clear=True,
    ):
        assert schema_snapshot.database_url() == "postgresql://primary/db"
        assert migration_preflight.database_url() == "postgresql://primary/db"


def test_database_url_falls_back_to_test_url_and_requires_one():
    with patch.dict(os.environ, {"TEST_DATABASE_URL": "postgresql://test/db"}, clear=True):
        assert schema_snapshot.database_url() == "postgresql://test/db"
        assert migration_preflight.database_url() == "postgresql://test/db"

    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(RuntimeError, match="DATABASE_URL or TEST_DATABASE_URL"):
            schema_snapshot.database_url()
        with pytest.raises(RuntimeError, match="DATABASE_URL or TEST_DATABASE_URL"):
            migration_preflight.database_url()


def test_schema_snapshot_render_is_deterministic():
    rendered = schema_snapshot.render({"tables": [{"table_name": "players"}]})

    assert rendered == '{\n  "tables": [\n    {\n      "table_name": "players"\n    }\n  ]\n}\n'


def run_snapshot_main(*arguments):
    with patch.object(sys, "argv", ["schema_snapshot.py", *map(str, arguments)]):
        return schema_snapshot.main()


def test_schema_snapshot_update_then_compare(tmp_path):
    expected = tmp_path / "expected.json"
    actual = tmp_path / "actual.json"
    catalog = {"tables": [{"table_name": "players"}]}

    with patch.object(schema_snapshot, "snapshot", return_value=catalog):
        assert run_snapshot_main("--expected", expected, "--update") == 0
        assert run_snapshot_main("--expected", expected, "--actual", actual) == 0

    assert expected.read_text(encoding="utf-8") == actual.read_text(encoding="utf-8")


def test_schema_snapshot_reports_missing_and_drifted_contracts(tmp_path, capsys):
    expected = tmp_path / "expected.json"
    actual = tmp_path / "actual.json"
    expected.write_text(schema_snapshot.render({"tables": []}), encoding="utf-8")

    with patch.object(
        schema_snapshot,
        "snapshot",
        return_value={"tables": [{"table_name": "players"}]},
    ):
        assert run_snapshot_main("--expected", expected, "--actual", actual) == 1
    assert "does not match" in capsys.readouterr().out
    assert "players" in actual.read_text(encoding="utf-8")

    with patch.object(schema_snapshot, "snapshot", return_value={"tables": []}):
        assert run_snapshot_main("--expected", tmp_path / "missing.json") == 1
    assert "snapshot is missing" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("tables", "versions", "expected"),
    [
        ([], [], None),
        (["players"], ["20260910_0001"], None),
        (["players"], [], "no Alembic revision"),
        (["players"], ["one", "two"], "multiple Alembic revisions"),
    ],
)
def test_migration_preflight_decisions(tables, versions, expected):
    error = migration_preflight.validate_preconditions(tables, versions)

    if expected is None:
        assert error is None
    else:
        assert expected in error


def test_migration_preflight_inspects_tables_and_revision():
    connection = Mock()
    table_result = Mock()
    table_result.scalars.return_value.all.return_value = ["players", "teams"]
    exists_result = Mock()
    exists_result.scalar_one.return_value = True
    version_result = Mock()
    version_result.scalars.return_value.all.return_value = ["20260910_0001"]
    connection.execute.side_effect = [table_result, exists_result, version_result]

    assert migration_preflight.inspect_database(connection) == (
        ["players", "teams"],
        ["20260910_0001"],
    )


def test_migration_preflight_does_not_query_missing_version_table():
    connection = Mock()
    table_result = Mock()
    table_result.scalars.return_value.all.return_value = []
    exists_result = Mock()
    exists_result.scalar_one.return_value = False
    connection.execute.side_effect = [table_result, exists_result]

    assert migration_preflight.inspect_database(connection) == ([], [])
    assert connection.execute.call_count == 2


def import_migration_smoke():
    os.environ.setdefault("ENV", "dev")
    os.environ.setdefault("DATABASE_URL", "postgresql://example.test/tradevalue")
    from backend.database import migration_smoke

    return migration_smoke


def test_reference_data_smoke_accepts_complete_baseline():
    migration_smoke = import_migration_smoke()
    session = Mock()
    sources = Mock()
    sources.scalars.return_value.all.return_value = ["capwages", "moneypuck", "nhl"]
    seasons = Mock()
    seasons.scalar_one.return_value = 22
    session.execute.side_effect = [sources, seasons]

    migration_smoke.validate_reference_data(session)


@pytest.mark.parametrize(
    ("sources", "seasons"),
    [(["nhl"], 22), (["capwages", "moneypuck", "nhl"], 21)],
)
def test_reference_data_smoke_rejects_incomplete_baseline(sources, seasons):
    migration_smoke = import_migration_smoke()
    session = Mock()
    source_result = Mock()
    source_result.scalars.return_value.all.return_value = sources
    season_result = Mock()
    season_result.scalar_one.return_value = seasons
    session.execute.side_effect = [source_result, season_result]

    with pytest.raises(RuntimeError, match="initial reference data is incomplete"):
        migration_smoke.validate_reference_data(session)


def response(status, body, text_body=None):
    result = Mock(status_code=status, text=text_body or str(body))
    result.json.return_value = body
    return result


def test_api_smoke_accepts_expected_empty_database_responses():
    migration_smoke = import_migration_smoke()
    client = Mock()
    client.get.side_effect = [
        response(200, {"status": "ok"}),
        response(200, {"availableSeasons": [{}], "currentSeason": 2026}),
        response(200, []),
    ]

    migration_smoke.smoke_checks(client)

    assert [call.args[0] for call in client.get.call_args_list] == [
        "/api/health",
        "/api/seasons",
        "/api/teams",
    ]


@pytest.mark.parametrize(
    "responses",
    [
        [response(503, {"error": "down"})],
        [response(200, {"status": "wrong"})],
        [response(200, {"status": "ok"}), response(200, {"availableSeasons": [], "currentSeason": 2026})],
        [
            response(200, {"status": "ok"}),
            response(200, {"availableSeasons": [{}], "currentSeason": 2026}),
            response(200, [{"id": 1}]),
        ],
    ],
)
def test_api_smoke_rejects_bad_status_or_payload(responses):
    migration_smoke = import_migration_smoke()
    client = Mock()
    client.get.side_effect = responses

    with pytest.raises(RuntimeError, match="post-migration smoke check failed"):
        migration_smoke.smoke_checks(client)


def test_api_smoke_rejects_invalid_json():
    migration_smoke = import_migration_smoke()
    client = Mock()
    invalid = response(200, {}, "not-json")
    invalid.json.side_effect = ValueError("invalid JSON")
    client.get.return_value = invalid

    with pytest.raises(RuntimeError, match="body=not-json"):
        migration_smoke.smoke_checks(client)


def run_command(database_url: str, *arguments: str, success=True):
    environment = {
        **os.environ,
        "DATABASE_URL": database_url,
        "TEST_DATABASE_URL": database_url,
        "ENV": "dev",
        "PYTHONPATH": "backend",
    }
    result = subprocess.run(
        [sys.executable, *arguments],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if success and result.returncode != 0:
        pytest.fail(f"command failed: {arguments}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}")
    if not success and result.returncode == 0:
        pytest.fail(f"command unexpectedly passed: {arguments}")
    return result


def test_alembic_environment_rejects_non_postgresql_database(tmp_path):
    result = run_command(
        f"sqlite:///{tmp_path / 'wrong.db'}",
        "-m",
        "alembic",
        "-c",
        str(ALEMBIC_CONFIG),
        "upgrade",
        "head",
        "--sql",
        success=False,
    )

    assert "TradeValue migrations require PostgreSQL" in result.stderr


@pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is required for migration lifecycle integration tests",
)
def test_complete_migration_lifecycle_on_isolated_database(tmp_path):
    source_url = make_url(TEST_DATABASE_URL)
    database_name = f"tradevalue_migration_{uuid4().hex[:12]}"
    database_url = source_url.set(database=database_name).render_as_string(hide_password=False)
    admin_url = source_url.set(database="postgres")
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT", pool_pre_ping=True)
    quoted_name = admin.dialect.identifier_preparer.quote(database_name)

    with admin.connect() as connection:
        connection.execute(text(f"CREATE DATABASE {quoted_name}"))

    try:
        run_command(database_url, "backend/database/verify_migrations.py")
        run_command(database_url, "backend/database/migration_preflight.py")

        isolated = create_engine(database_url)
        with isolated.begin() as connection:
            connection.execute(text("CREATE TABLE players (id bigint PRIMARY KEY)"))
        unsafe = run_command(
            database_url,
            "backend/database/migration_preflight.py",
            success=False,
        )
        assert "has no Alembic revision" in unsafe.stdout
        with isolated.begin() as connection:
            connection.execute(text("DROP TABLE players"))
        isolated.dispose()

        offline_sql = run_command(
            database_url,
            "-m",
            "alembic",
            "-c",
            str(ALEMBIC_CONFIG),
            "upgrade",
            "head",
            "--sql",
        ).stdout
        assert "CREATE TABLE players" in offline_sql
        assert "20260910_0001" in offline_sql

        alembic = ("-m", "alembic", "-c", str(ALEMBIC_CONFIG))
        run_command(database_url, *alembic, "upgrade", "head")
        run_command(database_url, *alembic, "upgrade", "head")
        current = run_command(database_url, *alembic, "current", "--check-heads")
        assert "20260910_0001 (head)" in current.stdout
        run_command(
            database_url,
            "backend/database/schema_snapshot.py",
            "--actual",
            str(tmp_path / "actual.json"),
        )
        run_command(database_url, "backend/database/migration_smoke.py")

        run_command(database_url, *alembic, "downgrade", "base")
        run_command(database_url, "backend/database/migration_preflight.py")
        run_command(database_url, *alembic, "upgrade", "head")
        run_command(database_url, "backend/database/schema_snapshot.py")

        isolated = create_engine(database_url)
        with isolated.connect() as connection:
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "20260910_0001"
            assert connection.execute(text("SELECT COUNT(*) FROM seasons")).scalar_one() == 22
            assert connection.execute(text("SELECT COUNT(*) FROM data_sources")).scalar_one() == 3
        isolated.dispose()
    finally:
        with admin.connect() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :database_name AND pid <> pg_backend_pid()"
                ),
                {"database_name": database_name},
            )
            connection.execute(text(f"DROP DATABASE IF EXISTS {quoted_name}"))
        admin.dispose()
