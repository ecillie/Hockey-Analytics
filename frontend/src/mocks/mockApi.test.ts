import { describe, expect, it } from 'vitest'
import { mockApi, queryMockPlayers } from './mockApi'
import { mockPlayers } from './fixtures'

describe('mock API', () => {
  it('filters, sorts, and paginates player rows', () => {
    const result = queryMockPlayers({ team: 'EDM', sort: 'points', order: 'desc', page: 1, pageSize: 1 })
    expect(result.pagination).toMatchObject({ page: 1, pageSize: 1, totalItems: 2, totalPages: 2 })
    expect(result.data[0].fullName).toBe('Connor McDavid')
  })

  it('supports every player filter, sort direction, and paging bound', () => {
    expect(queryMockPlayers({ search: 'connor', position: 'C', rosterStatus: 'ACTIVE', order: 'asc', sort: 'name', page: 0, pageSize: 0 }).pagination).toMatchObject({ page: 1, pageSize: 1 })
    expect(queryMockPlayers({ sort: 'team', order: 'asc', pageSize: 1000 }).pagination.pageSize).toBe(100)
    expect(queryMockPlayers().data.length).toBeGreaterThan(0)

    const first = mockPlayers[0]
    const second = mockPlayers[1]
    const originalFirst = first.hockeyValue
    const originalSecond = second.hockeyValue
    first.hockeyValue = null
    second.hockeyValue = null
    try {
      expect(queryMockPlayers({ sort: 'hockeyValue', order: 'asc' }).data).toContain(first)
    } finally {
      first.hockeyValue = originalFirst
      second.hockeyValue = originalSecond
    }
  })

  it('supports empty and missing-player responses', async () => {
    expect(queryMockPlayers({ search: 'no such player' }).data).toEqual([])
    await expect(mockApi.getPlayer(99999)).rejects.toMatchObject({ status: 404, code: 'PLAYER_NOT_FOUND' })
  })

  it('builds two-to-four player comparisons', async () => {
    const result = await mockApi.comparePlayers([101, 102], 2025)
    expect(result.players).toHaveLength(2)
    expect(result.players[0].stats.season).toBe(2025)
  })

  it('implements the complete mock service contract', async () => {
    await expect(mockApi.getHealth()).resolves.toEqual({ status: 'ok' })
    await expect(mockApi.getSeasons()).resolves.toMatchObject({ currentSeason: 2025 })
    await expect(mockApi.getPlayer(101)).resolves.toMatchObject({ id: 101 })
    await expect(mockApi.getPlayerStats(101, 2024)).resolves.toMatchObject({ season: 2024 })
    await expect(mockApi.getPlayerSeasons(101)).resolves.toHaveLength(4)
    await expect(mockApi.getPlayerValue(101)).resolves.toMatchObject({ season: 2025 })
    await expect(mockApi.getPlayerValue(120, 2024)).resolves.toMatchObject({ hockeyValue: 0, toiHours: null })
    await expect(mockApi.getPlayerValueHistory(101)).resolves.toHaveLength(4)
    await expect(mockApi.getHockeyValueLeaders({ season: 2025, limit: 2 })).resolves.toHaveLength(2)
    await expect(mockApi.getPlayerContract(101)).resolves.toMatchObject({ playerId: 101 })
    await expect(mockApi.getTeams()).resolves.toHaveLength(32)
    await expect(mockApi.getTeam(11)).resolves.toMatchObject({ id: 11, rosterCounts: expect.any(Object) })
    await expect(mockApi.getTeamRoster(11, { season: 2025, status: 'ACTIVE' })).resolves.toMatchObject({ status: 'ACTIVE' })
    await expect(mockApi.getTeamRoster(11, { season: 2025 })).resolves.toMatchObject({ status: null })
    await expect(mockApi.getTeamContracts(11, 2025)).resolves.toMatchObject({ season: 2025 })
    await expect(mockApi.getTeamContracts(11, 2030)).resolves.toMatchObject({ season: 2030 })
    await expect(mockApi.getTeamCap(11, 2025)).resolves.toMatchObject({ teamId: 11, calculationStatus: 'ESTIMATE' })
    await expect(mockApi.search('connor')).resolves.toMatchObject({ players: expect.any(Array), teams: expect.any(Array) })
    await expect(mockApi.search('edmonton', ['team'], 1)).resolves.toMatchObject({ players: [], teams: [expect.objectContaining({ id: 11 })] })
    await expect(mockApi.getOverview(2024)).resolves.toMatchObject({ season: 2024 })
    await expect(mockApi.comparePlayers([101, 102], 2024)).resolves.toMatchObject({ season: 2024 })
  }, 15_000)

  it('returns typed not-found and validation failures', async () => {
    await expect(mockApi.getTeam(99999)).rejects.toMatchObject({ code: 'TEAM_NOT_FOUND' })
    await expect(mockApi.getPlayer(99999)).rejects.toMatchObject({ code: 'PLAYER_NOT_FOUND' })
    await expect(mockApi.comparePlayers([101], 2025)).rejects.toMatchObject({ code: 'INVALID_COMPARISON' })
    await expect(mockApi.comparePlayers([101, 102, 103, 104, 105], 2025)).rejects.toMatchObject({ code: 'INVALID_COMPARISON' })
    await expect(mockApi.getPlayers({ search: '__error__' })).rejects.toMatchObject({ code: 'MOCK_FAILURE' })
  })

  it('honors signals aborted before and during latency', async () => {
    const alreadyAborted = new AbortController()
    alreadyAborted.abort()
    await expect(mockApi.getHealth(alreadyAborted.signal)).rejects.toMatchObject({ name: 'AbortError' })

    const controller = new AbortController()
    const request = mockApi.getHealth(controller.signal)
    controller.abort()
    await expect(request).rejects.toMatchObject({ name: 'AbortError' })
  })
})
