import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import { SeasonProvider, useSeason } from './SeasonContext'

function Consumer() {
  const { season, setSeason, info } = useSeason()
  return <><span>{season}</span><span>{info?.currentSeason ?? 'none'}</span><button onClick={() => setSeason(2024)}>change</button></>
}

describe('SeasonContext', () => {
  it('loads and persists a selected season', async () => {
    const user = userEvent.setup()
    render(<SeasonProvider><Consumer /></SeasonProvider>)
    await waitFor(() => expect(screen.getAllByText('2025')).toHaveLength(2))
    await user.click(screen.getByRole('button', { name: 'change' }))
    expect(screen.getByText('2024')).toBeInTheDocument()
    expect(localStorage.getItem('tradevalue-season')).toBe('2024')
  })

  it('keeps defaults when season loading fails', async () => {
    vi.spyOn(api, 'getSeasons').mockRejectedValueOnce(new Error('offline'))
    render(<SeasonProvider><Consumer /></SeasonProvider>)
    await waitFor(() => expect(screen.getByText('none')).toBeInTheDocument())
  })

  it('requires a provider', () => {
    expect(() => render(<Consumer />)).toThrow('useSeason must be used within SeasonProvider')
  })
})
