export type RosterStatus = 'ACTIVE' | 'MINORS' | 'LTIR' | 'UNKNOWN'
export type Position = 'C' | 'LW' | 'RW' | 'D' | 'G' | 'F'
export type SortOrder = 'asc' | 'desc'
export type PlayerSort = 'name' | 'team' | 'gamesPlayed' | 'goals' | 'assists' | 'points' | 'gameScore' | 'gameScorePer60' | 'hockeyValue' | 'capHitCents'

export interface ApiErrorBody {
  error: { code: string; message: string; details?: Record<string, string[]> }
}

export interface Pagination {
  page: number
  pageSize: number
  totalItems: number
  totalPages: number
}

export interface PaginatedResponse<T> {
  data: T[]
  pagination: Pagination
}

export interface TeamSummary {
  id: number
  nhlTeamId: number | null
  abbreviation: string
  name: string
  city: string | null
  active: boolean
}

export interface Team extends TeamSummary {
  rosterCounts: Record<RosterStatus, number>
}

export interface PlayerIdentity {
  id: number
  firstName: string
  lastName: string
  fullName: string
  birthDate: string | null
  age: number | null
  primaryPosition: Position | null
  shootsCatches: 'L' | 'R' | null
  nationality: string | null
  active: boolean
  rosterStatus: RosterStatus
  team: TeamSummary | null
}

export interface PlayerSummary extends PlayerIdentity {
  season: number
  gamesPlayed: number | null
  goals: number | null
  assists: number | null
  points: number | null
  toiSeconds: number | null
  gameScore: number | null
  gameScorePer60: number | null
  hockeyValue: number | null
  projectedNextSeasonHockeyValue: number | null
  capHitCents: number | null
}

export interface TraditionalSkaterStats {
  gamesPlayed: number | null
  goals: number | null
  assists: number | null
  points: number | null
  plusMinus: number | null
  penaltyMinutes: number | null
  powerPlayGoals: number | null
  powerPlayPoints: number | null
  shortHandedGoals: number | null
  shots: number | null
  shootingPercentage: number | null
}

export interface AdvancedSkaterStats {
  situation: string
  iceTimeSeconds: number | null
  shifts: number | null
  gameScore: number | null
  gameScorePer60: number | null
  individualExpectedGoals: number | null
  expectedGoalsPer60: number | null
  onIceExpectedGoalsPercentage: number | null
  takeaways: number | null
  giveaways: number | null
  shotsBlocked: number | null
  penalties: number | null
  penaltiesDrawn: number | null
}

export interface GoalieStats {
  gamesPlayed: number | null
  wins: number | null
  losses: number | null
  overtimeLosses: number | null
  shotsAgainst: number | null
  saves: number | null
  savePercentage: number | null
  goalsAgainstAverage: number | null
  shutouts: number | null
  timeOnIceSeconds: number | null
  expectedGoalsAgainst: number | null
  goalsSavedAboveExpected: number | null
}

export interface PlayerStats {
  playerId: number
  season: number
  team: TeamSummary | null
  traditional: TraditionalSkaterStats | null
  advanced: AdvancedSkaterStats | null
  goalie: GoalieStats | null
}

export interface SeasonHistoryRow {
  season: number
  team: TeamSummary | null
  gamesPlayed: number | null
  goals: number | null
  assists: number | null
  points: number | null
  gameScorePer60: number | null
  hockeyValue: number | null
}

export interface HockeyValue {
  playerId: number
  season: number
  hockeyValue: number | null
  projectedNextSeasonHockeyValue: number | null
  gameScorePer60AboveReplacement: number | null
  toiHours: number | null
  modelVersion: string | null
}

export interface HockeyValueHistoryPoint {
  season: number
  hockeyValue: number | null
}

export interface ContractSeason {
  season: number
  owningTeam: TeamSummary | null
  baseSalaryCents: number | null
  signingBonusCents: number | null
  performanceBonusCents: number | null
  totalCashCents: number | null
  capHitCents: number
  capPercentage: number | null
  isSlide: boolean
}

