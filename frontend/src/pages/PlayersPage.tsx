import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api, type PlayerFilters, type PlayerSort, type Position, type RosterStatus } from '../api'
import { PageHeader } from '../components/common/PageHeader'
import { Pagination } from '../components/common/Pagination'
import { SeasonSelector } from '../components/common/SeasonSelector'
import { ErrorState, LoadingState } from '../components/common/States'
import { PlayerTable } from '../components/players/PlayerTable'
import { useSeason } from '../context/SeasonContext'
import { useApiQuery } from '../hooks/useApiQuery'

export function PlayersPage() {
  const { season: globalSeason } = useSeason()
  const [searchParams, setSearchParams] = useSearchParams()
  const [searchInput, setSearchInput] = useState(searchParams.get('search') ?? '')
  const params = useMemo<PlayerFilters>(() => ({
    season: Number(searchParams.get('season')) || globalSeason,
    team: searchParams.get('team') || undefined,
    position: (searchParams.get('position') as Position) || undefined,
    rosterStatus: (searchParams.get('rosterStatus') as RosterStatus) || undefined,
    search: searchParams.get('search') || undefined,
    sort: (searchParams.get('sort') as PlayerSort) || 'hockeyValue',
    order: searchParams.get('order') === 'asc' ? 'asc' : 'desc',
    page: Math.max(1, Number(searchParams.get('page')) || 1),
    pageSize: 10,
  }), [searchParams, globalSeason])
  const { data, loading, error, retry } = useApiQuery((signal) => api.getPlayers(params, signal), [JSON.stringify(params)])
  const teams = useApiQuery((signal) => api.getTeams(signal), [])
  const update = (key: string, value?: string | number) => {
    setSearchParams((current) => { const next = new URLSearchParams(current); if (value === undefined || value === '') next.delete(key); else next.set(key, String(value)); if (key !== 'page') next.set('page', '1'); return next })
  }
  // The debounced update intentionally reads the latest URLSearchParams snapshot.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { const timer = window.setTimeout(() => update('search', searchInput.trim()), 300); return () => window.clearTimeout(timer) }, [searchInput])
  const sort = (key: PlayerSort) => {
    const nextOrder = params.sort === key && params.order === 'desc' ? 'asc' : 'desc'
    setSearchParams((current) => { const next = new URLSearchParams(current); next.set('sort', key); next.set('order', nextOrder); next.set('page', '1'); return next })
  }
  return <>
    <PageHeader eyebrow="Player database" title="Players" description="Filter, sort, and reproduce any league view through the URL." actions={<SeasonSelector value={params.season} onChange={(value) => update('season', value)} />} />
    <section className="filter-bar">
      <label className="filter-search"><span>Search</span><input value={searchInput} placeholder="Player name" onChange={(e) => setSearchInput(e.target.value)} /></label>
      <label><span>Team</span><select value={params.team ?? ''} onChange={(e) => update('team', e.target.value)}><option value="">All teams</option>{teams.data?.map((team) => <option value={team.abbreviation} key={team.id}>{team.abbreviation} — {team.name}</option>)}</select></label>
      <label><span>Position</span><select value={params.position ?? ''} onChange={(e) => update('position', e.target.value)}><option value="">All positions</option>{['C', 'LW', 'RW', 'D', 'G'].map((position) => <option key={position}>{position}</option>)}</select></label>
      <label><span>Roster</span><select value={params.rosterStatus ?? ''} onChange={(e) => update('rosterStatus', e.target.value)}><option value="">All statuses</option><option value="ACTIVE">NHL</option><option value="MINORS">Minors</option><option value="LTIR">LTIR</option><option value="UNKNOWN">Unknown</option></select></label>
      <button className="reset-button" onClick={() => { setSearchInput(''); setSearchParams({ season: String(params.season), sort: 'hockeyValue', order: 'desc' }) }}>Reset</button>
    </section>
    <div className="results-meta"><span>{data ? `${data.pagination.totalItems} players` : 'Loading players'}</span><span>Sorted by {params.sort} · {params.order}</span></div>
    {loading && !data ? <LoadingState rows={10} /> : error ? <ErrorState message="Unable to load player statistics." onRetry={retry} /> : data && <><PlayerTable players={data.data} sort={params.sort} order={params.order} onSort={sort} /><Pagination {...data.pagination} onChange={(page) => update('page', page)} /></>}
  </>
}
