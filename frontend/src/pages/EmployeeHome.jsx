import { Link } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { ErrorBox, IncidentTable, Stat, useAsync } from '../components/ui'

export default function EmployeeHome() {
  const { user } = useAuth()
  const { data, error } = useAsync(() => api.get('/incidents'), [])
  const rows = data || []
  const open = rows.filter(i => !['RESOLVED', 'VERIFIED', 'CLOSED'].includes(i.status))
  const waiting = rows.filter(i => i.status === 'AWAITING_INFO')
  const toVerify = rows.filter(i => i.status === 'RESOLVED')

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Hello, {user.name.split(' ')[0]}</h1>
          <p className="muted">Track everything you've reported to IT.</p>
        </div>
        <Link to="/report" className="btn primary">+ Report an incident</Link>
      </div>
      <ErrorBox error={error} />
      <div className="stats">
        <Stat label="Open" value={open.length} />
        <Stat label="Needs your reply" value={waiting.length} tone={waiting.length ? 'warn' : ''} />
        <Stat label="Awaiting your confirmation" value={toVerify.length} tone={toVerify.length ? 'ok' : ''} />
        <Stat label="Total reported" value={rows.length} />
      </div>
      {(waiting.length > 0 || toVerify.length > 0) && (
        <div className="callout">
          {waiting.map(i => <div key={i.id}>Support asked a question on <Link to={`/incidents/${i.id}`}>{i.code} – {i.title}</Link>.</div>)}
          {toVerify.map(i => <div key={i.id}><Link to={`/incidents/${i.id}`}>{i.code}</Link> was resolved – please confirm the fix and leave feedback.</div>)}
        </div>
      )}
      <section className="card">
        <h3>My incidents</h3>
        <IncidentTable rows={rows} showReporter={false} empty="You haven't reported anything yet." />
      </section>
    </>
  )
}
