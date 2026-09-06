"""Populate player roster statuses from the free NHL/AHL roster feeds.

Usage from the backend directory:
    python -m app.ScriptingFiles.FullDataScript.populate_roster_status
"""

from __future__ import annotations

import logging
import os
from urllib.parse import quote_plus

from app.ScriptingFiles.FullDataScript.roster_status.ahl_roster_service import (
    AhlRosterService,
)
from app.ScriptingFiles.FullDataScript.roster_status.nhl_roster_service import (
    NhlRosterService,
)
from app.ScriptingFiles.FullDataScript.roster_status.roster_repository import (
    PostgresRosterRepository,
)
from app.ScriptingFiles.FullDataScript.roster_status.roster_status_service import (
    RosterStatusService,
)


LOGGER = logging.getLogger(__name__)


def _database_dsn() -> str:
    if os.getenv("DATABASE_URL"):
        return os.environ["DATABASE_URL"]

    user = os.getenv("DB_USER")
    database = os.getenv("DB_NAME")
    if not user or not database:
        raise RuntimeError("Set DATABASE_URL or both DB_USER and DB_NAME")

    password = os.getenv("DB_PASSWORD", "")
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    credentials = quote_plus(user)
    if password:
        credentials += f":{quote_plus(password)}"
    return f"postgresql://{credentials}@{host}:{port}/{quote_plus(database)}"


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        import psycopg2
    except ImportError as exc:
        raise RuntimeError("Roster sync requires psycopg2-binary") from exc

    connection = psycopg2.connect(_database_dsn())
    try:
        service = RosterStatusService(
            repository=PostgresRosterRepository(connection),
            nhl_service=NhlRosterService(),
            ahl_service=AhlRosterService(),
        )
        summary = service.sync()
        connection.commit()
    except Exception:
        connection.rollback()
        LOGGER.exception("Roster-status sync failed; database changes were rolled back")
        return 1
    finally:
        connection.close()

    LOGGER.info(
        "Roster sync complete: updated=%s active=%s minors=%s ltir=%s "
        "unknown=%s preserved=%s",
        summary.statuses_updated,
        summary.active_count,
        summary.minors_count,
        summary.ltir_count,
        summary.unknown_count,
        summary.preserved_count,
    )
    if summary.errors:
        LOGGER.error("Roster sync completed with incomplete feeds")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
