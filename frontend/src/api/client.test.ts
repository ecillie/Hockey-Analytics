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

  it('skips empty query values and forwards boolean and scalar values', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200, headers: { 'content-type': 'application/json' } }))
    const controller = new AbortController()
    await new ApiClient('https://stats.example/').get('/api/test', { empty: '', missing: undefined, nil: null, active: false, page: 2 }, controller.signal)
    expect(fetchMock).toHaveBeenCalledWith(new URL('https://stats.example/api/test?active=false&page=2'), expect.objectContaining({ signal: controller.signal }))
  })

  it('preserves abort failures', async () => {
    const abort = new DOMException('Aborted', 'AbortError')
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(abort)
    await expect(new ApiClient('https://stats.example').get('/api/health')).rejects.toBe(abort)
  })

  it('rejects non-JSON success responses', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('ok', { status: 200, headers: { 'content-type': 'text/plain' } }))
    await expect(new ApiClient('https://stats.example').get('/api/health')).rejects.toMatchObject({ status: 200, code: 'INVALID_RESPONSE' })
  })

  it('rejects responses without a content type', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(null, { status: 204 }))
    await expect(new ApiClient('https://stats.example').get('/api/health')).rejects.toMatchObject({ code: 'INVALID_RESPONSE' })
  })

  it('supplies fallback fields for non-JSON API errors', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('failure', { status: 503, headers: { 'content-type': 'text/plain' } }))
    await expect(new ApiClient('https://stats.example').get('/api/health')).rejects.toMatchObject({ status: 503, code: 'HTTP_503', message: 'The API could not complete this request.' })
  })

  it('retains structured validation details', async () => {
    const details = { season: ['is invalid'] }
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ error: { code: 'VALIDATION', message: 'Invalid request.', details } }), { status: 422, headers: { 'content-type': 'application/json' } }))
    await expect(new ApiClient('https://stats.example').get('/api/players')).rejects.toMatchObject({ details })
  })
})
