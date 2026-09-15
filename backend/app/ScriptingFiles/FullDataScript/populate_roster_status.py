"""Populate player roster statuses from the free NHL/AHL roster feeds.

Usage from the backend directory:
    python -m app.ScriptingFiles.FullDataScript.populate_roster_status
"""

from __future__ import annotations

from dataclasses import asdict
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
from app.ScriptingFiles.FullDataScript.ingestion_tracking import tracked_ingestion


LOGGER = logging.getLogger(__name__)


class IncompleteRosterFeedError(RuntimeError):
    pass


@tracked_ingestion("nhl", "populate_roster_status")
def sync_roster_status() -> dict[str, object]:
    with database_transaction() as connection:
        service = RosterStatusService(
            repository=PostgresRosterRepository(connection),
            nhl_service=NhlRosterService(),
            ahl_service=AhlRosterService(),
        )
        summary = service.sync()
        if summary.errors:
            raise IncompleteRosterFeedError("; ".join(summary.errors))
        result = asdict(summary)
        result.update({
            "records_read": summary.statuses_updated + summary.preserved_count,
            "records_updated": summary.statuses_updated,
            "records_skipped": summary.preserved_count,
        })
        return result


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        init_db()
        summary = sync_roster_status()
    except IncompleteRosterFeedError:
        LOGGER.exception("Roster-status sync refused an incomplete feed; changes were rolled back")
        return 2
    except Exception:
        LOGGER.exception("Roster-status sync failed; database changes were rolled back")
        return 1

    LOGGER.info(
        "Roster sync complete: updated=%s active=%s minors=%s ltir=%s "
        "unknown=%s preserved=%s",
        summary["statuses_updated"],
        summary["active_count"],
        summary["minors_count"],
        summary["ltir_count"],
        summary["unknown_count"],
        summary["preserved_count"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
