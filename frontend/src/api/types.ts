import type { components, operations } from './generated'

type Schemas = components['schemas']

// Runtime API models come directly from FastAPI's generated OpenAPI schema.
// `npm run api:contract` fails when either the backend schema or this generated
// TypeScript contract is stale.
export type RosterStatus = Schemas['RosterStatus']
export type Position = Schemas['Position']
export type ApiErrorBody = Schemas['ErrorResponse']
export type Pagination = Schemas['Pagination']
export type TeamSummary = Schemas['TeamSummary']
export type Team = Schemas['Team']
export type PlayerIdentity = Schemas['PlayerIdentity']
export type PlayerSummary = Schemas['PlayerSummary']
export type TraditionalSkaterStats = Schemas['TraditionalSkaterStats']
export type AdvancedSkaterStats = Schemas['AdvancedSkaterStats']
export type GoalieStats = Schemas['GoalieStats']
export type PlayerStats = Schemas['PlayerStats']
export type SeasonHistoryRow = Schemas['SeasonHistoryRow']
export type HockeyValue = Schemas['HockeyValue']
export type HockeyValueHistoryPoint = Schemas['HockeyValueHistoryPoint']
export type ContractSeason = Schemas['ContractSeason']
export type Contract = Schemas['Contract']
export type TeamRosterResponse = Schemas['TeamRosterResponse']
export type TeamContractsResponse = Schemas['TeamContractsResponse']
export type TeamCap = Schemas['TeamCap']
export type SeasonInfo = Schemas['SeasonInfo']
export type SearchResponse = Schemas['SearchResponse']
export type OverviewResponse = Schemas['OverviewResponse']
export type CompareResponse = Schemas['CompareResponse']
export type HealthResponse = Schemas['HealthResponse']

export type PaginatedResponse<T> = Omit<Schemas['PaginatedPlayers'], 'data'> & {
  data: T[]
}

type GeneratedPlayerFilters = NonNullable<
  operations['players_api_players_get']['parameters']['query']
>
export type PlayerFilters = {
  [Key in keyof GeneratedPlayerFilters]: Exclude<GeneratedPlayerFilters[Key], null>
}
export type SortOrder = NonNullable<PlayerFilters['order']>
export type PlayerSort = NonNullable<PlayerFilters['sort']>

export interface ApiService {
  getHealth(signal?: AbortSignal): Promise<HealthResponse>
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
