"""Create the initial TradeValue schema.

Revision ID: 20260910_0001
Revises: None
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from alembic import op


revision = "20260910_0001"
down_revision = None
branch_labels = None
depends_on = None

SCHEMA_SHA256 = "b29d0567ee3a17cb95abe37b00de0cf3589e809fb65019f67bd1e6b74509d2b5"
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "database" / "schema.sql"


def _schema_body() -> str:
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    digest = hashlib.sha256(schema.encode()).hexdigest()
    if digest != SCHEMA_SHA256:
        raise RuntimeError(
            "backend/database/schema.sql is the frozen initial-schema snapshot; "
            "create a new Alembic revision instead of editing it"
        )
    lines = schema.splitlines()
    return "\n".join(line for line in lines if line.strip() not in {"BEGIN;", "COMMIT;"})


def _execute_script(sql: str) -> None:
    context = op.get_context()
    if context.as_sql:
        context.impl.static_output(sql.rstrip() + "\n")
    else:
        # The baseline contains literal percent signs in comments and SQL.
        # Execute it through the DBAPI cursor so psycopg2 does not interpret
        # those literals as pyformat parameters.
        cursor = op.get_bind().connection.cursor()
        try:
            cursor.execute(sql)
        finally:
            cursor.close()


def upgrade() -> None:
    _execute_script(_schema_body())


def downgrade() -> None:
    _execute_script(
        """
DROP TABLE IF EXISTS
    predictions,
    model_versions,
    player_game_stats,
    goalie_advanced_season_stats,
    skater_advanced_season_stats,
    goalie_season_stats,
    skater_season_stats,
    source_records,
    ingestion_runs,
    games,
    contract_seasons,
    contracts,
    player_team_stints,
    ltir_overrides,
    player_external_ids,
    players,
    teams,
    seasons,
    data_sources
CASCADE;
DROP TYPE IF EXISTS roster_status;
"""
    )
