# TradeValue Frontend API Contract

This document is the backend implementation blueprint for the frontend in `frontend/`. All JSON fields use camelCase. Seasons are represented by their start year (`2025` means 2025–26), dates are ISO 8601 strings, durations are seconds, ratios use `0.10 = 10%`, and money is integer cents. Nullable database values remain `null`; they are not coerced to zero.

## Shared conventions

- Base URL: `VITE_API_BASE_URL`; all routes below are relative to it.
- Success bodies are JSON. Collection endpoints use bounded results.
- Errors use `{ "error": { "code": "PLAYER_NOT_FOUND", "message": "Player not found.", "details": { "field": ["reason"] } } }`. `details` is optional.
- `RosterStatus`: `ACTIVE | MINORS | LTIR | UNKNOWN` (the UI labels `ACTIVE` as NHL).
- `Position`: `C | LW | RW | D | G | F`.
- Pagination: `{ page, pageSize, totalItems, totalPages }`; `page` is one-based and `pageSize` must be capped by the backend.
- Regular-season requests correspond to database `game_type = 2`. Aggregate player rows should prefer `stat_scope = TOTAL` to avoid double-counting traded players.
- Hockey Value follows the model metadata definition: next-season `game_score_per_60_above_replacement × TOI hours`. The backend owns this calculation and model version selection.
- CORS must allow the deployed frontend origin. Authentication is not currently required.

## Endpoint index and priority

| Priority | Method | Path | Frontend function | Primary consumers |
|---|---|---|---|---|
| P0 | GET | `/api/health` | `getHealth()` | deployment health checks |
| P0 | GET | `/api/seasons` | `getSeasons()` | app season context, all selectors |
| P0 | GET | `/api/players` | `getPlayers(params)` | Players, compare picker |
| P0 | GET | `/api/players/:playerId` | `getPlayer(id)` | Player Detail |
| P0 | GET | `/api/players/:playerId/stats` | `getPlayerStats(id, season)` | Player Detail, Compare |
| P0 | GET | `/api/players/:playerId/seasons` | `getPlayerSeasons(id)` | Player Detail history |
| P0 | GET | `/api/teams` | `getTeams()` | Teams, player filters |
| P0 | GET | `/api/teams/:teamId` | `getTeam(id)` | Team Detail |
| P0 | GET | `/api/teams/:teamId/roster` | `getTeamRoster(id, params)` | Team Detail |
| P1 | GET | `/api/players/:playerId/value` | `getPlayerValue(id, season)` | Player Detail, Compare |
| P1 | GET | `/api/players/:playerId/value/history` | `getPlayerValueHistory(id)` | future dedicated value view |
| P1 | GET | `/api/rankings/hockey-value` | `getHockeyValueLeaders(params)` | ranking integrations |
| P1 | GET | `/api/players/:playerId/contract` | `getPlayerContract(id)` | Player Detail, Compare |
| P1 | GET | `/api/teams/:teamId/contracts` | `getTeamContracts(id, season)` | Team Detail |
| P1 | GET | `/api/teams/:teamId/cap` | `getTeamCap(id, season)` | Team Detail |
| P1 | GET | `/api/search` | `search(query, types, limit)` | global search |
| P1 | GET | `/api/overview` | `getOverview(season)` | Overview |
| P2 | GET | `/api/players/compare` | `comparePlayers(ids, season)` | Compare |

## Endpoints

### GET `/api/health`

Purpose: lightweight service readiness check. Query: none. Response: `{ "status": "ok" }`. Type: `{ status: "ok" }`. Used by `getHealth()` and external health checks.

### GET `/api/seasons`

Purpose: the single source for valid seasons and cap ceilings. Query: none. Response: `SeasonInfo`, containing `currentSeason` and `availableSeasons[]` with `startYear`, `endYear`, `label`, and nullable `salaryCapCents`. Used by `getSeasons()`, `SeasonProvider`, and every `SeasonSelector`.

### GET `/api/players`

Purpose: server-side filtered, sorted, paginated player/season view; it must contain the joins and derived fields needed by the table to prevent N+1 requests.

Query:

- `season: integer` (season start year)
- `team: string` (team abbreviation)
- `position: Position`
- `rosterStatus: RosterStatus`
- `search: string`
- `sort: name | team | gamesPlayed | goals | assists | points | gameScore | gameScorePer60 | hockeyValue | capHitCents`
- `order: asc | desc`
- `page: integer >= 1`
- `pageSize: integer` (frontend uses 10/25/100; backend should cap at 100)

Response: `PaginatedResponse<PlayerSummary>`. Used by `getPlayers()`, Players, and Compare. `PlayerSummary` includes identity/team, season stats, total ice time, Hockey Value/current projection, current-season cap hit, and roster status. All statistics and value fields are nullable.

### GET `/api/players/:playerId`

Purpose: stable identity/profile plus current team from the applicable team stint. Path `playerId: integer`. Response: `PlayerIdentity`. Used by `getPlayer()` and Player Detail. A missing ID returns `404 PLAYER_NOT_FOUND`.

### GET `/api/players/:playerId/stats`

Purpose: one player-season payload with separately modeled stat groups. Query `season: integer` required. Response: `PlayerStats` with `traditional: TraditionalSkaterStats | null`, `advanced: AdvancedSkaterStats | null`, and `goalie: GoalieStats | null`. A skater has no goalie group and a goalie has no skater groups. Used by Player Detail and Compare.

### GET `/api/players/:playerId/seasons`

Purpose: bounded career table/trend data. Query: none. Response: `SeasonHistoryRow[]`, newest or oldest ordering is acceptable if documented; frontend sorts for display. Rows include season, team, GP/G/A/PTS, GS/60, and Hockey Value. Used by Player Detail.

