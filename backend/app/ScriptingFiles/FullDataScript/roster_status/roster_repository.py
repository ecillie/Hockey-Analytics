"""PostgreSQL persistence adapter for roster-status synchronization."""

from __future__ import annotations

from datetime import date
from typing import Iterable, Protocol

from app.ScriptingFiles.FullDataScript.roster_status.roster_models import (
    RosterStatus,
    StoredPlayer,
)


class RosterRepository(Protocol):
    def load_players(self) -> list[StoredPlayer]: ...

    def load_active_ltir_player_ids(self, as_of: date) -> set[int]: ...

    def bulk_update_statuses(self, updates: dict[int, RosterStatus]) -> None: ...

    def save_ahl_external_ids(
        self,
        matches: Iterable[tuple[int, str, str]],
    ) -> None: ...


class PostgresRosterRepository:
    """Uses a PEP-249 connection, such as a psycopg2 connection."""

    def __init__(self, connection: object) -> None:
        self.connection = connection

    def load_players(self) -> list[StoredPlayer]:
        query = """
            SELECT
                p.id,
                p.first_name,
                p.last_name,
                p.birth_date,
                p.roster_status::text,
                MAX(pei.external_id) FILTER (WHERE ds.code = 'nhl') AS nhl_external_id,
                MAX(pei.external_id) FILTER (WHERE ds.code = 'ahl') AS ahl_external_id
            FROM players p
            LEFT JOIN player_external_ids pei ON pei.player_id = p.id
            LEFT JOIN data_sources ds ON ds.id = pei.source_id
            GROUP BY p.id, p.first_name, p.last_name, p.birth_date, p.roster_status
            ORDER BY p.id
        """
        with self.connection.cursor() as cursor:
            cursor.execute(query)
            return [
                StoredPlayer(
                    id=row[0],
                    first_name=row[1],
                    last_name=row[2],
                    birth_date=row[3],
                    roster_status=RosterStatus(row[4]),
                    nhl_external_id=row[5],
                    ahl_external_id=row[6],
                )
                for row in cursor.fetchall()
            ]

    def load_active_ltir_player_ids(self, as_of: date) -> set[int]:
        query = """
            SELECT DISTINCT player_id
            FROM ltir_overrides
            WHERE start_date <= %s
              AND (end_date IS NULL OR end_date >= %s)
        """
        with self.connection.cursor() as cursor:
            cursor.execute(query, (as_of, as_of))
            return {row[0] for row in cursor.fetchall()}

    def bulk_update_statuses(self, updates: dict[int, RosterStatus]) -> None:
        if not updates:
            return
        query = """
            UPDATE players
            SET roster_status = %s::roster_status,
                roster_status_updated_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """
        with self.connection.cursor() as cursor:
            cursor.executemany(
                query,
                [(status.value, player_id) for player_id, status in updates.items()],
            )

    def save_ahl_external_ids(
        self,
        matches: Iterable[tuple[int, str, str]],
    ) -> None:
        rows = list(matches)
        if not rows:
            return
        query = """
            INSERT INTO player_external_ids (
                player_id,
                source_id,
                external_id,
                source_name
            )
            SELECT %s, ds.id, %s, %s
            FROM data_sources ds
            WHERE ds.code = 'ahl'
            ON CONFLICT (source_id, external_id) DO NOTHING
        """
        with self.connection.cursor() as cursor:
            cursor.executemany(query, rows)
