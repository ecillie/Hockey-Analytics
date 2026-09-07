import { Link } from 'react-router-dom'
import { api } from '../api'
import { PageHeader } from '../components/common/PageHeader'
import { ErrorState, LoadingState } from '../components/common/States'
import { useApiQuery } from '../hooks/useApiQuery'

export function TeamsPage() {
  const { data, loading, error, retry } = useApiQuery((signal) => api.getTeams(signal), [])
  return <><PageHeader eyebrow="League directory" title="Teams" description="Active NHL organizations and their roster, contract, and cap views." />
    {loading ? <LoadingState rows={12} /> : error ? <ErrorState message="Unable to load teams." onRetry={retry} /> : <div className="team-directory">{data?.map((team) => <Link to={`/teams/${team.id}`} key={team.id} className="team-row"><span className="team-monogram">{team.abbreviation}</span><span><strong>{team.name}</strong><small>{team.city}</small></span><span>Roster & cap <b>→</b></span></Link>)}</div>}
  </>
}
