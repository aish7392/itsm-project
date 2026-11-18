import { api } from '../api'
import { useAuth } from '../auth'
import { ErrorBox, IncidentTable, Stat, useAsync } from '../components/ui'

export default function TechnicianHome() {
  const { user } = useAuth()
  const wl = useAsync(() => api.get('/me/workload'), [])
  const all = useAsync(() => api.get('/incidents'), [])
  const rows = all.data || []
  const newOnes = rows.filter(i => i.status === 'ASSIGNED')
  const atRisk = rows.filter(i => ['AT_RISK', 'BREACHED'].includes(i.sla_state) && i.status !== 'CLOSED')
  const done = rows.filter(i => ['RESOLVED', 'VERIFIED', 'CLOSED'].includes(i.status))
  const w = wl.data
  const pct = w ? Math.round((w.active / w.max_workload) * 100) : 0

  const toggle = async () => { await api.post('/me/availability'); wl.reload() }

  return (
    <>
      <div className="page-head">
        <div><h1>My queue</h1><p className="muted">Skills: {(user.skills || []).join(' · ') || '—'}</p></div>
        {w && <button className={`btn ${w.is_available ? 'ghost' : 'danger'}`} onClick={toggle}>
          {w.is_available ? '● Available — go offline' : '○ Offline — go available'}</button>}
      </div>
      <ErrorBox error={wl.error || all.error} />
      <div className="stats">
        <div className="stat">
          <div className="stat-label">Workload</div>
          <div className="stat-value">{w ? `${w.active} / ${w.max_workload}` : '—'}</div>
          <div className="meter"><span style={{ width: `${Math.min(pct, 100)}%` }} className={pct >= 100 ? 'full' : pct >= 70 ? 'high' : ''} /></div>
        </div>
        <Stat label="Waiting for acceptance" value={newOnes.length} tone={newOnes.length ? 'warn' : ''} />
        <Stat label="SLA at risk / breached" value={atRisk.length} tone={atRisk.length ? 'bad' : ''} />
        <Stat label="Resolved by me" value={w?.resolved ?? done.length} tone="ok" />
      </div>
      <section className="card">
        <h3>Active incidents</h3>
        <IncidentTable rows={rows.filter(i => !['RESOLVED', 'VERIFIED', 'CLOSED'].includes(i.status))} showTech={false} empty="Queue is empty. Nice." />
      </section>
      <section className="card">
        <h3>Recently resolved</h3>
        <IncidentTable rows={done} showTech={false} empty="Nothing resolved yet." />
      </section>
    </>
  )
}
