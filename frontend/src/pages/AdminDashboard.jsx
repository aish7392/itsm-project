import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { Bars, ErrorBox, IncidentTable, PriorityBadge, Stat, StatusBadge, useAsync } from '../components/ui'

function Trend({ data }) {
  if (!data?.length) return null
  const max = Math.max(1, ...data.flatMap(d => [d.created, d.resolved]))
  return (
    <div className="trend">
      {data.map(d => (
        <div className="trend-col" key={d.date} title={`${d.date}: ${d.created} created, ${d.resolved} resolved`}>
          <div className="trend-bars">
            <span className="tb created" style={{ height: `${(d.created / max) * 100}%` }} />
            <span className="tb resolved" style={{ height: `${(d.resolved / max) * 100}%` }} />
          </div>
          <span className="trend-x">{d.date.slice(8)}</span>
        </div>
      ))}
    </div>
  )
}

export default function AdminDashboard() {
  const ov = useAsync(() => api.get('/reports/overview'), [])
  const wl = useAsync(() => api.get('/reports/workload'), [])
  const sv = useAsync(() => api.get('/reports/services'), [])
  const cl = useAsync(() => api.get('/reports/clusters'), [])
  const risky = useAsync(() => api.get('/incidents?sla_status=AT_RISK'), [])
  const breached = useAsync(() => api.get('/incidents?sla_status=BREACHED&active_only=true'), [])
  const [monitor, setMonitor] = useState(null)
  const o = ov.data || {}

  const runMonitor = async () => {
    setMonitor(await api.post('/admin/sla/run'))
    ;[ov, wl, sv, cl, risky, breached].forEach(x => x.reload())
  }

  return (
    <>
      <div className="page-head">
        <div><h1>Operations dashboard</h1><p className="muted">Live service health, SLA compliance and technician load.</p></div>
        <div className="actions">
          {monitor && <span className="muted sm">Checked {monitor.checked} · {monitor.warnings} warnings · {monitor.violations} violations · {monitor.escalations} escalations</span>}
          <button className="btn ghost" onClick={runMonitor}>Run SLA check now</button>
        </div>
      </div>
      <ErrorBox error={ov.error} />
      <div className="stats six">
        <Stat label="Total incidents" value={o.total} />
        <Stat label="Open" value={o.open} />
        <Stat label="Critical (P1) open" value={o.critical_open} tone={o.critical_open ? 'bad' : ''} />
        <Stat label="Resolved" value={o.resolved} tone="ok" />
        <Stat label="SLA violations" value={o.sla_violations} tone={o.sla_violations ? 'bad' : ''} sub={`${o.at_risk ?? 0} at risk now`} />
        <Stat label="SLA compliance" value={o.sla_compliance_pct != null ? `${o.sla_compliance_pct}%` : '—'}
          sub={`Avg resolve ${o.avg_resolution_hours ?? '—'}h · CSAT ${o.avg_feedback ?? '—'}/5`} />
      </div>

      {cl.data?.length > 0 && (
        <section className="card alert-card">
          <h3>Correlated incident clusters <span className="muted sm">— possible major incidents / duplicates</span></h3>
          {cl.data.map((c, idx) => (
            <div className="cluster" key={idx}>
              <div className="cluster-head"><PriorityBadge p={c.highest_priority} /> <strong>{c.size} related incidents</strong> <span className="muted">on {c.services.join(', ')}</span></div>
              <div className="cluster-items">
                {c.incidents.map(i => <Link key={i.id} to={`/incidents/${i.id}`} className="chip">{i.code} · {i.title} <StatusBadge s={i.status} /></Link>)}
              </div>
            </div>
          ))}
        </section>
      )}

      <div className="grid-3">
        <section className="card"><h3>By priority</h3><Bars data={o.by_priority} tone="accent" /></section>
        <section className="card"><h3>By status</h3><Bars data={o.by_status} /></section>
        <section className="card"><h3>By category</h3><Bars data={o.by_category} /></section>
      </div>

      <div className="grid-2">
        <section className="card">
          <h3>Last 14 days <span className="legend"><i className="lg created" />created <i className="lg resolved" />resolved</span></h3>
          <Trend data={o.trend} />
        </section>
        <section className="card">
          <h3>Service analysis</h3>
          <table className="table compact">
            <thead><tr><th>Service</th><th>Total</th><th>Open</th><th>P1</th><th>Breached</th></tr></thead>
            <tbody>{(sv.data || []).map(r => (
              <tr key={r.service}><td>{r.service}</td><td>{r.total}</td><td>{r.open}</td><td>{r.p1}</td><td className={r.breached ? 'bad-text' : ''}>{r.breached}</td></tr>
            ))}</tbody>
          </table>
        </section>
      </div>

      <section className="card">
        <h3>Technician workload</h3>
        <table className="table compact">
          <thead><tr><th>Technician</th><th>Skills</th><th>Active</th><th>Utilisation</th><th>Resolved</th><th>Breaches</th><th>Status</th></tr></thead>
          <tbody>{(wl.data || []).map(t => (
            <tr key={t.id}>
              <td><span className="mono muted">{t.code}</span> {t.name} {t.team_lead && <span className="tag">lead</span>}</td>
              <td className="muted sm">{t.skills.join(', ')}</td>
              <td>{t.active} / {t.max_workload}</td>
              <td style={{ minWidth: 140 }}><div className="meter"><span style={{ width: `${Math.min(t.utilisation_pct, 100)}%` }} className={t.utilisation_pct >= 100 ? 'full' : t.utilisation_pct >= 70 ? 'high' : ''} /></div></td>
              <td>{t.resolved}</td>
              <td className={t.breached ? 'bad-text' : ''}>{t.breached}</td>
              <td>{t.available ? <span className="ok-text">Available</span> : <span className="muted">Offline</span>}</td>
            </tr>
          ))}</tbody>
        </table>
      </section>

      <div className="grid-2">
        <section className="card"><h3>SLA breached (open)</h3><IncidentTable rows={breached.data} showReporter={false} empty="No open breaches." /></section>
        <section className="card"><h3>SLA at risk</h3><IncidentTable rows={risky.data} showReporter={false} empty="Nothing at risk right now." /></section>
      </div>
    </>
  )
}
