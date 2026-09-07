export const formatCurrency = (cents: number | null | undefined, compact = false) => {
  if (cents == null) return '—'
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', notation: compact ? 'compact' : 'standard', maximumFractionDigits: compact ? 2 : 0 }).format(cents / 100)
}
export const formatNumber = (value: number | null | undefined, digits = 0) => value == null ? '—' : value.toFixed(digits)
export const formatPercent = (value: number | null | undefined, digits = 1) => value == null ? '—' : `${(value * 100).toFixed(digits)}%`
export const formatToi = (seconds: number | null | undefined) => seconds == null ? '—' : `${Math.floor(seconds / 3600)}:${String(Math.floor((seconds % 3600) / 60)).padStart(2, '0')}`
export const seasonLabel = (startYear: number) => `${startYear}–${String(startYear + 1).slice(-2)}`
