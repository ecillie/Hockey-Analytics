import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

describe('AppShell API status', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
    vi.resetModules()
  })

  it('shows a connected status outside mock mode', async () => {
    vi.stubEnv('VITE_USE_MOCK_API', 'false')
    const { AppShell } = await import('./AppShell')
    render(<MemoryRouter><AppShell /></MemoryRouter>)
    expect(screen.getByText('API connected')).toBeInTheDocument()
  })
})
