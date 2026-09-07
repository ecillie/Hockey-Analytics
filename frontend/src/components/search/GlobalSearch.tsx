import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, type SearchResponse } from '../../api'
import { Icon } from '../common/Icon'

export function GlobalSearch() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResponse | null>(null)
  const [open, setOpen] = useState(false)
  const navigate = useNavigate()
  const root = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (query.trim().length < 2) return
    const controller = new AbortController()
    const timer = window.setTimeout(() => api.search(query, undefined, 8, controller.signal).then(setResults).catch(() => setResults({ players: [], teams: [] })), 250)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [query])
  useEffect(() => {
    const close = (event: MouseEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])
  const submit = (event: FormEvent) => { event.preventDefault(); if (query.trim()) { navigate(`/players?search=${encodeURIComponent(query.trim())}`); setOpen(false) } }
  const hasResults = Boolean(results && (results.players.length || results.teams.length))
  return <div className="global-search" ref={root}>
    <form onSubmit={submit}><Icon name="search" /><input aria-label="Search players and teams" placeholder="Search players or teams" value={query} onChange={(e) => { setQuery(e.target.value); setOpen(true) }} onFocus={() => setOpen(true)} /></form>
    {open && query.length >= 2 && <div className="search-results">
      {!results && <div className="search-message">Searching…</div>}
      {results?.players.map((player) => <Link key={`p-${player.id}`} to={`/players/${player.id}`} onClick={() => setOpen(false)}><span><strong>{player.fullName}</strong><small>{player.team?.abbreviation ?? 'FA'} · {player.primaryPosition ?? '—'}</small></span><Icon name="arrow" /></Link>)}
      {results?.teams.map((team) => <Link key={`t-${team.id}`} to={`/teams/${team.id}`} onClick={() => setOpen(false)}><span><strong>{team.name}</strong><small>{team.abbreviation}</small></span><Icon name="arrow" /></Link>)}
      {results && !hasResults && <div className="search-message">No matching players or teams.</div>}
      {hasResults && <button type="button" onClick={() => navigate(`/players?search=${encodeURIComponent(query)}`)}>View all player results</button>}
    </div>}
  </div>
}
