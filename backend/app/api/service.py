"""Database-backed application service for the public API."""

from __future__ import annotations

from math import ceil
from typing import Any, Iterable

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.queries import (
    CONTRACT_SEASONS_SQL,
    CONTRACT_SQL,
    PLAYER_IDENTITY_SQL,
    SUMMARY_CTES,
    TEAM_SQL,
)


class ApiProblem(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        details: dict[str, list[str]] | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details


def _team(row: Any, prefix: str = "") -> dict[str, Any] | None:
    team_id = row.get(f"{prefix}team_id")
    if team_id is None:
        return None
    return {
        "id": team_id,
        "nhlTeamId": row.get(f"{prefix}nhl_team_id"),
        "abbreviation": row.get(f"{prefix}abbreviation"),
        "name": row.get(f"{prefix}team_name"),
        "city": row.get(f"{prefix}team_city"),
        "active": row.get(f"{prefix}team_active"),
    }


def _identity(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "firstName": row["first_name"],
        "lastName": row["last_name"],
        "fullName": row["full_name"],
        "birthDate": row["birth_date"],
        "age": row["age"],
        "primaryPosition": row["primary_position"],
        "shootsCatches": row["shoots_catches"],
        "nationality": row["nationality"],
        "active": row["active"],
        "rosterStatus": row["roster_status"],
        "team": _team(row),
    }


def _summary(row: Any) -> dict[str, Any]:
    return {
        **_identity(row),
        "season": row["season"],
        "gamesPlayed": row["games_played"],
        "goals": row["goals"],
        "assists": row["assists"],
        "points": row["points"],
        "toiSeconds": round(row["ice_time_seconds"]) if row["ice_time_seconds"] is not None else None,
        "gameScore": row["game_score"],
        "gameScorePer60": row["game_score_per_60"],
        "hockeyValue": row["hockey_value"],
        "projectedNextSeasonHockeyValue": row["projected_hockey_value"],
        "capHitCents": row["cap_hit_cents"],
    }


class TradeValueService:
    SORT_COLUMNS = {
        "name": "full_name",
        "team": "abbreviation",
        "gamesPlayed": "games_played",
        "goals": "goals",
        "assists": "assists",
        "points": "points",
        "gameScore": "game_score",
        "gameScorePer60": "game_score_per_60",
        "hockeyValue": "hockey_value",
        "capHitCents": "cap_hit_cents",
    }

    def __init__(self, session: Session):
        self.session = session

    def _one(self, sql: str, params: dict[str, Any]) -> Any | None:
        return self.session.execute(text(sql), params).mappings().first()

    def _all(self, sql: str, params: dict[str, Any] | None = None) -> list[Any]:
        return list(self.session.execute(text(sql), params or {}).mappings())

    def current_season(self) -> int:
        value = self.session.execute(
            text("""SELECT MAX(start_year) FROM seasons
                    WHERE start_year <= EXTRACT(YEAR FROM CURRENT_DATE)
                        - CASE WHEN EXTRACT(MONTH FROM CURRENT_DATE) < 7 THEN 1 ELSE 0 END""")
        ).scalar_one_or_none()
        if value is None:
            raise ApiProblem(503, "SEASONS_UNAVAILABLE", "No seasons are configured.")
        return int(value)

    def require_season(self, season: int) -> None:
        exists = self.session.execute(
            text("SELECT EXISTS(SELECT 1 FROM seasons WHERE start_year = :season)"),
            {"season": season},
        ).scalar_one()
        if not exists:
            raise ApiProblem(400, "INVALID_SEASON", "The requested season is not available.", {"season": ["Unknown season."]})

    def seasons(self) -> dict[str, Any]:
        rows = self._all(
            "SELECT start_year, end_year, label, salary_cap_cents FROM seasons ORDER BY start_year"
        )
        return {
            "currentSeason": self.current_season(),
            "availableSeasons": [
                {"startYear": r["start_year"], "endYear": r["end_year"], "label": r["label"], "salaryCapCents": r["salary_cap_cents"]}
                for r in rows
            ],
        }

    def player_identity(self, player_id: int) -> dict[str, Any]:
        row = self._one(PLAYER_IDENTITY_SQL, {"player_id": player_id})
        if row is None:
            raise ApiProblem(404, "PLAYER_NOT_FOUND", "Player not found.")
        return _identity(row)

    def team_summary(self, team_id: int) -> dict[str, Any]:
        row = self._one(TEAM_SQL, {"team_id": team_id})
        if row is None:
            raise ApiProblem(404, "TEAM_NOT_FOUND", "Team not found.")
        return {
            "id": row["id"], "nhlTeamId": row["nhl_team_id"],
            "abbreviation": row["abbreviation"], "name": row["team_name"],
            "city": row["team_city"], "active": row["team_active"],
        }

    def _summary_rows(
        self,
        season: int,
        where: str = "TRUE",
        params: dict[str, Any] | None = None,
        order: str = "id ASC",
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[Any]:
        query = SUMMARY_CTES + f" SELECT * FROM summary WHERE {where} ORDER BY {order}"
        bind = {"season": season, **(params or {})}
        if limit is not None:
            query += " LIMIT :_limit"
            bind["_limit"] = limit
        if offset is not None:
            query += " OFFSET :_offset"
            bind["_offset"] = offset
        return self._all(query, bind)

    def summary_for_player(self, player_id: int, season: int) -> Any | None:
        rows = self._summary_rows(season, "id = :player_id", {"player_id": player_id})
        return rows[0] if rows else None

    def players(
        self, season: int, team: str | None, position: str | None,
        roster_status: str | None, search: str | None, sort: str,
        order: str, page: int, page_size: int,
    ) -> dict[str, Any]:
        self.require_season(season)
        clauses = ["(games_played IS NOT NULL OR team_id IS NOT NULL OR cap_hit_cents IS NOT NULL)"]
        params: dict[str, Any] = {}
        if team:
            clauses.append("UPPER(abbreviation) = UPPER(:team)")
            params["team"] = team
        if position:
            clauses.append("primary_position = :position")
            params["position"] = position
        if roster_status:
            clauses.append("roster_status = :roster_status")
            params["roster_status"] = roster_status
        if search:
            clauses.append("full_name ILIKE :search")
            params["search"] = f"%{search.strip()}%"
        where = " AND ".join(clauses)
        count_sql = SUMMARY_CTES + f" SELECT COUNT(*) FROM summary WHERE {where}"
        total = int(self.session.execute(text(count_sql), {"season": season, **params}).scalar_one())
        column = self.SORT_COLUMNS[sort]
        direction = "ASC" if order == "asc" else "DESC"
        rows = self._summary_rows(
            season, where, params, f"{column} {direction} NULLS LAST, id ASC",
            page_size, (page - 1) * page_size,
        )
        return {
            "data": [_summary(r) for r in rows],
            "pagination": {"page": page, "pageSize": page_size, "totalItems": total, "totalPages": ceil(total / page_size)},
        }

    def teams(self) -> list[dict[str, Any]]:
        rows = self._all(
            "SELECT id, nhl_team_id, abbreviation, name team_name, city team_city, active team_active FROM teams WHERE active ORDER BY name, id"
        )
        return [
            {"id": r["id"], "nhlTeamId": r["nhl_team_id"], "abbreviation": r["abbreviation"], "name": r["team_name"], "city": r["team_city"], "active": r["team_active"]}
            for r in rows
        ]

    def team(self, team_id: int) -> dict[str, Any]:
        team = self.team_summary(team_id)
        rows = self._all(
            """SELECT p.roster_status::text roster_status, COUNT(*) count
               FROM players p JOIN LATERAL (
                 SELECT team_id FROM player_team_stints pts WHERE pts.player_id = p.id
                 ORDER BY season_start_year DESC, (departed_on IS NULL) DESC,
                          departed_on DESC NULLS LAST, pts.id DESC LIMIT 1
               ) stint ON true WHERE stint.team_id = :team_id GROUP BY p.roster_status""",
            {"team_id": team_id},
        )
        counts = {status: 0 for status in ("ACTIVE", "MINORS", "LTIR", "UNKNOWN")}
        counts.update({r["roster_status"]: r["count"] for r in rows})
        return {**team, "rosterCounts": counts}

    def roster(self, team_id: int, season: int, status: str | None) -> dict[str, Any]:
        self.require_season(season)
        team = self.team_summary(team_id)
        where = "team_id = :team_id"
        params: dict[str, Any] = {"team_id": team_id}
        if status:
            where += " AND roster_status = :status"
            params["status"] = status
        rows = self._summary_rows(season, where, params, "full_name ASC, id ASC", 100)
        return {"team": team, "season": season, "status": status, "players": [_summary(r) for r in rows]}

    def player_stats(self, player_id: int, season: int) -> dict[str, Any]:
        self.require_season(season)
        self.player_identity(player_id)
        row = self.summary_for_player(player_id, season)
        if row is None:
            raise ApiProblem(404, "PLAYER_NOT_FOUND", "Player not found.")
        traditional = None
        advanced = None
        if row["primary_position"] != "G":
            if row["games_played"] is not None:
                traditional = {
                    "gamesPlayed": row["games_played"], "goals": row["goals"], "assists": row["assists"], "points": row["points"],
                    "plusMinus": row["plus_minus"], "penaltyMinutes": row["penalty_minutes"], "powerPlayGoals": row["power_play_goals"],
                    "powerPlayPoints": row["power_play_points"], "shortHandedGoals": row["short_handed_goals"], "shots": row["shots"],
                    "shootingPercentage": row["shooting_percentage"],
                }
            if row["ice_time_seconds"] is not None:
                advanced = {
                    "situation": "all", "iceTimeSeconds": round(row["ice_time_seconds"]), "shifts": row["shifts"],
                    "gameScore": row["game_score"], "gameScorePer60": row["game_score_per_60"],
                    "individualExpectedGoals": row["individual_expected_goals"], "expectedGoalsPer60": row["expected_goals_per_60"],
                    "onIceExpectedGoalsPercentage": row["on_ice_expected_goals_pct"], "takeaways": row["takeaways"],
                    "giveaways": row["giveaways"], "shotsBlocked": row["shots_blocked"], "penalties": row["penalties"],
                    "penaltiesDrawn": row["penalties_drawn"],
                }
        goalie = self._goalie_stats(player_id, season) if row["primary_position"] == "G" else None
        return {"playerId": player_id, "season": season, "team": _team(row), "traditional": traditional, "advanced": advanced, "goalie": goalie}

    def _goalie_stats(self, player_id: int, season: int) -> dict[str, Any] | None:
        sql = r"""
        WITH basic AS (
          SELECT SUM(g.games_played)::int games_played, SUM(g.wins)::int wins,
            SUM(g.losses)::int losses, SUM(g.overtime_losses)::int overtime_losses,
            SUM(g.shots_against)::int shots_against, SUM(g.saves)::int saves,
            CASE WHEN SUM(g.shots_against) > 0 THEN SUM(g.saves)::float / SUM(g.shots_against) END save_percentage,
            SUM(g.goals_against)::int goals_against, SUM(g.time_on_ice_seconds)::int time_on_ice_seconds,
            CASE WHEN SUM(g.time_on_ice_seconds) > 0 THEN SUM(g.goals_against) * 3600.0 / SUM(g.time_on_ice_seconds) END gaa,
            SUM(g.shutouts)::int shutouts
          FROM goalie_season_stats g WHERE g.player_id=:player_id AND g.season_start_year=:season AND g.game_type=2
            AND (g.stat_scope='TOTAL' OR NOT EXISTS (SELECT 1 FROM goalie_season_stats x WHERE x.player_id=g.player_id AND x.season_start_year=g.season_start_year AND x.game_type=2 AND x.stat_scope='TOTAL'))
        ), advanced AS (
          SELECT SUM(a.expected_goals_against)::float xga, SUM(a.goals_against)::float ga
          FROM goalie_advanced_season_stats a WHERE a.player_id=:player_id AND a.season_start_year=:season AND a.game_type=2 AND a.situation='all'
            AND (a.stat_scope='TOTAL' OR NOT EXISTS (SELECT 1 FROM goalie_advanced_season_stats x WHERE x.player_id=a.player_id AND x.season_start_year=a.season_start_year AND x.game_type=2 AND x.situation=a.situation AND x.stat_scope='TOTAL'))
        ) SELECT *, CASE WHEN xga IS NOT NULL AND ga IS NOT NULL THEN xga-ga END gsae FROM basic CROSS JOIN advanced
        """
        row = self._one(sql, {"player_id": player_id, "season": season})
        if row is None or row["games_played"] is None:
            return None
        return {"gamesPlayed": row["games_played"], "wins": row["wins"], "losses": row["losses"], "overtimeLosses": row["overtime_losses"],
                "shotsAgainst": row["shots_against"], "saves": row["saves"], "savePercentage": row["save_percentage"],
                "goalsAgainstAverage": row["gaa"], "shutouts": row["shutouts"], "timeOnIceSeconds": row["time_on_ice_seconds"],
                "expectedGoalsAgainst": row["xga"], "goalsSavedAboveExpected": row["gsae"]}

    def hockey_value(self, player_id: int, season: int | None) -> dict[str, Any]:
        season = season if season is not None else self.current_season()
        self.require_season(season)
        self.player_identity(player_id)
        row = self.summary_for_player(player_id, season)
        return {"playerId": player_id, "season": season,
                "hockeyValue": row["hockey_value"] if row else None,
                "projectedNextSeasonHockeyValue": row["projected_hockey_value"] if row else None,
                "gameScorePer60AboveReplacement": row["gs60_above_replacement"] if row else None,
                "toiHours": row["ice_time_seconds"] / 3600.0 if row and row["ice_time_seconds"] is not None else None,
                "modelVersion": row["model_version"] if row else None}

    def player_seasons(self, player_id: int) -> list[dict[str, Any]]:
        self.player_identity(player_id)
        seasons = [int(r["season"]) for r in self._all(
            """SELECT DISTINCT season_start_year season FROM (
                 SELECT season_start_year FROM skater_season_stats WHERE player_id=:player_id AND game_type=2
                 UNION SELECT season_start_year FROM goalie_season_stats WHERE player_id=:player_id AND game_type=2
               ) history ORDER BY season DESC LIMIT 40""", {"player_id": player_id})]
        result = []
        for season in seasons:
            row = self.summary_for_player(player_id, season)
            if row:
                result.append({"season": season, "team": _team(row), "gamesPlayed": row["games_played"], "goals": row["goals"],
                               "assists": row["assists"], "points": row["points"], "gameScorePer60": row["game_score_per_60"],
                               "hockeyValue": row["hockey_value"]})
        return result

    def value_history(self, player_id: int) -> list[dict[str, Any]]:
        return [{"season": row["season"], "hockeyValue": row["hockeyValue"]} for row in self.player_seasons(player_id)]

    def leaders(self, season: int, position: str | None, team: str | None, limit: int) -> list[dict[str, Any]]:
        self.require_season(season)
        clauses = ["hockey_value IS NOT NULL"]
        params: dict[str, Any] = {}
        if position:
            clauses.append("primary_position=:position"); params["position"] = position
        if team:
            clauses.append("UPPER(abbreviation)=UPPER(:team)"); params["team"] = team
        rows = self._summary_rows(season, " AND ".join(clauses), params, "hockey_value DESC NULLS LAST, id ASC", limit)
        return [_summary(r) for r in rows]

    def contract(self, player_id: int, current_season: int | None = None) -> dict[str, Any] | None:
        self.player_identity(player_id)
        current_season = current_season if current_season is not None else self.current_season()
        row = self._one(CONTRACT_SQL, {"player_id": player_id, "current_season": current_season})
        if row is None:
            return None
        signing_team = None
        if row["signing_team_id"] is not None:
            signing_team = {"id": row["signing_team_id"], "nhlTeamId": row["signing_nhl_team_id"], "abbreviation": row["signing_abbreviation"],
                            "name": row["signing_team_name"], "city": row["signing_team_city"], "active": row["signing_team_active"]}
        seasons = [self._contract_season(r) for r in self._all(CONTRACT_SEASONS_SQL, {"contract_id": row["id"]})]
        return {"id": row["id"], "playerId": row["player_id"], "signingTeam": signing_team, "signedOn": row["signed_on"],
                "startSeason": row["start_season"], "endSeason": row["end_season"], "termYears": row["term_years"],
                "contractType": row["contract_type"], "expiryStatus": row["expiry_status"], "totalValueCents": row["total_value_cents"],
                "averageValueCents": row["average_value_cents"], "isEntryLevel": row["is_entry_level"], "seasons": seasons}

    @staticmethod
    def _contract_season(row: Any) -> dict[str, Any]:
        return {"season": row["season_start_year"], "owningTeam": _team(row), "baseSalaryCents": row["base_salary_cents"],
                "signingBonusCents": row["signing_bonus_cents"], "performanceBonusCents": row["performance_bonus_cents"],
                "totalCashCents": row["total_cash_cents"], "capHitCents": row["cap_hit_cents"],
                "capPercentage": float(row["cap_percentage"]) if row["cap_percentage"] is not None else None, "isSlide": row["is_slide"]}

    def team_contracts(self, team_id: int, season: int) -> dict[str, Any]:
        self.require_season(season); team = self.team_summary(team_id)
        ids = self._all("""SELECT c.player_id FROM contracts c JOIN contract_seasons cs ON cs.contract_id=c.id
                           WHERE cs.owning_team_id=:team_id AND cs.season_start_year=:season ORDER BY c.player_id""",
                        {"team_id": team_id, "season": season})
        rows = []
        for item in ids:
            contract = self.contract(item["player_id"], season)
            if contract:
                contract_season = next((s for s in contract["seasons"] if s["season"] == season and s["owningTeam"] and s["owningTeam"]["id"] == team_id), None)
                if contract_season:
                    rows.append({"player": self.player_identity(item["player_id"]), "contract": contract, "season": contract_season})
        return {"team": team, "season": season, "contracts": rows}

    def team_cap(self, team_id: int, season: int) -> dict[str, Any]:
        self.require_season(season); self.team_summary(team_id)
        row = self._one("""SELECT s.salary_cap_cents,
             COALESCE(SUM(cs.cap_hit_cents) FILTER (WHERE p.roster_status='ACTIVE'),0)::bigint active_cap,
             COALESCE(SUM(cs.cap_hit_cents) FILTER (WHERE p.roster_status='LTIR'),0)::bigint ltir_cap,
             COALESCE(SUM(cs.cap_hit_cents) FILTER (WHERE p.roster_status='MINORS'),0)::bigint minors_cap,
             COALESCE(SUM(cs.cap_hit_cents),0)::bigint total_cap
           FROM seasons s LEFT JOIN contract_seasons cs ON cs.season_start_year=s.start_year AND cs.owning_team_id=:team_id
           LEFT JOIN contracts c ON c.id=cs.contract_id LEFT JOIN players p ON p.id=c.player_id
           WHERE s.start_year=:season GROUP BY s.salary_cap_cents""", {"team_id": team_id, "season": season})
        ceiling = row["salary_cap_cents"]
        return {"teamId": team_id, "season": season, "salaryCapCents": ceiling, "activeRosterCapCents": row["active_cap"],
                "ltirCapCents": row["ltir_cap"], "minorsCapCents": row["minors_cap"], "totalCommitmentsCents": row["total_cap"],
                "capSpaceCents": ceiling - row["active_cap"] if ceiling is not None else None, "calculationStatus": "ESTIMATE"}

    def search(self, query: str, types: Iterable[str], limit: int) -> dict[str, Any]:
        q = f"%{query.strip()}%"; requested = set(types)
        players: list[dict[str, Any]] = []
        teams: list[dict[str, Any]] = []
        if "player" in requested:
            ids = self._all("SELECT id FROM players WHERE CONCAT_WS(' ', first_name, last_name) ILIKE :q ORDER BY active DESC, last_name, first_name, id LIMIT :limit", {"q": q, "limit": limit})
            players = [self.player_identity(r["id"]) for r in ids]
        if "team" in requested:
            rows = self._all("""SELECT id, nhl_team_id, abbreviation, name team_name, city team_city, active team_active FROM teams
                              WHERE CONCAT_WS(' ', city, name, abbreviation) ILIKE :q ORDER BY active DESC, name, id LIMIT :limit""", {"q": q, "limit": limit})
            teams = [{"id": r["id"], "nhlTeamId": r["nhl_team_id"], "abbreviation": r["abbreviation"], "name": r["team_name"], "city": r["team_city"], "active": r["team_active"]} for r in rows]
        return {"players": players, "teams": teams}

    def overview(self, season: int) -> dict[str, Any]:
        self.require_season(season)
        rows = self._summary_rows(season, "games_played IS NOT NULL", order="id ASC")
        summaries = [_summary(r) for r in rows]
        skaters = [s for s in summaries if s["primaryPosition"] != "G"]
        values = [s["hockeyValue"] for s in skaters if s["hockeyValue"] is not None]
        def top(field: str) -> list[dict[str, Any]]:
            return sorted((s for s in skaters if s[field] is not None), key=lambda s: (-s[field], s["id"]))[:5]
        return {"season": season, "league": {"players": len(summaries), "goals": sum(s["goals"] or 0 for s in skaters),
                "gamesPlayed": sum(s["gamesPlayed"] or 0 for s in summaries), "averageHockeyValue": sum(values) / len(values) if values else None},
                "leaders": {"hockeyValue": top("hockeyValue"), "points": top("points"), "goals": top("goals"), "gameScorePer60": top("gameScorePer60")}}

    def compare(self, ids: list[int], season: int) -> dict[str, Any]:
        self.require_season(season)
        return {"season": season, "players": [{"player": self.player_identity(player_id), "stats": self.player_stats(player_id, season),
                 "value": self.hockey_value(player_id, season), "contract": self.contract(player_id, season)} for player_id in ids]}
