import { describe, expect, it } from 'vitest'
import { formatCurrency, formatNumber, formatPercent, formatToi, seasonLabel } from './format'

describe('format helpers', () => {
  it('formats present values in standard and compact forms', () => {
    expect(formatCurrency(12_500_000)).toBe('$125,000')
    expect(formatCurrency(1_250_000_000, true)).toBe('$12.50M')
    expect(formatNumber(2.345, 2)).toBe('2.35')
    expect(formatPercent(.9234, 3)).toBe('92.340%')
    expect(formatToi(7_440)).toBe('2:04')
    expect(seasonLabel(2025)).toBe('2025–26')
  })

  it('uses a dash for missing values', () => {
    expect(formatCurrency(null)).toBe('—')
    expect(formatNumber(undefined)).toBe('—')
    expect(formatPercent(null)).toBe('—')
    expect(formatToi(undefined)).toBe('—')
  })
})
