import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from '../../api'
import { mockPlayers, mockTeams } from '../../mocks/fixtures'
import { GlobalSearch } from './GlobalSearch'

function Location() {
  return <output>{useLocation().pathname}{useLocation().search}</output>
}

const renderSearch = () => render(<MemoryRouter><GlobalSearch /><Routes><Route path="*" element={<Location />} /></Routes></MemoryRouter>)

describe('GlobalSearch', () => {
  afterEach(() => vi.restoreAllMocks())

  it('shows results and navigates to all player results', async () => {
    vi.spyOn(api, 'search').mockResolvedValue({ players: [mockPlayers[0]], teams: [mockTeams[10]] })
    const user = userEvent.setup()
    renderSearch()
    const input = screen.getByRole('textbox', { name: 'Search players and teams' })
    await user.type(input, 'mc')
    expect(screen.getByText('Searching…')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('Connor McDavid')).toBeInTheDocument())
    expect(screen.getByText('Edmonton Oilers')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'View all player results' }))
    expect(screen.getByRole('status')).toHaveTextContent('/players?search=mc')
  })

  it('opens result links and handles players without team or position', async () => {
    vi.spyOn(api, 'search').mockResolvedValue({ players: [{ ...mockPlayers[0], team: null, primaryPosition: null }], teams: [mockTeams[10]] })
    const user = userEvent.setup()
    renderSearch()
    await user.type(screen.getByRole('textbox'), 'mc')
    await waitFor(() => expect(screen.getByText('— · —')).toBeInTheDocument())
    await user.click(screen.getByText('Connor McDavid'))
    expect(screen.getByRole('status')).toHaveTextContent('/players/101')
  })

  it('navigates to a team result', async () => {
    vi.spyOn(api, 'search').mockResolvedValue({ players: [], teams: [mockTeams[10]] })
    const user = userEvent.setup()
    renderSearch()
    await user.type(screen.getByRole('textbox'), 'oil')
    await user.click(await screen.findByText('Edmonton Oilers'))
    expect(screen.getByRole('status')).toHaveTextContent('/teams/11')
  })

  it('shows empty results after success or failure', async () => {
    const search = vi.spyOn(api, 'search').mockResolvedValueOnce({ players: [], teams: [] }).mockRejectedValueOnce(new Error('offline'))
    const user = userEvent.setup()
    renderSearch()
    const input = screen.getByRole('textbox')
    await user.type(input, 'zz')
    expect(await screen.findByText('No matching players or teams.')).toBeInTheDocument()
    await user.clear(input)
    await user.type(input, 'yy')
    await waitFor(() => expect(search).toHaveBeenCalledTimes(2))
    expect(await screen.findByText('No matching players or teams.')).toBeInTheDocument()
  })

  it('submits trimmed queries, ignores empty submits, and closes outside', async () => {
    vi.spyOn(api, 'search').mockResolvedValue({ players: [], teams: [] })
    const user = userEvent.setup()
    renderSearch()
    const input = screen.getByRole('textbox')
    await user.click(input)
    await user.keyboard('{Enter}')
    expect(screen.getByRole('status')).toHaveTextContent('/')
    await user.type(input, '  sidney  ')
    await user.keyboard('{Enter}')
    expect(screen.getByRole('status')).toHaveTextContent('/players?search=sidney')
    await user.clear(input)
    await user.type(input, 'ab')
    await screen.findByText('No matching players or teams.')
    await user.click(document.body)
    expect(screen.queryByText('No matching players or teams.')).not.toBeInTheDocument()
    await user.click(input)
    expect(screen.getByText('No matching players or teams.')).toBeInTheDocument()
  })

  it('cancels a pending debounced search when the query changes', async () => {
    vi.useFakeTimers()
    const search = vi.spyOn(api, 'search').mockResolvedValue({ players: [], teams: [] })
    renderSearch()
    const input = screen.getByRole('textbox')
    input.focus()
    await act(async () => {
      input.dispatchEvent(new InputEvent('input', { bubbles: true, data: 'a', inputType: 'insertText' }))
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set?.call(input, 'ab')
      input.dispatchEvent(new Event('input', { bubbles: true }))
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set?.call(input, 'abc')
      input.dispatchEvent(new Event('input', { bubbles: true }))
      vi.advanceTimersByTime(250)
    })
    expect(search).toHaveBeenCalledTimes(1)
    vi.useRealTimers()
  })
})
