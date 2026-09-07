import { ApiError } from '../api/client'
import type { ApiService, HockeyValue, PlayerFilters, PlayerSummary, RosterStatus } from '../api/types'
import { mockContracts, mockHistory, mockPlayers, mockPlayerStats, mockSeasons, mockTeams } from './fixtures'

const latency = Math.max(0, Number(import.meta.env.VITE_MOCK_LATENCY_MS ?? 120))
const wait = async (signal?: AbortSignal) => {
  if (signal?.aborted) throw new DOMException('Aborted', 'AbortError')
  await new Promise<void>((resolve, reject) => {
    const timer = window.setTimeout(resolve, latency)
    signal?.addEventListener('abort', () => { window.clearTimeout(timer); reject(new DOMException('Aborted', 'AbortError')) }, { once: true })
  })
}
const playerOr404 = (id: number) => {
  const player = mockPlayers.find((item) => item.id === id)
  if (!player) throw new ApiError('Player not found.', 404, 'PLAYER_NOT_FOUND')
  return player
}
const teamOr404 = (id: number) => {
  const found = mockTeams.find((item) => item.id === id)
  if (!found) throw new ApiError('Team not found.', 404, 'TEAM_NOT_FOUND')
  return found
}

export function queryMockPlayers(params: PlayerFilters = {}) {
  const page = Math.max(1, params.page ?? 1)
  const pageSize = Math.min(100, Math.max(1, params.pageSize ?? 25))
  let data = mockPlayers.filter((player) =>
    (!params.search || player.fullName.toLowerCase().includes(params.search.toLowerCase())) &&
    (!params.team || player.team?.abbreviation === params.team) &&
    (!params.position || player.primaryPosition === params.position) &&
    (!params.rosterStatus || player.rosterStatus === params.rosterStatus)
  )
  const sort = params.sort ?? 'hockeyValue'
  const direction = params.order === 'asc' ? 1 : -1
  data = [...data].sort((a, b) => {
    const av = sort === 'name' ? a.fullName : sort === 'team' ? a.team?.abbreviation : a[sort]
    const bv = sort === 'name' ? b.fullName : sort === 'team' ? b.team?.abbreviation : b[sort]
    if (av == null) return 1
    if (bv == null) return -1
    return (typeof av === 'string' ? av.localeCompare(String(bv)) : Number(av) - Number(bv)) * direction
  })
  const totalItems = data.length
  return { data: data.slice((page - 1) * pageSize, page * pageSize), pagination: { page, pageSize, totalItems, totalPages: Math.ceil(totalItems / pageSize) } }
}

