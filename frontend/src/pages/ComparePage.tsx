import { useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { PageHeader } from '../components/common/PageHeader'
import { SeasonSelector } from '../components/common/SeasonSelector'
import { ErrorState, LoadingState } from '../components/common/States'
import { useSeason } from '../context/SeasonContext'
import { useApiQuery } from '../hooks/useApiQuery'
import { formatCurrency, formatNumber } from '../utils/format'

export function ComparePage() {
  const { season } = useSeason()
  const [params, setParams] = useSearchParams()
  const allPlayers = useApiQuery((signal) => api.getPlayers({ season, pageSize: 100, sort: 'hockeyValue' }, signal), [season])
  const ids = useMemo(() => (params.get('ids') ?? '101,102').split(',').map(Number).filter(Boolean).slice(0, 4), [params])
  const comparison = useApiQuery((signal) => ids.length >= 2 ? api.comparePlayers(ids, season, signal) : Promise.reject(new Error('Select at least two players.')), [ids.join(','), season])
  const toggle = (id: number) => {
    const next = ids.includes(id) ? ids.filter((value) => value !== id) : [...ids, id].slice(-4)
    setParams({ ids: next.join(',') })
  }
  const rows = comparison.data ? [
    ['Hockey Value', (i: number) => formatNumber(comparison.data!.players[i].value?.hockeyValue, 1)],
    ['Projected HV', (i: number) => formatNumber(comparison.data!.players[i].value?.projectedNextSeasonHockeyValue, 1)],
    ['Games played', (i: number) => formatNumber(comparison.data!.players[i].stats.traditional?.gamesPlayed)],
    ['Goals', (i: number) => formatNumber(comparison.data!.players[i].stats.traditional?.goals)],
    ['Assists', (i: number) => formatNumber(comparison.data!.players[i].stats.traditional?.assists)],
    ['Points', (i: number) => formatNumber(comparison.data!.players[i].stats.traditional?.points)],
    ['Game Score / 60', (i: number) => formatNumber(comparison.data!.players[i].stats.advanced?.gameScorePer60, 2)],
    ['On-ice xG share', (i: number) => formatNumber((comparison.data!.players[i].stats.advanced?.onIceExpectedGoalsPercentage ?? 0) * 100, 1) + '%'],
    ['Cap hit', (i: number) => formatCurrency(comparison.data!.players[i].contract?.averageValueCents, true)],
  ] as const : []
  return <>
    <PageHeader eyebrow="Decision workspace" title="Player comparison" description="Compare two to four players using the same season and valuation definitions." actions={<SeasonSelector />} />
    <section className="compare-picker"><span>Selected players</span><div>{allPlayers.data?.data.map((player) => <button key={player.id} className={ids.includes(player.id) ? 'selected' : ''} onClick={() => toggle(player.id)} disabled={!ids.includes(player.id) && ids.length >= 4}>{player.fullName}<small>{player.team?.abbreviation} · {player.primaryPosition}</small></button>)}</div></section>
    {comparison.loading ? <LoadingState rows={10} /> : comparison.error ? <ErrorState message={ids.length < 2 ? 'Select at least two players.' : 'Unable to build this comparison.'} onRetry={comparison.retry} /> : comparison.data && <div className="table-scroll"><table className="comparison-table"><thead><tr><th>Metric</th>{comparison.data.players.map(({ player }) => <th key={player.id}><span>{player.team?.abbreviation} · {player.primaryPosition}</span><strong>{player.fullName}</strong></th>)}</tr></thead><tbody>{rows.map(([label, value]) => <tr key={label}><th>{label}</th>{comparison.data!.players.map((item, i) => <td key={item.player.id}>{value(i)}</td>)}</tr>)}</tbody></table></div>}
  </>
}
