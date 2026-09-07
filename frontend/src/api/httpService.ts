import { ApiClient } from './client'
import type { ApiService, CompareResponse, Contract, HockeyValue, HockeyValueHistoryPoint, OverviewResponse, PaginatedResponse, PlayerIdentity, PlayerStats, PlayerSummary, RosterStatus, SearchResponse, SeasonHistoryRow, SeasonInfo, Team, TeamCap, TeamContractsResponse, TeamRosterResponse, TeamSummary } from './types'

const client = new ApiClient(import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000')

export const httpApi: ApiService = {
  getHealth: (signal) => client.get('/api/health', undefined, signal),
  getSeasons: (signal) => client.get<SeasonInfo>('/api/seasons', undefined, signal),
  getOverview: (season, signal) => client.get<OverviewResponse>('/api/overview', { season }, signal),
  getPlayers: (params = {}, signal) => client.get<PaginatedResponse<PlayerSummary>>('/api/players', { ...params }, signal),
  getPlayer: (id, signal) => client.get<PlayerIdentity>(`/api/players/${id}`, undefined, signal),
  getPlayerStats: (id, season, signal) => client.get<PlayerStats>(`/api/players/${id}/stats`, { season }, signal),
  getPlayerSeasons: (id, signal) => client.get<SeasonHistoryRow[]>(`/api/players/${id}/seasons`, undefined, signal),
  getPlayerValue: (id, season, signal) => client.get<HockeyValue>(`/api/players/${id}/value`, { season }, signal),
  getPlayerValueHistory: (id, signal) => client.get<HockeyValueHistoryPoint[]>(`/api/players/${id}/value/history`, undefined, signal),
  getHockeyValueLeaders: (params, signal) => client.get<PlayerSummary[]>('/api/rankings/hockey-value', params, signal),
  getPlayerContract: (id, signal) => client.get<Contract | null>(`/api/players/${id}/contract`, undefined, signal),
  getTeams: (signal) => client.get<TeamSummary[]>('/api/teams', undefined, signal),
  getTeam: (id, signal) => client.get<Team>(`/api/teams/${id}`, undefined, signal),
  getTeamRoster: (id, params, signal) => client.get<TeamRosterResponse>(`/api/teams/${id}/roster`, params, signal),
  getTeamContracts: (id, season, signal) => client.get<TeamContractsResponse>(`/api/teams/${id}/contracts`, { season }, signal),
  getTeamCap: (id, season, signal) => client.get<TeamCap>(`/api/teams/${id}/cap`, { season }, signal),
  search: (q, types = ['player', 'team'], limit = 8, signal) => client.get<SearchResponse>('/api/search', { q, types, limit }, signal),
  comparePlayers: (ids, season, signal) => client.get<CompareResponse>('/api/players/compare', { ids, season }, signal),
}

export type { RosterStatus }
