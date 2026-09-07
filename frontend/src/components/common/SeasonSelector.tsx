import { useSeason } from '../../context/SeasonContext'
import { seasonLabel } from '../../utils/format'

export function SeasonSelector({ value, onChange, compact = false }: { value?: number; onChange?: (season: number) => void; compact?: boolean }) {
  const { season, setSeason, info } = useSeason()
  const selected = value ?? season
  const change = onChange ?? setSeason
  return <label className={`season-select ${compact ? 'compact' : ''}`}><span>Season</span><select aria-label="Season" value={selected} onChange={(event) => change(Number(event.target.value))}>{(info?.availableSeasons ?? [{ startYear: 2025, endYear: 2026, label: '2025-26', salaryCapCents: null }]).slice().reverse().map((item) => <option value={item.startYear} key={item.startYear}>{seasonLabel(item.startYear)}</option>)}</select></label>
}
