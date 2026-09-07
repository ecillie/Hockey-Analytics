import { Link } from 'react-router-dom'
import type { PlayerSort, PlayerSummary, SortOrder } from '../../api'
import { formatCurrency, formatNumber } from '../../utils/format'
import { EmptyState } from '../common/States'
import { StatusBadge } from '../common/StatusBadge'

interface Props { players: PlayerSummary[]; sort?: PlayerSort; order?: SortOrder; onSort?: (sort: PlayerSort) => void; compact?: boolean }
const columns: Array<{ key: PlayerSort; label: string; className?: string }> = [
  { key: 'gamesPlayed', label: 'GP' }, { key: 'goals', label: 'G' }, { key: 'assists', label: 'A' }, { key: 'points', label: 'PTS' },
  { key: 'gameScore', label: 'GmSc', className: 'priority-low' }, { key: 'gameScorePer60', label: 'GS/60' }, { key: 'hockeyValue', label: 'HV' },
  { key: 'capHitCents', label: 'Cap hit', className: 'priority-medium' },
]

export function PlayerTable({ players, sort, order, onSort, compact }: Props) {
  if (!players.length) return <EmptyState title="No players found" />
  return <div className="table-scroll"><table className={`data-table ${compact ? 'table-compact' : ''}`}>
    <thead><tr><th className="rank-col">#</th><th className="player-col">Player</th><th>Team</th><th>Pos</th>{columns.map((column) => <th key={column.key} className={`numeric ${column.className ?? ''}`}><button className={sort === column.key ? 'sorted' : ''} onClick={() => onSort?.(column.key)} disabled={!onSort}>{column.label}{sort === column.key && <span>{order === 'asc' ? '↑' : '↓'}</span>}</button></th>)}<th className="priority-medium">Status</th></tr></thead>
    <tbody>{players.map((player, index) => <tr key={player.id}><td className="rank-col muted">{index + 1}</td><td className="player-col"><Link to={`/players/${player.id}`}><strong>{player.fullName}</strong><small>{player.age ?? '—'} years</small></Link></td><td><Link className="team-code" to={player.team ? `/teams/${player.team.id}` : '#'}>{player.team?.abbreviation ?? 'FA'}</Link></td><td>{player.primaryPosition ?? '—'}</td><td className="numeric">{formatNumber(player.gamesPlayed)}</td><td className="numeric">{formatNumber(player.goals)}</td><td className="numeric">{formatNumber(player.assists)}</td><td className="numeric"><strong>{formatNumber(player.points)}</strong></td><td className="numeric priority-low">{formatNumber(player.gameScore, 1)}</td><td className="numeric">{formatNumber(player.gameScorePer60, 2)}</td><td className="numeric value-cell"><strong>{formatNumber(player.hockeyValue, 1)}</strong></td><td className="numeric priority-medium">{formatCurrency(player.capHitCents, true)}</td><td className="priority-medium"><StatusBadge status={player.rosterStatus} /></td></tr>)}</tbody>
  </table></div>
}
