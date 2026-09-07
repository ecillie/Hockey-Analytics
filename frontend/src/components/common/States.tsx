export function LoadingState({ rows = 5 }: { rows?: number }) {
  return <div className="loading-state" aria-label="Loading"><span className="loading-line wide" />{Array.from({ length: rows }, (_, i) => <span className="loading-line" key={i} />)}</div>
}
export function ErrorState({ message = 'Unable to load this data.', onRetry }: { message?: string; onRetry?: () => void }) {
  return <div className="state-box" role="alert"><strong>{message}</strong><p>Check the connection and try again.</p>{onRetry && <button className="button" onClick={onRetry}>Try again</button>}</div>
}
export function EmptyState({ title = 'No results', message = 'Adjust the filters and try again.' }: { title?: string; message?: string }) {
  return <div className="state-box"><strong>{title}</strong><p>{message}</p></div>
}