### GET `/api/players/:playerId/value`

Purpose: authoritative model output and interpretable calculation inputs. Query `season?: integer`; omit to use the current season. Response: `HockeyValue` with nullable `hockeyValue`, `projectedNextSeasonHockeyValue`, `gameScorePer60AboveReplacement`, `toiHours`, and `modelVersion`. Used by Player Detail and Compare.

### GET `/api/players/:playerId/value/history`

Purpose: historical model values. Query: none. Response: `HockeyValueHistoryPoint[]` (`season`, nullable `hockeyValue`). Used by `getPlayerValueHistory()`; reserved for richer trend views.

### GET `/api/rankings/hockey-value`

Purpose: bounded ranking without fetching the whole player table. Query `season`, optional `position`, `team`, and `limit` (cap 100). Response: `PlayerSummary[]`, descending by Hockey Value. Used by `getHockeyValueLeaders()`.

### GET `/api/teams`

Purpose: concise active team directory/filter source. Query: none. Response: `TeamSummary[]` with database-backed `id`, nullable `nhlTeamId`, `abbreviation`, `name`, nullable `city`, and `active`. Conference/division are intentionally absent because the schema does not store them. Used by Teams and player filters.

### GET `/api/teams/:teamId`

Purpose: team identity plus roster-status counts for the current organization view. Response: `Team` (`TeamSummary` plus `rosterCounts` for every `RosterStatus`). Used by Team Detail. Missing ID returns `404 TEAM_NOT_FOUND`.

### GET `/api/teams/:teamId/roster`

Purpose: avoid one request per player by returning roster and current-season table fields together. Query `season: integer`, optional `status: RosterStatus`. Response: `TeamRosterResponse` with `team`, `season`, nullable applied `status`, and `players: PlayerSummary[]`. Used by Team Detail.

### GET `/api/players/:playerId/contract`

Purpose: current/relevant contract and every associated contract season. Query: none. Response: `Contract | null`; absence is a successful `null`, while an unknown player is 404. Contract money is cents; clauses/source payloads are intentionally excluded. Used by Player Detail and Compare.

### GET `/api/teams/:teamId/contracts`

Purpose: season contract ledger without client joins. Query `season: integer`. Response: `TeamContractsResponse` with team, season, and rows containing `player: PlayerIdentity`, `contract: Contract`, and applicable `season: ContractSeason`. Used by Team Detail.

### GET `/api/teams/:teamId/cap`

Purpose: backend-owned cap aggregation. Query `season: integer`. Response: `TeamCap` with nullable ceiling/space, active/LTIR/minors subtotals, total commitments, and `calculationStatus: ESTIMATE | AUTHORITATIVE`. The frontend must not calculate buried-contract relief, accrued space, or LTIR pools. Used by Team Detail.

### GET `/api/search`

Purpose: debounced, bounded cross-entity search. Query `q: string` (minimum two characters), `types: comma-separated player,team`, `limit: integer` (cap recommended at 20). Response: `SearchResponse` with `players: PlayerIdentity[]` and `teams: TeamSummary[]`. Used by Global Search.

### GET `/api/overview`

Purpose: one efficient homepage aggregate rather than eight independent calls. Query `season: integer`. Response: `OverviewResponse`: league tracked-player/game/goal counts, nullable average Hockey Value, plus top-five `PlayerSummary[]` lists for Hockey Value, points, goals, and GS/60. Used by Overview.

### GET `/api/players/compare`

Purpose: optional aggregate for two to four players. Query `ids: comma-separated integer IDs` and `season: integer`. Response: `CompareResponse`, each row containing `player`, `stats`, nullable `value`, and nullable `contract`. Used by Compare. The backend may initially implement this by composing existing service-layer queries, but must avoid per-player database connection overhead.

## Required response types

The authoritative TypeScript declarations are in `frontend/src/api/types.ts`: `ApiErrorBody`, `Pagination`, `PaginatedResponse<T>`, `RosterStatus`, `Position`, `TeamSummary`, `Team`, `PlayerIdentity`, `PlayerSummary`, `TraditionalSkaterStats`, `AdvancedSkaterStats`, `GoalieStats`, `PlayerStats`, `SeasonHistoryRow`, `HockeyValue`, `HockeyValueHistoryPoint`, `Contract`, `ContractSeason`, `TeamRosterResponse`, `TeamContractsResponse`, `TeamCap`, `SeasonInfo`, `SearchResponse`, `OverviewResponse`, and `CompareResponse`.

## Backend implementation requirements

1. Implement filtering, whitelisted sorting, stable secondary ordering by player ID, and pagination in SQL/service code.
2. Resolve player totals without double-counting team stints. Treat `TOTAL` records as canonical for traded-player season totals.
3. Keep missing numeric data as `null`; zero means a measured zero.
4. Use cents as JSON integers and ratios as JSON numbers. Never serialize currency-formatted strings.
5. Join table-critical values—team, stats, value, cap hit, status—inside `/api/players` and roster aggregates.
6. Calculate Hockey Value, projections, and team cap server-side. Return the model version with player value output.
7. Validate enums, IDs, page bounds, seasons, sort fields, comparison size, and search length. Use 400 for invalid input, 404 for missing entities, and the shared error envelope for all failures.
8. Add response validation/contract tests against the TypeScript shapes before switching `VITE_USE_MOCK_API=false`.

## Frontend cutover

Set `VITE_API_BASE_URL` to the deployed API origin and `VITE_USE_MOCK_API=false`. No page or component changes should be required. The mock latency control (`VITE_MOCK_LATENCY_MS`) is development-only.