export const mockApi: ApiService = {
  async getHealth(signal) { await wait(signal); return { status: 'ok' } },
  async getSeasons(signal) { await wait(signal); return mockSeasons },
  async getPlayers(params, signal) { await wait(signal); if (params?.search === '__error__') throw new ApiError('Simulated API failure.', 500, 'MOCK_FAILURE'); return queryMockPlayers(params) },
  async getPlayer(id, signal) { await wait(signal); return playerOr404(id) },
  async getPlayerStats(id, season, signal) { await wait(signal); playerOr404(id); return { ...mockPlayerStats[id], season } },
  async getPlayerSeasons(id, signal) { await wait(signal); playerOr404(id); return mockHistory[id] },
  async getPlayerValue(id, season = 2025, signal) { await wait(signal); const player = playerOr404(id); return { playerId: id, season, hockeyValue: player.hockeyValue, projectedNextSeasonHockeyValue: player.projectedNextSeasonHockeyValue, gameScorePer60AboveReplacement: player.gameScorePer60 ? player.gameScorePer60 - 1.12 : null, toiHours: player.toiSeconds ? player.toiSeconds / 3600 : null, modelVersion: 'mock-skater-v1' } },
  async getPlayerValueHistory(id, signal) { await wait(signal); playerOr404(id); return mockHistory[id].map(({ season, hockeyValue }) => ({ season, hockeyValue })) },
  async getHockeyValueLeaders(params, signal) { await wait(signal); return queryMockPlayers({ ...params, sort: 'hockeyValue', order: 'desc', pageSize: params.limit ?? 10 }).data },
  async getPlayerContract(id, signal) { await wait(signal); playerOr404(id); return mockContracts[id] ?? null },
  async getTeams(signal) { await wait(signal); return mockTeams },
  async getTeam(id, signal) { await wait(signal); const team = teamOr404(id); const roster = mockPlayers.filter((p) => p.team?.id === id); const statuses: RosterStatus[] = ['ACTIVE', 'MINORS', 'LTIR', 'UNKNOWN']; return { ...team, rosterCounts: Object.fromEntries(statuses.map((status) => [status, roster.filter((p) => p.rosterStatus === status).length])) as Record<RosterStatus, number> } },
  async getTeamRoster(id, { season, status }, signal) { await wait(signal); const team = teamOr404(id); return { team, season, status: status ?? null, players: mockPlayers.filter((p) => p.team?.id === id && (!status || p.rosterStatus === status)) } },
  async getTeamContracts(id, season, signal) { await wait(signal); const team = teamOr404(id); return { team, season, contracts: mockPlayers.filter((p) => p.team?.id === id && mockContracts[p.id]).map((player) => ({ player, contract: mockContracts[player.id], season: mockContracts[player.id].seasons.find((s) => s.season === season) ?? mockContracts[player.id].seasons[0] })) } },
  async getTeamCap(id, season, signal) { await wait(signal); teamOr404(id); const roster = mockPlayers.filter((p) => p.team?.id === id); const sum = (status: RosterStatus) => roster.filter((p) => p.rosterStatus === status).reduce((n, p) => n + (p.capHitCents ?? 0), 0); const activeRosterCapCents = sum('ACTIVE'); const ltirCapCents = sum('LTIR'); const minorsCapCents = sum('MINORS'); const totalCommitmentsCents = activeRosterCapCents + ltirCapCents + minorsCapCents; return { teamId: id, season, salaryCapCents: 9550000000, activeRosterCapCents, ltirCapCents, minorsCapCents, totalCommitmentsCents, capSpaceCents: 9550000000 - activeRosterCapCents, calculationStatus: 'ESTIMATE' } },
  async search(query, types = ['player', 'team'], limit = 8, signal) { await wait(signal); const q = query.trim().toLowerCase(); return { players: types.includes('player') ? mockPlayers.filter((p) => p.fullName.toLowerCase().includes(q)).slice(0, limit) : [], teams: types.includes('team') ? mockTeams.filter((t) => `${t.city} ${t.name} ${t.abbreviation}`.toLowerCase().includes(q)).slice(0, limit) : [] } },
  async getOverview(season, signal) { await wait(signal); const sorted = (key: keyof PlayerSummary) => [...mockPlayers].filter((p) => p.primaryPosition !== 'G').sort((a, b) => Number(b[key] ?? 0) - Number(a[key] ?? 0)).slice(0, 5); return { season, league: { players: mockPlayers.length, goals: mockPlayers.reduce((n, p) => n + (p.goals ?? 0), 0), gamesPlayed: mockPlayers.reduce((n, p) => n + (p.gamesPlayed ?? 0), 0), averageHockeyValue: mockPlayers.reduce((n, p) => n + (p.hockeyValue ?? 0), 0) / mockPlayers.length }, leaders: { hockeyValue: sorted('hockeyValue'), points: sorted('points'), goals: sorted('goals'), gameScorePer60: sorted('gameScorePer60') } } },
  async comparePlayers(ids, season, signal) { await wait(signal); if (ids.length < 2 || ids.length > 4) throw new ApiError('Select between 2 and 4 players.', 400, 'INVALID_COMPARISON'); return { season, players: ids.map((id) => { const player = playerOr404(id); const history = mockHistory[id].find((row) => row.season === season); const value: HockeyValue = { playerId: id, season, hockeyValue: history?.hockeyValue ?? player.hockeyValue, projectedNextSeasonHockeyValue: player.projectedNextSeasonHockeyValue, gameScorePer60AboveReplacement: (history?.gameScorePer60 ?? player.gameScorePer60 ?? 1.12) - 1.12, toiHours: player.toiSeconds ? player.toiSeconds / 3600 : null, modelVersion: 'mock-skater-v1' }; return { player, stats: { ...mockPlayerStats[id], season }, value, contract: mockContracts[id] ?? null } }) } },
}
