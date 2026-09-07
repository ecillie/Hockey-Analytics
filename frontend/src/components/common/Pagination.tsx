export function Pagination({ page, totalPages, totalItems, onChange }: { page: number; totalPages: number; totalItems: number; onChange: (page: number) => void }) {
  return <div className="pagination"><span>{totalItems} results · Page {page} of {Math.max(1, totalPages)}</span><div><button disabled={page <= 1} onClick={() => onChange(page - 1)}>Previous</button><button disabled={page >= totalPages} onClick={() => onChange(page + 1)}>Next</button></div></div>
}
