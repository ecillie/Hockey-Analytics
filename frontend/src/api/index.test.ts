import { afterEach, describe, expect, it, vi } from 'vitest'

describe('API selection', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
    vi.resetModules()
  })

  it('selects the HTTP API when mock mode is disabled', async () => {
    vi.stubEnv('VITE_USE_MOCK_API', 'false')
    const { api, isMockMode } = await import('./index')
    const { httpApi } = await import('./httpService')
    expect(isMockMode).toBe(false)
    expect(api).toBe(httpApi)
  })
})
