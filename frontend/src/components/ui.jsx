import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

export const ago = (iso) => {
  if (!iso) return '—'
  const s = (Date.now() - new Date(iso).getTime()) / 1000
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  return `${Math.floor(s / 86400)}d ago`
}
export const fmt = (iso) => iso ? new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) : '—'
export const human = (s) => s ? s.replaceAll('_', ' ').toLowerCase().replace(/^\w/, c => c.toUpperCase()) : '—'

export function useAsync(fn, deps = []) {
  const [state, set] = useState({ data: null, error: null, loading: true })
  const run = useCallback(() => {
    set(s => ({ ...s, loading: true }))
    return fn().then(data => set({ data, error: null, loading: false }))
      .catch(error => set({ data: null, error, loading: false }))
  }, deps) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { run() }, [run])
  return { ...state, reload: run }
}

export const StatusBadge = ({ s }) => <span className={`badge st-${s?.toLowerCase()}`}>{human(s)}</span>
export const PriorityBadge = ({ p }) => <span className={`prio prio-${p?.toLowerCase()}`}>{p}</span>
export function SlaBadge({ state, minutes }) {
  const label = { ON_TRACK: 'On track', AT_RISK: 'At risk', BREACHED: 'Breached', MET: 'Met' }[state] || state
  const left = minutes != null && state !== 'MET'
    ? (minutes < 0 ? ` · ${Math.abs(Math.round(minutes))}m over` : ` · ${minutes < 120 ? Math.round(minutes) + 'm' : Math.round(minutes / 60) + 'h'} left`)
    : ''
  return <span className={`sla sla-${state?.toLowerCase()}`}>{label}{left}</span>
}

export const ErrorBox = ({ error }) => error
  ? <div className="error-box"><strong>{error.code?.replaceAll('_', ' ') || 'Error'}</strong> {error.message}</div>
  : null

export const Stat = ({ label, value, tone, sub }) => (
  <div className={`stat ${tone || ''}`}>
    <div className="stat-label">{label}</div>
    <div className="stat-value">{value ?? '—'}</div>
    {sub && <div className="stat-sub">{sub}</div>}
  </div>
)

export function Bars({ data, tone }) {
  const entries = Object.entries(data || {}).sort((a, b) => b[1] - a[1])
  const max = Math.max(1, ...entries.map(e => e[1]))
  if (!entries.length) return <div className="empty sm">No data</div>
  return (
    <div className="bars">
      {entries.map(([k, v]) => (
        <div className="bar-row" key={k}>
          <span className="bar-label" title={k}>{human(k)}</span>
          <span className="bar-track"><span className={`bar-fill ${tone || ''}`} style={{ width: `${(v / max) * 100}%` }} /></span>
          <span className="bar-val">{v}</span>
        </div>
      ))}
    </div>
  )
}

export function IncidentTable({ rows, showReporter = true, showTech = true, empty = 'No incidents found.' }) {
  if (!rows?.length) return <div className="empty">{empty}</div>
  return (
    <div className="table-wrap">
      <table className="table">
        <thead><tr>
          <th>ID</th><th>Title</th><th>Pri</th><th>Status</th><th>Service</th>
          {showReporter && <th>Reporter</th>}{showTech && <th>Technician</th>}<th>SLA</th><th>Created</th>
        </tr></thead>
        <tbody>
          {rows.map(i => (
            <tr key={i.id}>
              <td className="mono"><Link to={`/incidents/${i.id}`}>{i.code}</Link></td>
              <td className="title-cell"><Link to={`/incidents/${i.id}`}>{i.title}</Link>
                {i.escalation_level > 0 && <span className="esc">ESC L{i.escalation_level}</span>}</td>
              <td><PriorityBadge p={i.priority} /></td>
              <td><StatusBadge s={i.status} /></td>
              <td>{i.service?.name}</td>
              {showReporter && <td>{i.reporter?.name}</td>}
              {showTech && <td>{i.technician?.name || <span className="muted">Unassigned</span>}</td>}
              <td><SlaBadge state={i.sla_state} minutes={i.sla_minutes_left} /></td>
              <td className="muted">{ago(i.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

const FLOW = ['NEW', 'CLASSIFIED', 'ASSIGNED', 'ACKNOWLEDGED', 'IN_PROGRESS', 'RESOLVED', 'VERIFIED', 'CLOSED']
export function Lifecycle({ status }) {
  const cur = status === 'AWAITING_INFO' ? FLOW.indexOf('IN_PROGRESS') : FLOW.indexOf(status)
  return (
    <ol className="lifecycle">
      {FLOW.map((s, i) => (
        <li key={s} className={i < cur ? 'done' : i === cur ? 'current' : ''}>
          <span className="dot" />
          <span className="lc-label">{status === 'AWAITING_INFO' && i === cur ? 'Awaiting info' : human(s)}</span>
        </li>
      ))}
    </ol>
  )
}
