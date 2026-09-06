"""Populate player roster statuses from the free NHL/AHL roster feeds.

Usage from the backend directory:
    python -m app.ScriptingFiles.FullDataScript.populate_roster_status
"""

from __future__ import annotations

import logging

from app.database import database_transaction, init_db
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


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        init_db()
        with database_transaction() as connection:
            service = RosterStatusService(
                repository=PostgresRosterRepository(connection),
                nhl_service=NhlRosterService(),
                ahl_service=AhlRosterService(),
            )
            summary = service.sync()
    except Exception:
        LOGGER.exception("Roster-status sync failed; database changes were rolled back")
        return 1

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
