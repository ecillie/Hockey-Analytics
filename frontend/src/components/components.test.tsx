import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import type { PlayerSummary } from '../api'
import { SeasonProvider } from '../context/SeasonContext'
import { Pagination } from './common/Pagination'
import { SeasonSelector } from './common/SeasonSelector'
import { Sparkline } from './common/Sparkline'
import { EmptyState, ErrorState, LoadingState } from './common/States'
import { StatusBadge } from './common/StatusBadge'
import { PlayerTable } from './players/PlayerTable'
import { mockPlayers } from '../mocks/fixtures'

const withRouter = (node: React.ReactNode) => render(<MemoryRouter>{node}</MemoryRouter>)

describe('shared components', () => {
  it('paginates in both directions and handles an empty result set', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    const { rerender } = render(<Pagination page={2} totalPages={3} totalItems={25} onChange={onChange} />)
    await user.click(screen.getByRole('button', { name: 'Previous' }))
    await user.click(screen.getByRole('button', { name: 'Next' }))
    expect(onChange.mock.calls).toEqual([[1], [3]])
    rerender(<Pagination page={1} totalPages={0} totalItems={0} onChange={onChange} />)
    expect(screen.getByText('0 results · Page 1 of 1')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled()
  })

  it('supports controlled compact season selection', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<SeasonProvider><SeasonSelector value={2025} onChange={onChange} compact /></SeasonProvider>)
    await screen.findByRole('option', { name: '2024–25' })
    await user.selectOptions(screen.getByLabelText('Season'), '2024')
    expect(onChange).toHaveBeenCalledWith(2024)
    expect(screen.getByText('Season').closest('label')).toHaveClass('compact')
  })

  it('renders sparkline edge cases and state defaults', async () => {
    const retry = vi.fn()
    const user = userEvent.setup()
    const { rerender } = render(<Sparkline values={[null]} />)
    expect(screen.getByRole('img', { name: 'Trend from 0 to 0' })).toBeInTheDocument()
    rerender(<Sparkline values={[2, 2, null]} />)
    expect(screen.getByRole('img', { name: 'Trend from 2 to 0' })).toBeInTheDocument()
    rerender(<LoadingState />)
    expect(screen.getByLabelText('Loading').children).toHaveLength(6)
    rerender(<ErrorState />)
    expect(screen.getByRole('alert')).toHaveTextContent('Unable to load this data.')
    rerender(<ErrorState message="Broken" onRetry={retry} />)
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    expect(retry).toHaveBeenCalledOnce()
    rerender(<EmptyState />)
    expect(screen.getByText('No results')).toBeInTheDocument()
  })

  it('renders active and non-active roster labels', () => {
    const { rerender } = render(<StatusBadge status="ACTIVE" />)
    expect(screen.getByText('NHL')).toHaveClass('status-active')
    rerender(<StatusBadge status="LTIR" />)
    expect(screen.getByText('LTIR')).toHaveClass('status-ltir')
  })

  it('renders an empty, static, and sortable player table', async () => {
    const user = userEvent.setup()
    const onSort = vi.fn()
    const incomplete: PlayerSummary = {
      ...mockPlayers[0], age: null, team: null, primaryPosition: null,
      gamesPlayed: null, goals: null, assists: null, points: null, gameScore: null,
      gameScorePer60: null, hockeyValue: null, capHitCents: null, rosterStatus: 'UNKNOWN',
    }
    const { rerender } = withRouter(<PlayerTable players={[]} />)
    expect(screen.getByText('No players found')).toBeInTheDocument()
    rerender(<MemoryRouter><PlayerTable players={[incomplete]} compact /></MemoryRouter>)
    expect(screen.getByRole('table')).toHaveClass('table-compact')
    expect(screen.getAllByText('—').length).toBeGreaterThan(2)
    expect(screen.getByRole('button', { name: 'HV' })).toBeDisabled()
    rerender(<MemoryRouter><PlayerTable players={[mockPlayers[0]]} sort="hockeyValue" order="asc" onSort={onSort} /></MemoryRouter>)
    expect(screen.getByRole('button', { name: 'HV↑' })).toHaveClass('sorted')
    await user.click(screen.getByRole('button', { name: 'PTS' }))
    expect(onSort).toHaveBeenCalledWith('points')
    rerender(<MemoryRouter><PlayerTable players={[mockPlayers[0]]} sort="hockeyValue" order="desc" onSort={onSort} /></MemoryRouter>)
    expect(screen.getByRole('button', { name: 'HV↓' })).toBeInTheDocument()
  })
})
