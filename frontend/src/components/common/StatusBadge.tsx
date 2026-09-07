import type { RosterStatus } from '../../api'
export function StatusBadge({ status }: { status: RosterStatus }) {
  return <span className={`status status-${status.toLowerCase()}`}>{status === 'ACTIVE' ? 'NHL' : status}</span>
}
