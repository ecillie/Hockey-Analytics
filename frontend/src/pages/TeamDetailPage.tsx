import { Link, useParams } from 'react-router-dom'
import { api, type RosterStatus } from '../api'
import { PageHeader } from '../components/common/PageHeader'
import { SeasonSelector } from '../components/common/SeasonSelector'
import { ErrorState, LoadingState } from '../components/common/States'
import { PlayerTable } from '../components/players/PlayerTable'
import { useSeason } from '../context/SeasonContext'
import { useApiQuery } from '../hooks/useApiQuery'
import { formatCurrency, formatPercent, seasonLabel } from '../utils/format'

export function TeamDetailPage() {
  const id = Number(useParams().id)
  const { season } = useSeason()
  const team = useApiQuery((signal) => api.getTeam(id, signal), [id])
  const roster = useApiQuery((signal) => api.getTeamRoster(id, { season }, signal), [id, season])
  const contracts = useApiQuery((signal) => api.getTeamContracts(id, season, signal), [id, season])
  const cap = useApiQuery((signal) => api.getTeamCap(id, season, signal), [id, season])
  if (team.loading) return <LoadingState rows={12} />
  if (!team.data || team.error) return <ErrorState message="Unable to load this team." onRetry={team.retry} />
  const statuses: Array<[RosterStatus, string]> = [['ACTIVE', 'NHL'], ['MINORS', 'Minors'], ['LTIR', 'LTIR'], ['UNKNOWN', 'Unknown']]
  return <>
    <div className="breadcrumb"><Link to="/teams">Teams</Link><span>/</span>{team.data.name}</div>
    <PageHeader eyebrow={team.data.abbreviation} title={team.data.name} description={`${team.data.city ?? ''} · Active organization`} actions={<SeasonSelector />} />
    <section className="team-status-strip">{statuses.map(([status, label]) => <div key={status}><span>{label}</span><strong>{team.data?.rosterCounts[status] ?? 0}</strong></div>)}</section>
    {cap.data && <section className="cap-band"><div><span>Salary cap</span><strong>{formatCurrency(cap.data.salaryCapCents, true)}</strong></div><div><span>Active roster</span><strong>{formatCurrency(cap.data.activeRosterCapCents, true)}</strong></div><div><span>Total commitments</span><strong>{formatCurrency(cap.data.totalCommitmentsCents, true)}</strong></div><div><span>Projected space</span><strong className={(cap.data.capSpaceCents ?? 0) < 0 ? 'negative' : 'positive'}>{formatCurrency(cap.data.capSpaceCents, true)}</strong></div><small>{cap.data.calculationStatus === 'ESTIMATE' ? 'Development estimate — backend cap engine required' : 'Authoritative calculation'}</small></section>}
    <section className="section-block"><div className="section-header"><div><span className="section-index">01</span><h2>Organization roster</h2></div><span>{seasonLabel(season)}</span></div>{roster.loading ? <LoadingState /> : roster.error ? <ErrorState message="Unable to load the roster." onRetry={roster.retry} /> : <PlayerTable players={roster.data?.players ?? []} />}</section>
    <section className="section-block"><div className="section-header"><div><span className="section-index">02</span><h2>Contract ledger</h2></div><span>{contracts.data?.contracts.length ?? 0} contracts</span></div>
      {contracts.loading ? <LoadingState /> : contracts.error ? <ErrorState message="Unable to load team contracts." onRetry={contracts.retry} /> : <div className="table-scroll"><table className="data-table"><thead><tr><th>Player</th><th>Pos</th><th>Expiry</th><th className="numeric">Cap hit</th><th className="numeric">Cap %</th><th className="numeric">Cash</th></tr></thead><tbody>{contracts.data?.contracts.map(({ player, contract, season: contractSeason }) => <tr key={player.id}><td><Link to={`/players/${player.id}`}><strong>{player.fullName}</strong></Link></td><td>{player.primaryPosition}</td><td>{seasonLabel(contract.endSeason)} {contract.expiryStatus}</td><td className="numeric">{formatCurrency(contractSeason.capHitCents)}</td><td className="numeric">{formatPercent(contractSeason.capPercentage)}</td><td className="numeric">{formatCurrency(contractSeason.totalCashCents)}</td></tr>)}</tbody></table></div>}
    </section>
  </>
}
