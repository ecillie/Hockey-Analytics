import type { components, paths } from './generated'

type GetPath = {
  [Path in keyof paths]: paths[Path]['get'] extends never ? never : Path
}[keyof paths]

export const API_GET_PATHS = [
  '/api/health',
  '/api/overview',
  '/api/players',
  '/api/players/compare',
  '/api/players/{player_id}',
  '/api/players/{player_id}/contract',
  '/api/players/{player_id}/seasons',
  '/api/players/{player_id}/stats',
  '/api/players/{player_id}/value',
  '/api/players/{player_id}/value/history',
  '/api/rankings/hockey-value',
  '/api/search',
  '/api/seasons',
  '/api/teams',
  '/api/teams/{team_id}',
  '/api/teams/{team_id}/cap',
  '/api/teams/{team_id}/contracts',
  '/api/teams/{team_id}/roster',
] as const satisfies readonly GetPath[]

type Assert<T extends true> = T
type MissingBackendPath = Exclude<GetPath, (typeof API_GET_PATHS)[number]>
type Schemas = components['schemas']
type GetResponse<Path extends GetPath> = paths[Path]['get'] extends {
  responses: { 200: { content: { 'application/json': infer Body } } }
} ? Body : never
type Equal<Left, Right> =
  (<Value>() => Value extends Left ? 1 : 2) extends
  (<Value>() => Value extends Right ? 1 : 2)
    ? (<Value>() => Value extends Right ? 1 : 2) extends
      (<Value>() => Value extends Left ? 1 : 2)
        ? true
        : false
    : false

// Compilation fails when FastAPI adds a GET endpoint without a frontend
// contract entry. The `satisfies` clause catches removed or renamed endpoints.
export type EveryBackendGetPathIsCovered = Assert<
  [MissingBackendPath] extends [never] ? true : false
>

// These checks bind each frontend call to the response model declared on its
// FastAPI route. A route returning the wrong named model fails `tsc` even when
// the standalone component schema still exists.
export type EndpointResponseContract = [
  Assert<Equal<GetResponse<'/api/health'>, Schemas['HealthResponse']>>,
  Assert<Equal<GetResponse<'/api/overview'>, Schemas['OverviewResponse']>>,
  Assert<Equal<GetResponse<'/api/players'>, Schemas['PaginatedPlayers']>>,
  Assert<Equal<GetResponse<'/api/players/compare'>, Schemas['CompareResponse']>>,
  Assert<Equal<GetResponse<'/api/players/{player_id}'>, Schemas['PlayerIdentity']>>,
  Assert<Equal<GetResponse<'/api/players/{player_id}/contract'>, Schemas['Contract'] | null>>,
  Assert<Equal<GetResponse<'/api/players/{player_id}/seasons'>, Schemas['SeasonHistoryRow'][]>>,
  Assert<Equal<GetResponse<'/api/players/{player_id}/stats'>, Schemas['PlayerStats']>>,
  Assert<Equal<GetResponse<'/api/players/{player_id}/value'>, Schemas['HockeyValue']>>,
  Assert<Equal<GetResponse<'/api/players/{player_id}/value/history'>, Schemas['HockeyValueHistoryPoint'][]>>,
  Assert<Equal<GetResponse<'/api/rankings/hockey-value'>, Schemas['PlayerSummary'][]>>,
  Assert<Equal<GetResponse<'/api/search'>, Schemas['SearchResponse']>>,
  Assert<Equal<GetResponse<'/api/seasons'>, Schemas['SeasonInfo']>>,
  Assert<Equal<GetResponse<'/api/teams'>, Schemas['TeamSummary'][]>>,
  Assert<Equal<GetResponse<'/api/teams/{team_id}'>, Schemas['Team']>>,
  Assert<Equal<GetResponse<'/api/teams/{team_id}/cap'>, Schemas['TeamCap']>>,
  Assert<Equal<GetResponse<'/api/teams/{team_id}/contracts'>, Schemas['TeamContractsResponse']>>,
  Assert<Equal<GetResponse<'/api/teams/{team_id}/roster'>, Schemas['TeamRosterResponse']>>,
]
