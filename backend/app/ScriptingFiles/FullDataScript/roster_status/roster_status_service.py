"""Coordinate free roster feeds and classify stored players."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
import logging
import unicodedata

from app.ScriptingFiles.FullDataScript.roster_status.ahl_roster_service import AhlRosterService
from app.ScriptingFiles.FullDataScript.roster_status.nhl_roster_service import NhlRosterService
from app.ScriptingFiles.FullDataScript.roster_status.roster_models import (
    ExternalRosterPlayer,
    FetchResult,
    RosterStatus,
    StoredPlayer,
    SyncSummary,
)
from app.ScriptingFiles.FullDataScript.roster_status.roster_repository import (
    RosterRepository,
)


LOGGER = logging.getLogger(__name__)


def normalize_name(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    without_accents = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return "".join(character for character in without_accents.casefold() if character.isalnum())


class RosterStatusService:
    def __init__(
        self,
        repository: RosterRepository,
        nhl_service: NhlRosterService,
        ahl_service: AhlRosterService,
    ) -> None:
        self.repository = repository
        self.nhl_service = nhl_service
        self.ahl_service = ahl_service

    def sync(self, as_of: date | None = None) -> SyncSummary:
        as_of = as_of or date.today()
        players = self.repository.load_players()
        ltir_player_ids = self.repository.load_active_ltir_player_ids(as_of)
        nhl_result = self.nhl_service.fetch_current_rosters()
        ahl_result = self.ahl_service.fetch_current_rosters()

        ahl_matches = self._match_ahl_players(players, ahl_result.items)
        self.repository.save_ahl_external_ids(
            (
                (player_id, match.external_id, match.full_name)
                for player_id, match in ahl_matches.items()
            )
        )

        updates: dict[int, RosterStatus] = {}
        counts = {status: 0 for status in RosterStatus}
        preserved_count = 0

        for player in players:
            status = self._classify(
                player=player,
                ltir_player_ids=ltir_player_ids,
                nhl_result=nhl_result,
                ahl_result=ahl_result,
                ahl_matches=ahl_matches,
            )
            if status is None:
                preserved_count += 1
                continue
            updates[player.id] = status
            counts[status] += 1

        self.repository.bulk_update_statuses(updates)
        errors = nhl_result.errors + ahl_result.errors
        for error in errors:
            LOGGER.warning(error)

        return SyncSummary(
            statuses_updated=len(updates),
            active_count=counts[RosterStatus.ACTIVE],
            minors_count=counts[RosterStatus.MINORS],
            ltir_count=counts[RosterStatus.LTIR],
            unknown_count=counts[RosterStatus.UNKNOWN],
            preserved_count=preserved_count,
            nhl_complete=nhl_result.complete,
            ahl_complete=ahl_result.complete,
            errors=errors,
        )

    @staticmethod
    def _classify(
        player: StoredPlayer,
        ltir_player_ids: set[int],
        nhl_result: FetchResult[dict[str, ExternalRosterPlayer]],
        ahl_result: FetchResult[list[ExternalRosterPlayer]],
        ahl_matches: dict[int, ExternalRosterPlayer],
    ) -> RosterStatus | None:
        if player.id in ltir_player_ids:
            return RosterStatus.LTIR

        if player.nhl_external_id and player.nhl_external_id in nhl_result.items:
            return RosterStatus.ACTIVE

        # NHL takes precedence. Do not mark a player as a minor if some NHL
        # team rosters could not be checked.
        if nhl_result.complete and player.id in ahl_matches:
            return RosterStatus.MINORS

        # UNKNOWN is a meaningful complete-feed result, not an error fallback.
        # Requiring an NHL external ID ensures we actually checked this player
        # by ID instead of inferring their status from a name.
        if (
            nhl_result.complete
            and ahl_result.complete
            and player.nhl_external_id is not None
        ):
            return RosterStatus.UNKNOWN

        return None

    @staticmethod
    def _match_ahl_players(
        players: list[StoredPlayer],
        ahl_players: list[ExternalRosterPlayer],
    ) -> dict[int, ExternalRosterPlayer]:
        ahl_by_id = {player.external_id: player for player in ahl_players}
        matches: dict[int, ExternalRosterPlayer] = {}

        # Once a conservative mapping is stored, all later syncs are ID-based.
        for player in players:
            if player.ahl_external_id and player.ahl_external_id in ahl_by_id:
                matches[player.id] = ahl_by_id[player.ahl_external_id]

        db_by_identity: dict[tuple[str, date], list[StoredPlayer]] = defaultdict(list)
        ahl_by_identity: dict[tuple[str, date], list[ExternalRosterPlayer]] = defaultdict(list)

        for player in players:
            if player.id not in matches and player.birth_date is not None:
                db_by_identity[(normalize_name(player.full_name), player.birth_date)].append(player)

        for ahl_player in ahl_players:
            if ahl_player.birth_date is not None:
                ahl_by_identity[
                    (normalize_name(ahl_player.full_name), ahl_player.birth_date)
                ].append(ahl_player)

        for identity, stored_candidates in db_by_identity.items():
            ahl_candidates = ahl_by_identity.get(identity, [])
            if len(stored_candidates) == 1 and len(ahl_candidates) == 1:
                matches[stored_candidates[0].id] = ahl_candidates[0]

        return matches
