import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiClient, ApiError } from './client'

describe('ApiClient', () => {
  afterEach(() => vi.restoreAllMocks())

  it('serializes query parameters and parses JSON', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ status: 'ok' }), { status: 200, headers: { 'content-type': 'application/json' } }))
    const client = new ApiClient('https://stats.example')
    await expect(client.get('/api/health', { season: 2025, ids: [1, 2] })).resolves.toEqual({ status: 'ok' })
    expect(fetchMock).toHaveBeenCalledWith(new URL('https://stats.example/api/health?season=2025&ids=1%2C2'), expect.objectContaining({ method: 'GET' }))
  })

  it('normalizes backend errors', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ error: { code: 'PLAYER_NOT_FOUND', message: 'Player not found.' } }), { status: 404, headers: { 'content-type': 'application/json' } }))
    const promise = new ApiClient('https://stats.example').get('/api/players/0')
    await expect(promise).rejects.toMatchObject({ status: 404, code: 'PLAYER_NOT_FOUND', message: 'Player not found.' } satisfies Partial<ApiError>)
  })

  it('normalizes network failures', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('offline'))
    await expect(new ApiClient('https://stats.example').get('/api/health')).rejects.toMatchObject({ status: 0, code: 'NETWORK_ERROR' })
  })
})
