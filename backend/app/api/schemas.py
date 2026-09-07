"""Response schemas shared by every TradeValue endpoint."""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RosterStatus(str, Enum):
    ACTIVE = "ACTIVE"
    MINORS = "MINORS"
    LTIR = "LTIR"
    UNKNOWN = "UNKNOWN"


class Position(str, Enum):
    C = "C"
    LW = "LW"
    RW = "RW"
    D = "D"
    G = "G"
    F = "F"


class TeamSummary(ApiModel):
    id: int
    nhlTeamId: int | None
    abbreviation: str
    name: str
    city: str | None
    active: bool


class Team(TeamSummary):
    rosterCounts: dict[RosterStatus, int]


class PlayerIdentity(ApiModel):
    id: int
    firstName: str
    lastName: str
    fullName: str
    birthDate: date | None
    age: int | None
    primaryPosition: Position | None
    shootsCatches: Literal["L", "R"] | None
    nationality: str | None
    active: bool
    rosterStatus: RosterStatus
    team: TeamSummary | None


class PlayerSummary(PlayerIdentity):
    season: int
    gamesPlayed: int | None
    goals: int | None
    assists: int | None
    points: int | None
    toiSeconds: int | None
    gameScore: float | None
    gameScorePer60: float | None
    hockeyValue: float | None
    projectedNextSeasonHockeyValue: float | None
    capHitCents: int | None


class TraditionalSkaterStats(ApiModel):
    gamesPlayed: int | None
    goals: int | None
    assists: int | None
    points: int | None
    plusMinus: int | None
    penaltyMinutes: int | None
    powerPlayGoals: int | None
    powerPlayPoints: int | None
    shortHandedGoals: int | None
    shots: int | None
    shootingPercentage: float | None


class AdvancedSkaterStats(ApiModel):
    situation: str
    iceTimeSeconds: int | None
    shifts: int | None
    gameScore: float | None
    gameScorePer60: float | None
    individualExpectedGoals: float | None
    expectedGoalsPer60: float | None
    onIceExpectedGoalsPercentage: float | None
    takeaways: int | None
    giveaways: int | None
    shotsBlocked: int | None
    penalties: int | None
    penaltiesDrawn: int | None


class GoalieStats(ApiModel):
    gamesPlayed: int | None
    wins: int | None
    losses: int | None
    overtimeLosses: int | None
    shotsAgainst: int | None
    saves: int | None
    savePercentage: float | None
    goalsAgainstAverage: float | None
    shutouts: int | None
    timeOnIceSeconds: int | None
    expectedGoalsAgainst: float | None
    goalsSavedAboveExpected: float | None


class PlayerStats(ApiModel):
    playerId: int
    season: int
    team: TeamSummary | None
    traditional: TraditionalSkaterStats | None
    advanced: AdvancedSkaterStats | None
    goalie: GoalieStats | None


class SeasonHistoryRow(ApiModel):
    season: int
    team: TeamSummary | None
    gamesPlayed: int | None
    goals: int | None
    assists: int | None
    points: int | None
    gameScorePer60: float | None
    hockeyValue: float | None


class HockeyValue(ApiModel):
    playerId: int
    season: int
    hockeyValue: float | None
    projectedNextSeasonHockeyValue: float | None
    gameScorePer60AboveReplacement: float | None
    toiHours: float | None
    modelVersion: str | None


class HockeyValueHistoryPoint(ApiModel):
    season: int
    hockeyValue: float | None


class ContractSeason(ApiModel):
    season: int
    owningTeam: TeamSummary | None
    baseSalaryCents: int | None
    signingBonusCents: int | None
    performanceBonusCents: int | None
    totalCashCents: int | None
    capHitCents: int
    capPercentage: float | None
    isSlide: bool


class Contract(ApiModel):
    id: int
    playerId: int
    signingTeam: TeamSummary | None
    signedOn: date | None
    startSeason: int
    endSeason: int
    termYears: int
    contractType: str | None
    expiryStatus: Literal["RFA", "UFA"] | None
    totalValueCents: int | None
    averageValueCents: int | None
    isEntryLevel: bool
    seasons: list[ContractSeason]


class Pagination(ApiModel):
    page: int
    pageSize: int
    totalItems: int
    totalPages: int


class PaginatedPlayers(ApiModel):
    data: list[PlayerSummary]
    pagination: Pagination


class TeamRosterResponse(ApiModel):
    team: TeamSummary
    season: int
    status: RosterStatus | None
    players: list[PlayerSummary]


class TeamContractRow(ApiModel):
    player: PlayerIdentity
    contract: Contract
    season: ContractSeason


class TeamContractsResponse(ApiModel):
    team: TeamSummary
    season: int
    contracts: list[TeamContractRow]


class TeamCap(ApiModel):
    teamId: int
    season: int
    salaryCapCents: int | None
    activeRosterCapCents: int
    ltirCapCents: int
    minorsCapCents: int
    totalCommitmentsCents: int
    capSpaceCents: int | None
    calculationStatus: Literal["ESTIMATE", "AUTHORITATIVE"]


class AvailableSeason(ApiModel):
    startYear: int
    endYear: int
    label: str
    salaryCapCents: int | None


class SeasonInfo(ApiModel):
    currentSeason: int
    availableSeasons: list[AvailableSeason]


class SearchResponse(ApiModel):
    players: list[PlayerIdentity]
    teams: list[TeamSummary]


class LeagueOverview(ApiModel):
    players: int
    goals: int
    gamesPlayed: int
    averageHockeyValue: float | None


class OverviewLeaders(ApiModel):
    hockeyValue: list[PlayerSummary]
    points: list[PlayerSummary]
    goals: list[PlayerSummary]
    gameScorePer60: list[PlayerSummary]


class OverviewResponse(ApiModel):
    season: int
    league: LeagueOverview
    leaders: OverviewLeaders


class CompareRow(ApiModel):
    player: PlayerIdentity
    stats: PlayerStats
    value: HockeyValue | None
    contract: Contract | None


class CompareResponse(ApiModel):
    season: int
    players: list[CompareRow]


class HealthResponse(ApiModel):
    status: Literal["ok"]


class ErrorDetail(ApiModel):
    code: str
    message: str
    details: dict[str, list[str]] | None = None


class ErrorResponse(ApiModel):
    error: ErrorDetail
