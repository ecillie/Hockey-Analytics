import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { AppShell } from './components/Layout/AppShell'
import { SeasonProvider } from './context/SeasonContext'
import { ComparePage } from './pages/ComparePage'
import { NotFoundPage } from './pages/NotFoundPage'
import { OverviewPage } from './pages/OverviewPage'
import { PlayerDetailPage } from './pages/PlayerDetailPage'
import { PlayersPage } from './pages/PlayersPage'
import { TeamDetailPage } from './pages/TeamDetailPage'
import { TeamsPage } from './pages/TeamsPage'

export function App() {
  return <BrowserRouter><SeasonProvider><Routes><Route element={<AppShell />}><Route index element={<OverviewPage />} /><Route path="players" element={<PlayersPage />} /><Route path="players/:id" element={<PlayerDetailPage />} /><Route path="teams" element={<TeamsPage />} /><Route path="teams/:id" element={<TeamDetailPage />} /><Route path="compare" element={<ComparePage />} /><Route path="*" element={<NotFoundPage />} /></Route></Routes></SeasonProvider></BrowserRouter>
}
