import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { ErrorBox, Lifecycle, PriorityBadge, SlaBadge, StatusBadge, ago, fmt, human, useAsync } from '../components/ui'

function TextAction({ label, placeholder, onSubmit, tone = 'primary', rows = 2, extra }) {
  const [text, setText] = useState('')
  return (
    <form className="text-action" onSubmit={async (e) => { e.preventDefault(); if (await onSubmit(text)) setText('') }}>
      <textarea rows={rows} value={text} placeholder={placeholder} onChange={e => setText(e.target.value)} required />
      {extra}
      <button className={`btn ${tone}`}>{label}</button>
    </form>
  )
}

export default function IncidentDetail() {
  const { id } = useParams()
  const { user, meta } = useAuth()
  const inc = useAsync(() => api.get(`/incidents/${id}`), [id])
  const recs = useAsync(() => api.get(`/incidents/${id}/recommendations`), [id])
  const [error, setError] = useState(null)
  const [flash, setFlash] = useState(null)
  const [edit, setEdit] = useState(null)
  const [verify, setVerify] = useState({ rating: 5, comment: '' })
  const [resolve, setResolve] = useState({ resolution: '', root_cause: '' })
  const [assignTo, setAssignTo] = useState('')

  const d = inc.data
  const act = async (path, body = {}, msg) => {
    setError(null)
    try {
      await api.post(`/incidents/${id}/${path}`, body)
      setFlash(msg || 'Saved'); setTimeout(() => setFlash(null), 2500)
      inc.reload(); recs.reload()
      return true
    } catch (err) { setError(err); return false }
  }
  const saveEdit = async (e) => {
    e.preventDefault(); setError(null)
    try {
      const body = { ...edit, affected_users: +edit.affected_users }
      if (!body.priority_override) delete body.priority_override
      await api.patch(`/incidents/${id}`, body); setEdit(null); inc.reload()
    } catch (err) { setError(err) }
  }

  if (inc.error) return <ErrorBox error={inc.error} />
  if (!d) return <div className="muted">Loading…</div>

  const isReporter = d.reporter?.id === user.id
  const isAssignee = d.technician?.id === user.id
  const isAdmin = user.role === 'ADMIN'
  const active = !['RESOLVED', 'VERIFIED', 'CLOSED'].includes(d.status)
  const canWork = isAssignee || isAdmin

  return (
    <>
      <div className="crumbs"><Link to={user.role === 'ADMIN' ? '/incidents' : '/'}>← Back</Link></div>
      <div className="inc-head">
        <div>
          <div className="inc-code mono">{d.code} {d.escalation_level > 0 && <span className="esc">Escalated L{d.escalation_level}</span>}</div>
          <h1>{d.title}</h1>
          <div className="inc-meta">
            <PriorityBadge p={d.priority} /> <StatusBadge s={d.status} /> <SlaBadge state={d.sla_state} minutes={d.sla_minutes_left} />
            <span className="muted">Reported {ago(d.created_at)} by {d.reporter.name}</span>
          </div>
        </div>
        {(isReporter || isAdmin) && active && !edit && (
          <button className="btn ghost" onClick={() => setEdit({ title: d.title, description: d.description, impact: d.impact, urgency: d.urgency, affected_users: d.affected_users, priority_override: '' })}>Edit</button>
        )}
      </div>
      <Lifecycle status={d.status} />
      <ErrorBox error={error} />
      {flash && <div className="flash">{flash}</div>}

      <div className="grid-2-1">
        <div>
          {edit ? (
            <form className="card form" onSubmit={saveEdit}>
              <h3>Edit incident</h3>
              <label>Title<input value={edit.title} onChange={e => setEdit({ ...edit, title: e.target.value })} /></label>
              <label>Description<textarea rows={4} value={edit.description} onChange={e => setEdit({ ...edit, description: e.target.value })} /></label>
              <div className="row">
                {['impact', 'urgency'].map(k => (
                  <label key={k}>{human(k)}<select value={edit[k]} onChange={e => setEdit({ ...edit, [k]: e.target.value })}>{meta.levels.map(l => <option key={l}>{l}</option>)}</select></label>
                ))}
                <label>People affected<input type="number" min={1} value={edit.affected_users} onChange={e => setEdit({ ...edit, affected_users: e.target.value })} /></label>
                {isAdmin && <label>Override priority<select value={edit.priority_override} onChange={e => setEdit({ ...edit, priority_override: e.target.value })}>
                  <option value="">Keep calculated</option>{meta.priorities.map(p => <option key={p.value} value={p.value}>{p.value} – {p.label}</option>)}</select></label>}
              </div>
              <div className="actions"><button className="btn primary">Save</button><button type="button" className="btn ghost" onClick={() => setEdit(null)}>Cancel</button></div>
            </form>
          ) : (
            <section className="card">
              <h3>Description</h3>
              <p className="pre">{d.description}</p>
              {d.resolution && (
                <div className="resolution">
                  <div className="res-label">Resolution</div>
                  <p>{d.resolution}</p>
                  {d.root_cause && <p className="muted">Root cause: {d.root_cause}</p>}
                </div>
              )}
              {d.feedback_rating && <div className="feedback">{'★'.repeat(d.feedback_rating)}{'☆'.repeat(5 - d.feedback_rating)} <span className="muted">{d.feedback_comment}</span></div>}
              {d.closure_notes && <p className="muted">Closure notes: {d.closure_notes}</p>}
            </section>
          )}

          {/* ── role-specific action panel ── */}
          <section className="card actions-card">
            <h3>Actions</h3>
            {/* technician */}
            {canWork && d.status === 'ASSIGNED' && (
              <div className="action-group">
                <p>{isAssignee ? 'This incident was assigned to you.' : `Waiting for ${d.technician?.name} to accept.`}</p>
                {isAssignee && <div className="actions">
                  <button className="btn primary" onClick={() => act('accept', {}, 'Incident acknowledged')}>Accept</button>
                </div>}
                {isAssignee && <TextAction label="Decline" tone="danger" placeholder="Reason for declining (e.g. outside my expertise)" onSubmit={t => act('decline', { text: t }, 'Declined – reassigned')} />}
              </div>
            )}
            {canWork && d.status === 'ACKNOWLEDGED' && (
              <div className="actions"><button className="btn primary" onClick={() => act('start', {}, 'Investigation started')}>Start investigation</button></div>
            )}
            {canWork && d.status === 'IN_PROGRESS' && (
              <>
                <div className="action-group">
                  <div className="ag-title">Investigation note</div>
                  <TextAction label="Add note" placeholder="What did you check / find?" onSubmit={t => act('notes', { text: t }, 'Note added')} />
                </div>
                <div className="action-group">
                  <div className="ag-title">Need more information from {d.reporter.name}?</div>
                  <TextAction label="Request info" tone="ghost" placeholder="Ask a question…" onSubmit={t => act('request-info', { text: t }, 'Question sent to reporter')} />
                </div>
                <form className="action-group" onSubmit={async e => { e.preventDefault(); if (await act('resolve', { ...resolve, root_cause: resolve.root_cause || null }, 'Resolved')) setResolve({ resolution: '', root_cause: '' }) }}>
                  <div className="ag-title">Resolve</div>
                  <textarea rows={2} placeholder="What fixed it?" value={resolve.resolution} onChange={e => setResolve({ ...resolve, resolution: e.target.value })} required />
                  <input placeholder="Root cause (optional)" value={resolve.root_cause} onChange={e => setResolve({ ...resolve, root_cause: e.target.value })} />
                  <button className="btn ok">Mark resolved</button>
                </form>
              </>
            )}
            {canWork && d.status === 'AWAITING_INFO' && <p className="muted">Waiting for the reporter to answer your question.</p>}
            {/* employee */}
            {isReporter && d.status === 'AWAITING_INFO' && (
              <div className="action-group">
                <div className="ag-title">Support needs more information</div>
                <p className="quote">{[...d.notes].reverse().find(n => n.kind === 'INFO_REQUEST')?.body}</p>
                <TextAction label="Send reply" placeholder="Your answer…" onSubmit={t => act('respond', { text: t }, 'Reply sent')} />
              </div>
            )}
            {(isReporter || isAdmin) && d.status === 'RESOLVED' && (
              <>
                <form className="action-group" onSubmit={e => { e.preventDefault(); act('verify', { rating: +verify.rating, comment: verify.comment || null }, 'Thanks for your feedback') }}>
                  <div className="ag-title">Is it fixed? Rate the support</div>
                  <div className="stars">{[1, 2, 3, 4, 5].map(n => (
                    <button type="button" key={n} className={n <= verify.rating ? 'on' : ''} onClick={() => setVerify({ ...verify, rating: n })}>★</button>))}</div>
                  <input placeholder="Comment (optional)" value={verify.comment} onChange={e => setVerify({ ...verify, comment: e.target.value })} />
                  <button className="btn ok">Confirm fix</button>
                </form>
                <div className="action-group">
                  <div className="ag-title">Still broken?</div>
                  <TextAction label="Reopen" tone="danger" placeholder="What's still wrong?" onSubmit={t => act('reopen', { text: t }, 'Reopened')} />
                </div>
              </>
            )}
            {((isAdmin && ['RESOLVED', 'VERIFIED'].includes(d.status)) || (isAssignee && d.status === 'VERIFIED')) && (
              <div className="action-group">
                <div className="ag-title">Close incident</div>
                <TextAction label="Close" tone="ghost" placeholder="Closure notes (optional)" rows={1} onSubmit={t => act('close', { notes: t }, 'Closed')} />
              </div>
            )}
            {/* admin assignment */}
            {isAdmin && ['CLASSIFIED', 'ASSIGNED'].includes(d.status) && (
              <div className="action-group">
                <div className="ag-title">Assign technician</div>
                {recs.data?.technicians?.length > 0 && (
                  <div className="recs">
                    {recs.data.technicians.slice(0, 4).map(t => (
                      <button key={t.id} className={`rec ${String(assignTo) === String(t.id) ? 'on' : ''}`} onClick={() => setAssignTo(t.id)}>
                        <strong>{t.name}</strong><span className="muted sm">{t.skills.join(', ')}</span>
                        <span className="sm">load {t.workload}/{t.max_workload} · score <b>{t.score}</b></span>
                      </button>
                    ))}
                  </div>
                )}
                <div className="actions">
                  <select value={assignTo} onChange={e => setAssignTo(e.target.value)}>
                    <option value="">Choose…</option>
                    {meta.technicians.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
                  </select>
                  <button className="btn primary" disabled={!assignTo} onClick={() => act('assign', { technician_id: +assignTo }, 'Assigned')}>Assign</button>
                  <button className="btn ghost" onClick={() => act('assign', { technician_id: null }, 'Auto-assigned')}>Auto-assign (strategy)</button>
                </div>
              </div>
            )}
            {isAdmin && d.allowed_transitions.filter(s => s !== d.status).length > 0 && (
              <div className="action-group">
                <div className="ag-title">Force status <span className="muted sm">(still validated by the lifecycle)</span></div>
                <div className="actions">{d.allowed_transitions.filter(s => s !== d.status).map(s => (
                  <button key={s} className="btn ghost sm" onClick={() => act('status', { status: s }, `Status → ${s}`)}>{human(s)}</button>))}</div>
              </div>
            )}
            {!isAdmin && !isAssignee && !isReporter && <p className="muted">View only.</p>}
            {d.status === 'CLOSED' && <p className="muted">This incident is closed.</p>}
            {active && (isReporter || isAdmin) && !['AWAITING_INFO'].includes(d.status) && (
              <div className="action-group">
                <div className="ag-title">Add a comment</div>
                <TextAction label="Comment" tone="ghost" rows={1} placeholder="Extra details, screenshots links…" onSubmit={t => act('notes', { text: t }, 'Comment added')} />
              </div>
            )}
          </section>

          <section className="card">
            <h3>Conversation & investigation</h3>
            {d.notes.length === 0 && <div className="empty sm">No notes yet.</div>}
            <ul className="notes">
              {d.notes.map(n => (
                <li key={n.id} className={`note k-${n.kind.toLowerCase()}`}>
                  <div className="note-head"><strong>{n.author.name}</strong> <span className="tag">{human(n.kind)}</span> <span className="muted sm">{fmt(n.created_at)}</span></div>
                  <div className="pre">{n.body}</div>
                </li>
              ))}
            </ul>
          </section>
        </div>

        <div>
          <section className="card">
            <h3>Details</h3>
            <dl className="kv">
              <dt>Service</dt><dd>{d.service.name} <span className="muted">({d.service.criticality}x)</span></dd>
              <dt>Category</dt><dd>{d.category?.name || '—'} {d.auto_category && <span className="tag">auto</span>}</dd>
              <dt>Impact / urgency</dt><dd>{human(d.impact)} / {human(d.urgency)}</dd>
              <dt>People affected</dt><dd>{d.affected_users}</dd>
              <dt>Priority score</dt><dd className="mono">{d.priority_score}</dd>
              <dt>Technician</dt><dd>{d.technician ? `${d.technician.name} (${d.technician.code})` : <span className="muted">Unassigned</span>}</dd>
              <dt>Reporter</dt><dd>{d.reporter.name} ({d.reporter.code})</dd>
            </dl>
          </section>
          <section className="card">
            <h3>SLA</h3>
            <dl className="kv">
              <dt>Policy</dt><dd>{d.sla_policy?.name || '—'}</dd>
              <dt>Respond by</dt><dd className={d.response_breached ? 'bad-text' : ''}>{fmt(d.response_due)}</dd>
              <dt>Resolve by</dt><dd className={d.resolution_breached ? 'bad-text' : ''}>{fmt(d.resolution_due)}</dd>
              <dt>Acknowledged</dt><dd>{fmt(d.acknowledged_at)}</dd>
              <dt>Resolved</dt><dd>{fmt(d.resolved_at)}</dd>
            </dl>
            {d.violations.map((v, i) => <div key={i} className="violation">{human(v.type)} SLA violated · deadline {fmt(v.deadline)}</div>)}
          </section>
          {d.related.length > 0 && (
            <section className="card">
              <h3>Related incidents</h3>
              {d.related.map(r => (
                <Link key={r.id} to={`/incidents/${r.id}`} className="related">
                  <span className={`tag ${r.type === 'DUPLICATE' ? 'warn' : ''}`}>{human(r.type)}</span>
                  <span className="mono">{r.code}</span><span className="grow ellipsis">{r.title}</span><StatusBadge s={r.status} />
                </Link>
              ))}
            </section>
          )}
          {user.role !== 'EMPLOYEE' && recs.data?.resolutions?.length > 0 && (
            <section className="card">
              <h3>Suggested resolutions</h3>
              {recs.data.resolutions.map(r => (
                <div key={r.id} className="assist-fix"><Link to={`/incidents/${r.id}`} className="mono">{r.code}</Link> <span className="muted sm">{Math.round(r.score * 100)}% similar</span><div>{r.resolution}</div></div>
              ))}
            </section>
          )}
          <section className="card">
            <h3>Audit trail</h3>
            <ol className="timeline">
              {d.audit.map(a => (
                <li key={a.id}>
                  <span className="tl-time mono">{new Date(a.timestamp).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })}</span>
                  <div>
                    <div className="tl-action">{human(a.action)}{a.new_state && a.previous_state !== a.new_state && <span className="muted"> · {a.previous_state || '∅'} → {a.new_state}</span>}</div>
                    <div className="tl-desc">{a.description}</div>
                    <div className="muted sm">{a.user ? `${a.user.name} (${a.user.code})` : 'System'}</div>
                  </div>
                </li>
              ))}
            </ol>
          </section>
        </div>
      </div>
    </>
  )
}
