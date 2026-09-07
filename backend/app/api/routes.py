"""FastAPI route definitions matching docs/api-contract.md."""

from __future__ import annotations

from collections.abc import Generator
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy import text

from app.api import schemas
from app.api.service import ApiProblem, TradeValueService
from app.database import SessionLocal


router = APIRouter(prefix="/api")


def get_service() -> Generator[TradeValueService, None, None]:
    session = SessionLocal()
    try:
        yield TradeValueService(session)
    finally:
        session.close()


Service = Annotated[TradeValueService, Depends(get_service)]
PlayerId = Annotated[int, Path(gt=0)]
TeamId = Annotated[int, Path(gt=0)]
Season = Annotated[int, Query(ge=1900, le=2200)]


@router.get("/health", response_model=schemas.HealthResponse)
def health(service: Service):
    service.session.execute(text("SELECT 1"))
    return {"status": "ok"}


@router.get("/seasons", response_model=schemas.SeasonInfo)
def seasons(service: Service):
    return service.seasons()


@router.get("/players", response_model=schemas.PaginatedPlayers)
def players(
    service: Service,
    season: Season | None = None,
    team: Annotated[str | None, Query(min_length=2, max_length=4)] = None,
    position: schemas.Position | None = None,
    rosterStatus: schemas.RosterStatus | None = None,
    search: Annotated[str | None, Query(max_length=120)] = None,
    sort: Literal["name", "team", "gamesPlayed", "goals", "assists", "points", "gameScore", "gameScorePer60", "hockeyValue", "capHitCents"] = "hockeyValue",
    order: Literal["asc", "desc"] = "desc",
    page: Annotated[int, Query(ge=1)] = 1,
    pageSize: Annotated[int, Query(ge=1, le=100)] = 25,
):
    selected = season if season is not None else service.current_season()
    return service.players(selected, team, position.value if position else None, rosterStatus.value if rosterStatus else None, search, sort, order, page, pageSize)


@router.get("/players/compare", response_model=schemas.CompareResponse)
def compare_players(service: Service, ids: str, season: Season):
    try:
        player_ids = [int(value.strip()) for value in ids.split(",") if value.strip()]
    except ValueError as exc:
        raise ApiProblem(400, "INVALID_COMPARISON", "Player IDs must be integers.", {"ids": ["Use comma-separated integer IDs."]}) from exc
    if len(player_ids) < 2 or len(player_ids) > 4 or any(value <= 0 for value in player_ids) or len(set(player_ids)) != len(player_ids):
        raise ApiProblem(400, "INVALID_COMPARISON", "Select between 2 and 4 distinct players.", {"ids": ["Use 2 to 4 distinct positive IDs."]})
    return service.compare(player_ids, season)


@router.get("/players/{player_id}", response_model=schemas.PlayerIdentity)
def player(service: Service, player_id: PlayerId):
    return service.player_identity(player_id)


@router.get("/players/{player_id}/stats", response_model=schemas.PlayerStats)
def player_stats(service: Service, player_id: PlayerId, season: Season):
    return service.player_stats(player_id, season)


@router.get("/players/{player_id}/seasons", response_model=list[schemas.SeasonHistoryRow])
def player_seasons(service: Service, player_id: PlayerId):
    return service.player_seasons(player_id)


@router.get("/players/{player_id}/value/history", response_model=list[schemas.HockeyValueHistoryPoint])
def value_history(service: Service, player_id: PlayerId):
    return service.value_history(player_id)


@router.get("/players/{player_id}/value", response_model=schemas.HockeyValue)
def hockey_value(service: Service, player_id: PlayerId, season: Season | None = None):
    return service.hockey_value(player_id, season)


@router.get("/players/{player_id}/contract", response_model=schemas.Contract | None)
def contract(service: Service, player_id: PlayerId):
    return service.contract(player_id)


@router.get("/rankings/hockey-value", response_model=list[schemas.PlayerSummary])
def hockey_value_leaders(
    service: Service, season: Season,
    position: schemas.Position | None = None,
    team: Annotated[str | None, Query(min_length=2, max_length=4)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
):
    return service.leaders(season, position.value if position else None, team, limit)


@router.get("/teams", response_model=list[schemas.TeamSummary])
def teams(service: Service):
    return service.teams()


@router.get("/teams/{team_id}", response_model=schemas.Team)
def team(service: Service, team_id: TeamId):
    return service.team(team_id)


@router.get("/teams/{team_id}/roster", response_model=schemas.TeamRosterResponse)
def roster(service: Service, team_id: TeamId, season: Season, status: schemas.RosterStatus | None = None):
    return service.roster(team_id, season, status.value if status else None)


@router.get("/teams/{team_id}/contracts", response_model=schemas.TeamContractsResponse)
def team_contracts(service: Service, team_id: TeamId, season: Season):
    return service.team_contracts(team_id, season)


@router.get("/teams/{team_id}/cap", response_model=schemas.TeamCap)
def team_cap(service: Service, team_id: TeamId, season: Season):
    return service.team_cap(team_id, season)


@router.get("/search", response_model=schemas.SearchResponse)
def search(
    service: Service,
    q: Annotated[str, Query(min_length=2, max_length=120)],
    types: str = "player,team",
    limit: Annotated[int, Query(ge=1, le=20)] = 8,
):
    requested = [value.strip() for value in types.split(",") if value.strip()]
    invalid = sorted(set(requested) - {"player", "team"})
    if not requested or invalid:
        raise ApiProblem(400, "INVALID_SEARCH_TYPES", "Search types must be player or team.", {"types": ["Use player, team, or both."]})
    return service.search(q, requested, limit)


@router.get("/overview", response_model=schemas.OverviewResponse)
def overview(service: Service, season: Season):
    return service.overview(season)
