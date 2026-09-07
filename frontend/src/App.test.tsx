import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { App } from './App'

const renderAt = (path: string) => {
  window.history.pushState({}, '', path)
  return render(<App />)
}

describe('application routes', () => {
  it('renders the overview and changes season', async () => {
    const user = userEvent.setup()
    renderAt('/')
    expect(await screen.findByRole('heading', { name: 'NHL Overview' })).toBeInTheDocument()
    await screen.findByRole('option', { name: '2024–25' })
    await user.selectOptions(screen.getByLabelText('Season'), '2024')
    expect(screen.getByLabelText('Season')).toHaveValue('2024')
  })

  it('searches and filters the player list through URL state', async () => {
    const user = userEvent.setup()
    renderAt('/players')
    expect(await screen.findByRole('heading', { name: 'Players' })).toBeInTheDocument()
    const inputs = screen.getAllByPlaceholderText('Player name')
    await user.type(inputs[0], 'McDavid')
    await screen.findByText('1 players')
    expect(screen.getByText('Connor McDavid')).toBeInTheDocument()
    expect(screen.queryByText('Nathan MacKinnon')).not.toBeInTheDocument()
  })

  it('renders player detail, team navigation, and comparison routes', async () => {
    const { unmount } = renderAt('/players/101')
    expect(await screen.findByRole('heading', { name: 'Connor McDavid' })).toBeInTheDocument()
    expect(await screen.findByText('Next-season projection')).toBeInTheDocument()
    unmount()
    window.history.pushState({}, '', '/teams/11')
    render(<App />)
    expect(await screen.findByRole('heading', { name: 'Edmonton Oilers' })).toBeInTheDocument()
    expect(await screen.findByText('Contract ledger')).toBeInTheDocument()
  })

  it('renders empty and API error states', async () => {
    const { unmount } = renderAt('/players?search=doesnotexist')
    expect(await screen.findByText('No players found')).toBeInTheDocument()
    unmount()
    window.history.pushState({}, '', '/players?search=__error__')
    render(<App />)
    await waitFor(() => expect(screen.getByText('Unable to load player statistics.')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })

  it('renders a not-found route', async () => {
    renderAt('/missing')
    expect(await screen.findByRole('heading', { name: 'Page not found' })).toBeInTheDocument()
  })
})
