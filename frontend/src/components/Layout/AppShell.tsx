import { NavLink, Outlet } from 'react-router-dom'
import { isMockMode } from '../../api'
import { Icon } from '../common/Icon'
import { GlobalSearch } from '../search/GlobalSearch'

const navigation = [
  { to: '/', label: 'Overview', icon: 'overview' as const, end: true },
  { to: '/players', label: 'Players', icon: 'players' as const },
  { to: '/teams', label: 'Teams', icon: 'teams' as const },
  { to: '/compare', label: 'Compare', icon: 'compare' as const },
]

export function AppShell() {
  return <div className="app-shell">
    <header className="topbar">
      <NavLink to="/" className="brand" aria-label="TradeValue home"><span className="brand-mark">TV</span><span><strong>TradeValue</strong><small>NHL ANALYTICS</small></span></NavLink>
      <GlobalSearch />
      <div className="data-status"><span className="status-dot" />{isMockMode ? 'Development data' : 'API connected'}</div>
    </header>
    <aside className="sidebar" aria-label="Primary navigation">
      <nav>{navigation.map((item) => <NavLink to={item.to} end={item.end} key={item.to}><Icon name={item.icon} /><span>{item.label}</span></NavLink>)}</nav>
      <div className="sidebar-note"><strong>Hockey Value</strong><p>Projected performance value above replacement, scaled by usage.</p></div>
    </aside>
    <main className="content"><Outlet /></main>
    <nav className="mobile-nav" aria-label="Mobile navigation">{navigation.map((item) => <NavLink to={item.to} end={item.end} key={item.to}><Icon name={item.icon} /><span>{item.label}</span></NavLink>)}</nav>
  </div>
}
