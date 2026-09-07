import { describe, expect, it } from 'vitest'
import { mockApi, queryMockPlayers } from './mockApi'

describe('mock API', () => {
  it('filters, sorts, and paginates player rows', () => {
    const result = queryMockPlayers({ team: 'EDM', sort: 'points', order: 'desc', page: 1, pageSize: 1 })
    expect(result.pagination).toMatchObject({ page: 1, pageSize: 1, totalItems: 2, totalPages: 2 })
    expect(result.data[0].fullName).toBe('Connor McDavid')
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
})
