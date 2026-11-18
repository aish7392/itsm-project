import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { ErrorBox, StatusBadge } from '../components/ui'

const LEVEL_HINT = {
  impact: { LOW: 'Just me / minor', MEDIUM: 'My team / degraded', HIGH: 'Many people / business stopped' },
  urgency: { LOW: 'Can wait days', MEDIUM: 'Needed today', HIGH: 'Needed right now' },
}

export default function ReportIncident() {
  const { meta } = useAuth()
  const nav = useNavigate()
  const [f, setF] = useState({ title: '', description: '', service_id: '', category_id: '', impact: 'MEDIUM', urgency: 'MEDIUM', affected_users: 1 })
  const [sugg, setSugg] = useState(null)
  const [error, setError] = useState(null)
  const [dup, setDup] = useState(null)
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })

  // live intelligence: category suggestion, similar incidents, known fixes (debounced)
  useEffect(() => {
    if ((f.title + f.description).trim().length < 8) { setSugg(null); return }
    const t = setTimeout(() => {
      api.post('/incidents/suggest', { title: f.title, description: f.description, service_id: f.service_id ? +f.service_id : null })
        .then(setSugg).catch(() => {})
    }, 450)
    return () => clearTimeout(t)
  }, [f.title, f.description, f.service_id])

  const submit = async (e, force = false) => {
    e?.preventDefault()
    setBusy(true); setError(null)
    try {
      const body = { ...f, service_id: +f.service_id, affected_users: +f.affected_users, category_id: f.category_id ? +f.category_id : null, force }
      const inc = await api.post('/incidents', body)
      nav(`/incidents/${inc.id}`)
    } catch (err) {
      if (err.code === 'DUPLICATE_INCIDENT') setDup(err)
      else setError(err)
    } finally { setBusy(false) }
  }

  const topCat = sugg?.categories?.[0]
  return (
    <>
      <div className="page-head"><div><h1>Report an incident</h1><p className="muted">Describe what's wrong. We classify, prioritise and route it automatically.</p></div></div>
      <div className="grid-2-1">
        <form className="card form" onSubmit={submit}>
          <ErrorBox error={error} />
          {dup && (
            <div className="error-box warn">
              <strong>Looks like a repeat.</strong> {dup.message}.{' '}
              <Link to={`/incidents/${dup.details.existing_id}`}>Open {dup.details.existing}</Link>{' '}or{' '}
              <button type="button" className="link" onClick={() => { setDup(null); submit(null, true) }}>submit anyway</button>.
            </div>
          )}
          <label>Short title<input value={f.title} onChange={set('title')} required minLength={5} maxLength={200} placeholder="e.g. Payment application unavailable" /></label>
          <label>What happened?<textarea rows={5} value={f.description} onChange={set('description')} required minLength={10} placeholder="What were you doing, what did you expect, what error do you see?" /></label>
          <div className="row">
            <label>Affected service
              <select value={f.service_id} onChange={set('service_id')} required>
                <option value="">Select a service…</option>
                {meta?.services.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </label>
            <label>Category
              <select value={f.category_id} onChange={set('category_id')}>
                <option value="">Auto-detect{topCat ? ` (${topCat.name})` : ''}</option>
                {meta?.categories.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </label>
          </div>
          <div className="row">
            {['impact', 'urgency'].map(k => (
              <div key={k} className="seg-wrap">
                <span className="seg-label">{k[0].toUpperCase() + k.slice(1)}</span>
                <div className="seg">
                  {['LOW', 'MEDIUM', 'HIGH'].map(l => (
                    <button type="button" key={l} className={f[k] === l ? 'on' : ''} onClick={() => setF({ ...f, [k]: l })}>{l.toLowerCase()}</button>
                  ))}
                </div>
                <small className="muted">{LEVEL_HINT[k][f[k]]}</small>
              </div>
            ))}
            <label className="narrow">People affected<input type="number" min={1} value={f.affected_users} onChange={set('affected_users')} /></label>
          </div>
          <button className="btn primary" disabled={busy}>{busy ? 'Submitting…' : 'Submit incident'}</button>
        </form>

        <aside className="card assist">
          <h3>Assistant</h3>
          {!sugg && <p className="muted">Start typing — we'll suggest a category, flag similar open incidents and show fixes that worked before.</p>}
          {sugg && <>
            <div className="assist-block">
              <div className="assist-title">Suggested category</div>
              {sugg.categories.length ? sugg.categories.map(c => (
                <div key={c.code} className="assist-row"><span>{c.name}</span><span className="muted mono">{Math.round(c.confidence * 100)}%</span></div>
              )) : <div className="muted">No strong match yet.</div>}
            </div>
            <div className="assist-block">
              <div className="assist-title">Similar open incidents</div>
              {sugg.similar.length ? sugg.similar.map(s => (
                <div key={s.id} className="assist-row">
                  <Link to={`/incidents/${s.id}`}>{s.code}</Link><span className="grow ellipsis">{s.title}</span>
                  <StatusBadge s={s.status} />
                </div>
              )) : <div className="muted">None — this looks new.</div>}
            </div>
            <div className="assist-block">
              <div className="assist-title">Fixes that worked before</div>
              {sugg.resolutions.length ? sugg.resolutions.map(r => (
                <div key={r.id} className="assist-fix"><span className="mono muted">{r.code}</span> {r.resolution}</div>
              )) : <div className="muted">No past fixes found.</div>}
            </div>
          </>}
        </aside>
      </div>
    </>
  )
}
