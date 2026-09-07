import { Link, useParams } from 'react-router-dom'
import { api } from '../api'
import { PageHeader } from '../components/common/PageHeader'
import { SeasonSelector } from '../components/common/SeasonSelector'
import { Sparkline } from '../components/common/Sparkline'
import { ErrorState, LoadingState } from '../components/common/States'
import { StatusBadge } from '../components/common/StatusBadge'
import { useSeason } from '../context/SeasonContext'
import { useApiQuery } from '../hooks/useApiQuery'
import { formatCurrency, formatNumber, formatPercent, formatToi, seasonLabel } from '../utils/format'

function Metric({ label, value, note }: { label: string; value: string; note?: string }) {
  return <div className="metric"><span>{label}</span><strong>{value}</strong>{note && <small>{note}</small>}</div>
}

export function PlayerDetailPage() {
  const id = Number(useParams().id)
  const { season } = useSeason()
  const profile = useApiQuery((signal) => api.getPlayer(id, signal), [id])
  const stats = useApiQuery((signal) => api.getPlayerStats(id, season, signal), [id, season])
  const value = useApiQuery((signal) => api.getPlayerValue(id, season, signal), [id, season])
  const history = useApiQuery((signal) => api.getPlayerSeasons(id, signal), [id])
  const contract = useApiQuery((signal) => api.getPlayerContract(id, signal), [id])
  if (profile.loading && !profile.data) return <LoadingState rows={12} />
  if (profile.error || !profile.data) return <ErrorState message="Unable to load this player." onRetry={profile.retry} />
  const player = profile.data
  const current = stats.data
  return <>
    <div className="breadcrumb"><Link to="/players">Players</Link><span>/</span>{player.fullName}</div>
    <PageHeader eyebrow={`${player.team?.abbreviation ?? 'Free agent'} · ${player.primaryPosition ?? 'Position unavailable'}`} title={player.fullName} description={[player.age !== null ? `Age ${player.age}` : null, player.shootsCatches ? `Shoots ${player.shootsCatches}` : null, player.nationality].filter(Boolean).join(' · ')} actions={<div className="detail-actions"><StatusBadge status={player.rosterStatus} /><SeasonSelector compact /></div>} />
    {stats.loading && !current ? <LoadingState rows={4} /> : stats.error ? <ErrorState message="Unable to load season statistics." onRetry={stats.retry} /> : current && <section className="stat-strip">
      {current.traditional ? <><Metric label="GP" value={formatNumber(current.traditional.gamesPlayed)} /><Metric label="G" value={formatNumber(current.traditional.goals)} /><Metric label="A" value={formatNumber(current.traditional.assists)} /><Metric label="PTS" value={formatNumber(current.traditional.points)} /><Metric label="Shots" value={formatNumber(current.traditional.shots)} /><Metric label="SH%" value={formatPercent(current.traditional.shootingPercentage)} /></> : current.goalie && <><Metric label="GP" value={formatNumber(current.goalie.gamesPlayed)} /><Metric label="W" value={formatNumber(current.goalie.wins)} /><Metric label="SV%" value={formatPercent(current.goalie.savePercentage, 3)} /><Metric label="GAA" value={formatNumber(current.goalie.goalsAgainstAverage, 2)} /></>}
    </section>}
    <div className="detail-grid">
      <section className="section-block performance-panel"><div className="section-header"><div><span className="section-index">01</span><h2>Performance</h2></div><span>{seasonLabel(season)} regular season</span></div>
        {current?.advanced ? <div className="metric-grid"><Metric label="Game Score" value={formatNumber(current.advanced.gameScore, 1)} /><Metric label="Game Score / 60" value={formatNumber(current.advanced.gameScorePer60, 2)} /><Metric label="Expected goals / 60" value={formatNumber(current.advanced.expectedGoalsPer60, 2)} /><Metric label="On-ice xG share" value={formatPercent(current.advanced.onIceExpectedGoalsPercentage)} /><Metric label="Time on ice" value={formatToi(current.advanced.iceTimeSeconds)} note="hours:minutes" /><Metric label="Penalty differential" value={formatNumber((current.advanced.penaltiesDrawn ?? 0) - (current.advanced.penalties ?? 0))} /></div> : <p className="muted">Advanced skater statistics are not available.</p>}
      </section>
      <section className="section-block value-panel"><div className="section-header"><div><span className="section-index">02</span><h2>Hockey Value</h2></div></div>
        {value.data ? <><div className="value-focus"><div><span>Current value</span><strong>{formatNumber(value.data.hockeyValue, 1)}</strong></div><div><span>Next-season projection</span><strong>{formatNumber(value.data.projectedNextSeasonHockeyValue, 1)}</strong></div></div><div className="value-formula"><span>GS/60 above replacement</span><strong>{formatNumber(value.data.gameScorePer60AboveReplacement, 2)}</strong><span>× TOI hours</span><strong>{formatNumber(value.data.toiHours, 1)}</strong></div>{history.data && <Sparkline values={history.data.map((row) => row.hockeyValue)} />}</> : <LoadingState rows={2} />}
      </section>
      <section className="section-block contract-panel"><div className="section-header"><div><span className="section-index">03</span><h2>Contract</h2></div></div>
        {contract.data ? <><div className="contract-summary"><Metric label="Cap hit" value={formatCurrency(contract.data.averageValueCents)} /><Metric label="Term" value={`${contract.data.termYears} years`} /><Metric label="Expires" value={`${seasonLabel(contract.data.endSeason)} ${contract.data.expiryStatus ?? ''}`} /></div><table className="data-table"><thead><tr><th>Season</th><th className="numeric">Base salary</th><th className="numeric">Cap hit</th><th className="numeric">Cap %</th></tr></thead><tbody>{contract.data.seasons.map((row) => <tr key={row.season}><td>{seasonLabel(row.season)}</td><td className="numeric">{formatCurrency(row.baseSalaryCents)}</td><td className="numeric">{formatCurrency(row.capHitCents)}</td><td className="numeric">{formatPercent(row.capPercentage)}</td></tr>)}</tbody></table></> : contract.loading ? <LoadingState rows={3} /> : <p className="muted">No active contract is available.</p>}
      </section>
      <section className="section-block history-panel"><div className="section-header"><div><span className="section-index">04</span><h2>Season history</h2></div></div>
        {history.data && <div className="table-scroll"><table className="data-table"><thead><tr><th>Season</th><th>Team</th><th className="numeric">GP</th><th className="numeric">G</th><th className="numeric">A</th><th className="numeric">PTS</th><th className="numeric">GS/60</th><th className="numeric">HV</th></tr></thead><tbody>{history.data.slice().reverse().map((row) => <tr key={row.season}><td>{seasonLabel(row.season)}</td><td>{row.team?.abbreviation ?? '—'}</td><td className="numeric">{formatNumber(row.gamesPlayed)}</td><td className="numeric">{formatNumber(row.goals)}</td><td className="numeric">{formatNumber(row.assists)}</td><td className="numeric">{formatNumber(row.points)}</td><td className="numeric">{formatNumber(row.gameScorePer60, 2)}</td><td className="numeric value-cell">{formatNumber(row.hockeyValue, 1)}</td></tr>)}</tbody></table></div>}
      </section>
    </div>
  </>
}
