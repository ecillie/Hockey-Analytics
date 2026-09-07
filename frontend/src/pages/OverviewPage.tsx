import { Link } from 'react-router-dom'
import { api } from '../api'
import { PageHeader } from '../components/common/PageHeader'
import { SeasonSelector } from '../components/common/SeasonSelector'
import { ErrorState, LoadingState } from '../components/common/States'
import { PlayerTable } from '../components/players/PlayerTable'
import { useSeason } from '../context/SeasonContext'
import { useApiQuery } from '../hooks/useApiQuery'
import { formatNumber } from '../utils/format'

export function OverviewPage() {
  const { season } = useSeason()
  const { data, loading, error, retry } = useApiQuery((signal) => api.getOverview(season, signal), [season])
  return <>
    <PageHeader eyebrow="League dashboard" title="NHL Overview" description="Performance, valuation, and contract context in one working view." actions={<SeasonSelector />} />
    {loading && !data ? <LoadingState rows={9} /> : error ? <ErrorState message="Unable to load the league overview." onRetry={retry} /> : data && <>
      <section className="snapshot" aria-label="League snapshot">
        <div><span>Players tracked</span><strong>{data.league.players}</strong></div>
        <div><span>Player games</span><strong>{data.league.gamesPlayed.toLocaleString()}</strong></div>
        <div><span>Goals</span><strong>{data.league.goals.toLocaleString()}</strong></div>
        <div><span>Avg. Hockey Value</span><strong>{formatNumber(data.league.averageHockeyValue, 1)}</strong></div>
      </section>
      <section className="section-block">
        <div className="section-header"><div><span className="section-index">01</span><h2>Hockey Value leaders</h2></div><Link to={`/players?season=${season}&sort=hockeyValue&order=desc`}>Full leaderboard →</Link></div>
        <PlayerTable players={data.leaders.hockeyValue} compact />
      </section>
      <section className="leader-grid">
        {([['Points', 'points'], ['Goals', 'goals'], ['Game Score / 60', 'gameScorePer60']] as const).map(([title, metric]) => <div className="mini-board" key={metric}><div className="section-header"><h2>{title}</h2></div><ol>{data.leaders[metric].map((player) => <li key={player.id}><span className="mini-rank">{data.leaders[metric].indexOf(player) + 1}</span><Link to={`/players/${player.id}`}>{player.fullName}</Link><small>{player.team?.abbreviation}</small><strong>{formatNumber(player[metric], metric === 'gameScorePer60' ? 2 : 0)}</strong></li>)}</ol></div>)}
      </section>
      <p className="mock-disclaimer">Development dataset for interface testing. Values are illustrative and must not be treated as current NHL records.</p>
    </>}
  </>
}
