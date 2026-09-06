"""Fetch current AHL rosters from the public HockeyTech LeagueStat feed."""

from __future__ import annotations

from datetime import date
import logging
import os

from app.ScriptingFiles.FullDataScript.roster_status.http_json_client import JsonHttpClient
from app.ScriptingFiles.FullDataScript.roster_status.roster_models import (
    ExternalRosterPlayer,
    FetchResult,
)


LOGGER = logging.getLogger(__name__)


class AhlRosterService:
    FEED_URL = "https://lscluster.hockeytech.com/feed/index.php"
    # This key is published by the AHL LeagueStat web client. It is not a secret.
    DEFAULT_PUBLIC_KEY = "ccb91f29d6744675"

    def __init__(
        self,
        http_client: JsonHttpClient | None = None,
        feed_key: str | None = None,
        season_id: str | None = None,
    ) -> None:
        self.http_client = http_client or JsonHttpClient()
        self.feed_key = feed_key or os.getenv("AHL_FEED_KEY", self.DEFAULT_PUBLIC_KEY)
        self.season_id = season_id or os.getenv("AHL_SEASON_ID")

    def _base_params(self) -> dict[str, str]:
        return {
            "feed": "statviewfeed",
            "key": self.feed_key,
            "client_code": "ahl",
            "site_id": "0",
            "lang": "en",
            "callback": "JSON_CALLBACK",
        }

    def fetch_current_rosters(self) -> FetchResult[list[ExternalRosterPlayer]]:
        try:
            bootstrap_params = self._base_params()
            bootstrap_params.update(
                {
                    "view": "bootstrap",
                    "season": self.season_id or "latest",
                    "pageName": "roster",
                    "league_id": "4",
                }
            )
            bootstrap = self.http_client.get_json(self.FEED_URL, bootstrap_params)
            season_id = self.season_id or str(bootstrap["current_season_id"])
            league_id = str(bootstrap.get("current_league_id", "4"))
            teams = [
                team
                for team in bootstrap.get("teamsNoAll", [])
                if str(team.get("id", "")) not in {"", "-1"}
            ]
        except Exception as exc:
            message = f"Unable to bootstrap AHL roster feed: {exc}"
            LOGGER.error(message)
            return FetchResult(items=[], complete=False, errors=(message,))

        if not teams:
            message = "AHL roster bootstrap returned no teams"
            LOGGER.error(message)
            return FetchResult(items=[], complete=False, errors=(message,))

        players_by_id: dict[str, ExternalRosterPlayer] = {}
        errors: list[str] = []

        for team in teams:
            team_id = str(team["id"])
            try:
                params = self._base_params()
                params.update(
                    {
                        "view": "roster",
                        "team_id": team_id,
                        "season_id": season_id,
                        "league_id": league_id,
                    }
                )
                payload = self.http_client.get_json(self.FEED_URL, params)
                for roster_group in payload.get("roster", []):
                    for section in roster_group.get("sections", []):
                        for entry in section.get("data", []):
                            row = entry.get("row", {})
                            player_id = row.get("player_id")
                            name = row.get("name")
                            if not player_id or not name:
                                continue
                            players_by_id[str(player_id)] = ExternalRosterPlayer(
                                external_id=str(player_id),
                                full_name=str(name),
                                birth_date=self._parse_date(row.get("birthdate")),
                                team_external_id=team_id,
                            )
            except Exception as exc:
                message = f"Unable to fetch AHL roster for team {team_id}: {exc}"
                LOGGER.error(message)
                errors.append(message)

        return FetchResult(
            items=list(players_by_id.values()),
            complete=not errors,
            errors=tuple(errors),
        )

    @staticmethod
    def _parse_date(value: object) -> date | None:
        if not value:
            return None
        try:
            return date.fromisoformat(str(value))
        except ValueError:
            return None
