export function Sparkline({ values }: { values: Array<number | null> }) {
  const valid = values.map((value) => value ?? 0)
  const min = Math.min(...valid), max = Math.max(...valid), spread = max - min || 1
  const points = valid.map((value, i) => `${(i / Math.max(1, valid.length - 1)) * 160},${42 - ((value - min) / spread) * 34}`).join(' ')
  return <svg className="sparkline" viewBox="0 0 160 48" role="img" aria-label={`Trend from ${valid[0]} to ${valid.at(-1)}`}><path d="M0 43H160" className="sparkline-grid"/><polyline points={points} /></svg>
}
