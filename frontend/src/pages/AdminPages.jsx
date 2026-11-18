import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, qs } from '../api'
import { useAuth } from '../auth'
import { ErrorBox, PriorityBadge, ago, fmt, human, useAsync } from '../components/ui'

function Page({ title, sub, children }) {
  return <><div className="page-head"><div><h1>{title}</h1>{sub && <p className="muted">{sub}</p>}</div></div>{children}</>
}

function useSubmit(after) {
  const [error, setError] = useState(null)
  const run = async (fn) => {
    setError(null)
    try { await fn(); after?.(); return true } catch (e) { setError(e); return false }
  }
  return [error, run]
}

// ─────────────────────────────── users ───────────────────────────────
const NEW_USER = { role: 'TECHNICIAN', name: '', email: '', password: '', department: '', skills: '', max_workload: 5, is_team_lead: false, experience_years: 1, title: 'SYSTEM_ADMIN' }

export function UsersPage() {
  const { meta, reloadMeta } = useAuth()
  const [role, setRole] = useState('')
  const users = useAsync(() => api.get(`/admin/users${qs({ role })}`), [role])
  const [f, setF] = useState(NEW_USER)
  const [error, run] = useSubmit(() => { users.reload(); reloadMeta() })
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })

  const create = (e) => {
    e.preventDefault()
    const body = { role: f.role, name: f.name, email: f.email, password: f.password, department: f.department || null }
    if (f.role === 'TECHNICIAN') Object.assign(body, { skills: f.skills.split(/[,\s]+/).filter(Boolean), max_workload: +f.max_workload, is_team_lead: f.is_team_lead, experience_years: +f.experience_years })
    if (f.role === 'ADMIN') body.title = f.title
    run(async () => { await api.post('/admin/users', body); setF(NEW_USER) })
  }
  const patch = (u, body) => run(() => api.patch(`/admin/users/${u.id}`, body))

  return (
    <Page title="Users & technicians" sub="Create accounts, manage technician skills, capacity and availability.">
      <ErrorBox error={error} />
      <form className="card form" onSubmit={create}>
        <h3>New user</h3>
        <div className="row">
          <label>Role<select value={f.role} onChange={set('role')}><option>EMPLOYEE</option><option>TECHNICIAN</option><option>ADMIN</option></select></label>
          <label>Name<input value={f.name} onChange={set('name')} required /></label>
          <label>Email<input type="email" value={f.email} onChange={set('email')} required /></label>
          <label>Temp password<input value={f.password} onChange={set('password')} required placeholder="min 8, letters+digits" /></label>
          <label>Department<input value={f.department} onChange={set('department')} /></label>
        </div>
        {f.role === 'TECHNICIAN' && (
          <div className="row">
            <label className="grow">Skills (categories)<input value={f.skills} onChange={set('skills')} placeholder={meta?.categories.map(c => c.code).slice(0, 4).join(', ')} /></label>
            <label className="narrow">Max workload<input type="number" min={1} value={f.max_workload} onChange={set('max_workload')} /></label>
            <label className="narrow">Experience (yrs)<input type="number" min={0} value={f.experience_years} onChange={set('experience_years')} /></label>
            <label className="check"><input type="checkbox" checked={f.is_team_lead} onChange={set('is_team_lead')} /> Team lead</label>
          </div>
        )}
        {f.role === 'ADMIN' && <div className="row"><label>Title<select value={f.title} onChange={set('title')}><option>SYSTEM_ADMIN</option><option>IT_MANAGER</option></select></label></div>}
        <button className="btn primary">Create user</button>
      </form>
      <section className="card">
        <div className="card-head"><h3>All users</h3>
          <select value={role} onChange={e => setRole(e.target.value)}><option value="">All roles</option><option>EMPLOYEE</option><option>TECHNICIAN</option><option>ADMIN</option></select></div>
        <table className="table compact">
          <thead><tr><th>ID</th><th>Name</th><th>Email</th><th>Role</th><th>Skills / title</th><th>Load</th><th>Available</th><th>Active</th></tr></thead>
          <tbody>{(users.data || []).map(u => (
            <tr key={u.id} className={u.is_active ? '' : 'dim'}>
              <td className="mono">{u.code}</td>
              <td>{u.name} {u.is_team_lead && <span className="tag">lead</span>}</td>
              <td className="muted">{u.email}</td>
              <td><span className={`role-pill r-${u.role.toLowerCase()}`}>{human(u.role)}</span></td>
              <td className="sm">{u.role === 'TECHNICIAN'
                ? <input className="inline-edit" defaultValue={u.skills.join(', ')} onBlur={e => e.target.value !== u.skills.join(', ') && patch(u, { skills: e.target.value.split(/[,\s]+/).filter(Boolean) })} />
                : u.title ? human(u.title) : '—'}</td>
              <td>{u.role === 'TECHNICIAN' ? <span>{u.workload} / <input type="number" min={1} className="inline-num" defaultValue={u.max_workload} onBlur={e => +e.target.value !== u.max_workload && patch(u, { max_workload: +e.target.value })} /></span> : '—'}</td>
              <td>{u.role === 'TECHNICIAN' ? <input type="checkbox" checked={u.is_available} onChange={e => patch(u, { is_available: e.target.checked })} /> : '—'}</td>
              <td><input type="checkbox" checked={u.is_active} onChange={e => patch(u, { is_active: e.target.checked })} /></td>
            </tr>
          ))}</tbody>
        </table>
      </section>
    </Page>
  )
}

