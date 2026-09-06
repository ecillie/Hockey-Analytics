"""Fetch current NHL rosters from the free NHL API."""

from __future__ import annotations

import logging

from app.ScriptingFiles.FullDataScript.roster_status.http_json_client import JsonHttpClient
from app.ScriptingFiles.FullDataScript.roster_status.roster_models import (
    ExternalRosterPlayer,
    FetchResult,
)


LOGGER = logging.getLogger(__name__)


class NhlRosterService:
    STANDINGS_URL = "https://api-web.nhle.com/v1/standings/now"
    ROSTER_URL = "https://api-web.nhle.com/v1/roster/{team}/current"

    def __init__(self, http_client: JsonHttpClient | None = None) -> None:
        self.http_client = http_client or JsonHttpClient()

    def fetch_current_rosters(self) -> FetchResult[dict[str, ExternalRosterPlayer]]:
        try:
            standings = self.http_client.get_json(self.STANDINGS_URL)
            teams = sorted(
                {
                    row.get("teamAbbrev", {}).get("default")
                    for row in standings.get("standings", [])
                    if row.get("teamAbbrev", {}).get("default")
                }
            )
        except Exception as exc:
            message = f"Unable to fetch NHL team list: {exc}"
            LOGGER.error(message)
            return FetchResult(items={}, complete=False, errors=(message,))

        if not teams:
            message = "NHL standings returned no teams"
            LOGGER.error(message)
            return FetchResult(items={}, complete=False, errors=(message,))

        players: dict[str, ExternalRosterPlayer] = {}
        errors: list[str] = []

        for team in teams:
            try:
                roster = self.http_client.get_json(self.ROSTER_URL.format(team=team))
                for group in ("forwards", "defensemen", "goalies"):
                    for row in roster.get(group, []):
                        player_id = row.get("id")
                        if player_id is None:
                            continue
                        first_name = row.get("firstName", {}).get("default", "")
                        last_name = row.get("lastName", {}).get("default", "")
                        players[str(player_id)] = ExternalRosterPlayer(
                            external_id=str(player_id),
                            full_name=f"{first_name} {last_name}".strip(),
                            team_external_id=team,
                        )
            except Exception as exc:
                message = f"Unable to fetch NHL roster for {team}: {exc}"
                LOGGER.error(message)
                errors.append(message)

        return FetchResult(
            items=players,
            complete=not errors,
            errors=tuple(errors),
        )