export interface Contract {
  id: number
  playerId: number
  signingTeam: TeamSummary | null
  signedOn: string | null
  startSeason: number
  endSeason: number
  termYears: number
  contractType: string | null
  expiryStatus: 'RFA' | 'UFA' | null
  totalValueCents: number | null
  averageValueCents: number | null
  isEntryLevel: boolean
  seasons: ContractSeason[]
}

export interface TeamRosterResponse {
  team: TeamSummary
  season: number
  status: RosterStatus | null
  players: PlayerSummary[]
}

export interface TeamContractsResponse {
  team: TeamSummary
  season: number
  contracts: Array<{ player: PlayerIdentity; contract: Contract; season: ContractSeason }>
}

export interface TeamCap {
  teamId: number
  season: number
  salaryCapCents: number | null
  activeRosterCapCents: number
  ltirCapCents: number
  minorsCapCents: number
  totalCommitmentsCents: number
  capSpaceCents: number | null
  calculationStatus: 'ESTIMATE' | 'AUTHORITATIVE'
}

export interface SeasonInfo {
  currentSeason: number
  availableSeasons: Array<{ startYear: number; endYear: number; label: string; salaryCapCents: number | null }>
}

export interface PlayerFilters {
  season?: number
  team?: string
  position?: Position
  rosterStatus?: RosterStatus
  search?: string
  sort?: PlayerSort
  order?: SortOrder
  page?: number
  pageSize?: number
}

export interface SearchResponse {
  players: PlayerIdentity[]
  teams: TeamSummary[]
}

export interface OverviewResponse {
  season: number
  league: { players: number; goals: number; gamesPlayed: number; averageHockeyValue: number | null }
  leaders: {
    hockeyValue: PlayerSummary[]
    points: PlayerSummary[]
    goals: PlayerSummary[]
    gameScorePer60: PlayerSummary[]
  }
}

export interface CompareResponse {
  season: number
  players: Array<{
    player: PlayerIdentity
    stats: PlayerStats
    value: HockeyValue | null
    contract: Contract | null
  }>
}

export interface ApiService {
  getHealth(signal?: AbortSignal): Promise<{ status: 'ok' }>
  getSeasons(signal?: AbortSignal): Promise<SeasonInfo>
  getOverview(season: number, signal?: AbortSignal): Promise<OverviewResponse>
  getPlayers(params?: PlayerFilters, signal?: AbortSignal): Promise<PaginatedResponse<PlayerSummary>>
  getPlayer(playerId: number, signal?: AbortSignal): Promise<PlayerIdentity>
  getPlayerStats(playerId: number, season: number, signal?: AbortSignal): Promise<PlayerStats>
  getPlayerSeasons(playerId: number, signal?: AbortSignal): Promise<SeasonHistoryRow[]>
  getPlayerValue(playerId: number, season?: number, signal?: AbortSignal): Promise<HockeyValue>
  getPlayerValueHistory(playerId: number, signal?: AbortSignal): Promise<HockeyValueHistoryPoint[]>
  getHockeyValueLeaders(params: Pick<PlayerFilters, 'season' | 'position' | 'team'> & { limit?: number }, signal?: AbortSignal): Promise<PlayerSummary[]>
  getPlayerContract(playerId: number, signal?: AbortSignal): Promise<Contract | null>
  getTeams(signal?: AbortSignal): Promise<TeamSummary[]>
  getTeam(teamId: number, signal?: AbortSignal): Promise<Team>
  getTeamRoster(teamId: number, params: { season: number; status?: RosterStatus }, signal?: AbortSignal): Promise<TeamRosterResponse>
  getTeamContracts(teamId: number, season: number, signal?: AbortSignal): Promise<TeamContractsResponse>
  getTeamCap(teamId: number, season: number, signal?: AbortSignal): Promise<TeamCap>
  search(query: string, types?: Array<'player' | 'team'>, limit?: number, signal?: AbortSignal): Promise<SearchResponse>
  comparePlayers(ids: number[], season: number, signal?: AbortSignal): Promise<CompareResponse>
}