// ─────────────────────────────── services ───────────────────────────────
export function ServicesPage() {
  const { reloadMeta } = useAuth()
  const list = useAsync(() => api.get('/admin/services'), [])
  const [f, setF] = useState({ name: '', description: '', criticality: 1, is_active: true })
  const [error, run] = useSubmit(() => { list.reload(); reloadMeta() })
  const save = (s, patch) => run(() => api.put(`/admin/services/${s.id}`, { name: s.name, description: s.description, criticality: s.criticality, is_active: s.is_active, ...patch }))
  return (
    <Page title="IT services" sub="Business criticality multiplies into every incident's priority score (1x – 3x).">
      <ErrorBox error={error} />
      <form className="card form" onSubmit={e => { e.preventDefault(); run(async () => { await api.post('/admin/services', { ...f, criticality: +f.criticality }); setF({ name: '', description: '', criticality: 1, is_active: true }) }) }}>
        <div className="row">
          <label>Name<input value={f.name} onChange={e => setF({ ...f, name: e.target.value })} required /></label>
          <label className="grow">Description<input value={f.description} onChange={e => setF({ ...f, description: e.target.value })} /></label>
          <label className="narrow">Criticality<input type="number" step="0.5" min={1} max={3} value={f.criticality} onChange={e => setF({ ...f, criticality: e.target.value })} /></label>
          <button className="btn primary">Add service</button>
        </div>
      </form>
      <section className="card">
        <table className="table compact">
          <thead><tr><th>Service</th><th>Description</th><th>Criticality</th><th>Active</th></tr></thead>
          <tbody>{(list.data || []).map(s => (
            <tr key={s.id}><td><strong>{s.name}</strong></td><td className="muted">{s.description}</td>
              <td><select value={s.criticality} onChange={e => save(s, { criticality: +e.target.value })}>{[1, 1.5, 2, 2.5, 3].map(v => <option key={v} value={v}>{v}x</option>)}</select></td>
              <td><input type="checkbox" checked={s.is_active} onChange={e => save(s, { is_active: e.target.checked })} /></td></tr>
          ))}</tbody>
        </table>
      </section>
    </Page>
  )
}

// ─────────────────────────────── categories ───────────────────────────────
export function CategoriesPage() {
  const { reloadMeta } = useAuth()
  const list = useAsync(() => api.get('/admin/categories'), [])
  const [f, setF] = useState({ code: '', name: '', keywords: '' })
  const [error, run] = useSubmit(() => { list.reload(); reloadMeta() })
  const save = (c, patch) => run(() => api.put(`/admin/categories/${c.id}`, { code: c.code, name: c.name, keywords: c.keywords, is_active: c.is_active, ...patch }))
  return (
    <Page title="Incident categories" sub="Keywords drive automatic categorisation — add a category here and the classifier learns it immediately.">
      <ErrorBox error={error} />
      <form className="card form" onSubmit={e => { e.preventDefault(); run(async () => { await api.post('/admin/categories', { ...f, keywords: f.keywords.split(/[,\s]+/).filter(Boolean) }); setF({ code: '', name: '', keywords: '' }) }) }}>
        <div className="row">
          <label className="narrow">Code<input value={f.code} onChange={e => setF({ ...f, code: e.target.value })} required placeholder="PRINTING" /></label>
          <label>Name<input value={f.name} onChange={e => setF({ ...f, name: e.target.value })} required /></label>
          <label className="grow">Keywords<input value={f.keywords} onChange={e => setF({ ...f, keywords: e.target.value })} placeholder="printer, toner, scan" /></label>
          <button className="btn primary">Add category</button>
        </div>
      </form>
      <section className="card">
        <table className="table compact">
          <thead><tr><th>Code</th><th>Name</th><th>Keywords (edit & tab out)</th><th>Active</th></tr></thead>
          <tbody>{(list.data || []).map(c => (
            <tr key={c.id}><td className="mono">{c.code}</td><td>{c.name}</td>
              <td><input className="inline-edit wide" defaultValue={c.keywords.join(', ')} onBlur={e => e.target.value !== c.keywords.join(', ') && save(c, { keywords: e.target.value.split(/[,\s]+/).filter(Boolean) })} /></td>
              <td><input type="checkbox" checked={c.is_active} onChange={e => save(c, { is_active: e.target.checked })} /></td></tr>
          ))}</tbody>
        </table>
      </section>
    </Page>
  )
}

// ─────────────────────────────── SLA ───────────────────────────────
export function SlaPage() {
  const { meta } = useAuth()
  const list = useAsync(() => api.get('/admin/sla-policies'), [])
  const [f, setF] = useState({ name: '', priority: 'P1', service_id: '', response_minutes: 5, resolution_minutes: 30 })
  const [error, run] = useSubmit(() => list.reload())
  const save = (p, patch) => run(() => api.put(`/admin/sla-policies/${p.id}`, { name: p.name, priority: p.priority, service_id: p.service_id, response_minutes: p.response_minutes, resolution_minutes: p.resolution_minutes, ...patch }))
  const rows = [...(list.data || [])].sort((a, b) => (a.service || '').localeCompare(b.service || '') || a.priority.localeCompare(b.priority))
  return (
    <Page title="SLA policies" sub="Service-specific policies override the organisation default for that priority.">
      <ErrorBox error={error} />
      <form className="card form" onSubmit={e => { e.preventDefault(); run(() => api.post('/admin/sla-policies', { ...f, service_id: f.service_id ? +f.service_id : null, response_minutes: +f.response_minutes, resolution_minutes: +f.resolution_minutes })) }}>
        <div className="row">
          <label>Name<input value={f.name} onChange={e => setF({ ...f, name: e.target.value })} required placeholder="Email P2 (Silver)" /></label>
          <label className="narrow">Priority<select value={f.priority} onChange={e => setF({ ...f, priority: e.target.value })}>{['P1', 'P2', 'P3', 'P4'].map(p => <option key={p}>{p}</option>)}</select></label>
          <label>Service<select value={f.service_id} onChange={e => setF({ ...f, service_id: e.target.value })}><option value="">Default (all services)</option>{meta?.services.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
          <label className="narrow">Respond (min)<input type="number" min={1} value={f.response_minutes} onChange={e => setF({ ...f, response_minutes: e.target.value })} /></label>
          <label className="narrow">Resolve (min)<input type="number" min={1} value={f.resolution_minutes} onChange={e => setF({ ...f, resolution_minutes: e.target.value })} /></label>
          <button className="btn primary">Add policy</button>
        </div>
      </form>
      <section className="card">
        <table className="table compact">
          <thead><tr><th>Policy</th><th>Priority</th><th>Applies to</th><th>Response target</th><th>Resolution target</th><th /></tr></thead>
          <tbody>{rows.map(p => (
            <tr key={p.id}><td>{p.name}</td><td><PriorityBadge p={p.priority} /></td><td>{p.service || <span className="muted">All services (default)</span>}</td>
              <td><input type="number" className="inline-num" defaultValue={p.response_minutes} onBlur={e => +e.target.value !== p.response_minutes && save(p, { response_minutes: +e.target.value })} /> min</td>
              <td><input type="number" className="inline-num" defaultValue={p.resolution_minutes} onBlur={e => +e.target.value !== p.resolution_minutes && save(p, { resolution_minutes: +e.target.value })} /> min</td>
              <td>{p.service_id && <button className="link danger" onClick={() => run(() => api.del(`/admin/sla-policies/${p.id}`))}>Delete</button>}</td></tr>
          ))}</tbody>
        </table>
      </section>
    </Page>
  )
}

// ─────────────────────────────── strategies ───────────────────────────────
export function SettingsPage() {
  const cfg = useAsync(() => api.get('/admin/config'), [])
  const [error, run] = useSubmit(() => cfg.reload())
  const c = cfg.data
  return (
    <Page title="Strategies" sub="Swap algorithms at runtime — the Strategy pattern in action.">
      <ErrorBox error={error} />
      {c && <div className="grid-2">
        <section className="card">
          <h3>Technician assignment</h3>
          {c.assignment_strategies.map(s => (
            <label key={s.name} className={`option ${c.assignment_strategy === s.name ? 'on' : ''}`}>
              <input type="radio" checked={c.assignment_strategy === s.name} onChange={() => run(() => api.put('/admin/config', { assignment_strategy: s.name }))} />
              <div><strong>{human(s.name)}</strong><div className="muted sm">{s.description}</div></div>
            </label>
          ))}
        </section>
        <section className="card">
          <h3>Priority calculation</h3>
          {c.priority_strategies.map(s => (
            <label key={s.name} className={`option ${c.priority_strategy === s.name ? 'on' : ''}`}>
              <input type="radio" checked={c.priority_strategy === s.name} onChange={() => run(() => api.put('/admin/config', { priority_strategy: s.name }))} />
              <div><strong>{human(s.name)}</strong><div className="muted sm">{s.description}</div></div>
            </label>
          ))}
          <div className="formula">
            <div className="mono">score = impact × urgency × criticality</div>
            <div className="muted sm">LOW 1 · MEDIUM 1.5 · HIGH 2 · criticality 1–3x<br />≥6 → P1 · ≥3.5 → P2 · ≥2 → P3 · else P4</div>
          </div>
        </section>
      </div>}
    </Page>
  )
}

// ─────────────────────────────── monitoring ───────────────────────────────
export function AuditPage() {
  const [action, setAction] = useState('')
  const [inc, setInc] = useState('')
  const logs = useAsync(() => api.get(`/admin/audit-logs${qs({ action, incident_id: inc ? (+inc.replace(/\D/g, '') >= 1000 ? +inc.replace(/\D/g, '') - 1000 : +inc) : '' })}`), [action, inc])
  return (
    <Page title="Audit log" sub="Immutable history of every important action.">
      <div className="card filters">
        <input placeholder="Incident (INC1004)" value={inc} onChange={e => setInc(e.target.value)} />
        <select value={action} onChange={e => setAction(e.target.value)}>
          <option value="">All actions</option>
          {['INCIDENT_CREATED', 'INCIDENT_ASSIGNED', 'STATUS_CHANGED', 'PRIORITY_CHANGED', 'INCIDENT_RESOLVED', 'INCIDENT_CLOSED', 'SLA_WARNING', 'SLA_VIOLATED', 'INCIDENT_ESCALATED', 'DUPLICATE_DETECTED', 'CORRELATION_DETECTED', 'USER_LOGIN', 'CONFIG_CHANGED'].map(a => <option key={a}>{a}</option>)}
        </select>
      </div>
      <section className="card">
        <table className="table compact">
          <thead><tr><th>Time</th><th>User</th><th>Action</th><th>Incident</th><th>State</th><th>Description</th></tr></thead>
          <tbody>{(logs.data || []).map(a => (
            <tr key={a.id}><td className="mono sm">{fmt(a.timestamp)}</td><td>{a.user ? `${a.user.code} ${a.user.name}` : <span className="muted">System</span>}</td>
              <td><span className="tag">{a.action}</span></td>
              <td className="mono">{a.incident_id ? <Link to={`/incidents/${a.incident_id}`}>{a.incident_code}</Link> : '—'}</td>
              <td className="sm muted">{a.new_state ? `${a.previous_state || '∅'} → ${a.new_state}` : ''}</td>
              <td>{a.description}</td></tr>
          ))}</tbody>
        </table>
      </section>
    </Page>
  )
}

export function ViolationsPage() {
  const v = useAsync(() => api.get('/admin/sla-violations'), [])
  return (
    <Page title="SLA violations" sub="Recorded automatically by the background SLA monitor.">
      <section className="card">
        {!v.data?.length ? <div className="empty">No violations recorded. 🎉</div> : (
          <table className="table compact">
            <thead><tr><th>Incident</th><th>Title</th><th>Pri</th><th>Type</th><th>Technician</th><th>Deadline</th><th>Detected</th></tr></thead>
            <tbody>{v.data.map(x => (
              <tr key={x.id}><td className="mono"><Link to={`/incidents/${x.incident_id}`}>{x.incident_code}</Link></td><td>{x.title}</td>
                <td><PriorityBadge p={x.priority} /></td><td><span className="tag warn">{x.type}</span></td><td>{x.technician || '—'}</td>
                <td className="sm">{fmt(x.deadline)}</td><td className="sm muted">{ago(x.detected_at)}</td></tr>
            ))}</tbody>
          </table>
        )}
      </section>
    </Page>
  )
}

export function OutboxPage() {
  const v = useAsync(() => api.get('/admin/email-outbox'), [])
  const [open, setOpen] = useState(null)
  return (
    <Page title="Email outbox" sub="Every email notification. Simulated unless SMTP is configured in the backend .env.">
      <section className="card">
        <table className="table compact">
          <thead><tr><th>When</th><th>To</th><th>Subject</th><th>Status</th></tr></thead>
          <tbody>{(v.data || []).map(e => (
            <tr key={e.id} onClick={() => setOpen(open === e.id ? null : e.id)} className="clickable">
              <td className="sm muted">{ago(e.created_at)}</td><td>{e.recipient}</td>
              <td>{e.subject}{open === e.id && <pre className="mail">{e.body}</pre>}</td>
              <td>{e.error ? <span className="bad-text" title={e.error}>Failed</span> : e.simulated ? <span className="tag">simulated</span> : <span className="ok-text">Sent</span>}</td></tr>
          ))}</tbody>
        </table>
      </section>
    </Page>
  )
}
