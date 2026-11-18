import { useState } from 'react'
import { api, qs } from '../api'
import { useAuth } from '../auth'
import { ErrorBox, IncidentTable, useAsync } from '../components/ui'

const EMPTY = { id: '', q: '', status: '', priority: '', category_id: '', service_id: '', technician_id: '', date_from: '', date_to: '', sla_status: '' }

export default function IncidentsPage() {
  const { user, meta } = useAuth()
  const [f, setF] = useState(EMPTY)
  const [applied, setApplied] = useState(EMPTY)
  const scope = user.role === 'TECHNICIAN' ? { scope: 'all' } : {}
  const { data, error, loading } = useAsync(() => {
    const p = { ...applied, ...scope }
    if (p.id) { const n = +String(p.id).replace(/\D/g, ''); p.id = n >= 1000 ? n - 1000 : n } // "INC1004" → 4
    return api.get(`/incidents${qs(p)}`)
  }, [JSON.stringify(applied)])
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })

  return (
    <>
      <div className="page-head"><div><h1>Incidents</h1><p className="muted">Search and filter across the organisation.</p></div></div>
      <form className="card filters" onSubmit={(e) => { e.preventDefault(); setApplied(f) }}>
        <input placeholder="INC1004" value={f.id} onChange={set('id')} className="w-sm" aria-label="Incident ID" />
        <input placeholder="Search title / description" value={f.q} onChange={set('q')} className="grow" />
        <select value={f.status} onChange={set('status')}><option value="">Any status</option>{meta?.statuses.map(s => <option key={s}>{s}</option>)}</select>
        <select value={f.priority} onChange={set('priority')}><option value="">Any priority</option>{meta?.priorities.map(p => <option key={p.value} value={p.value}>{p.value} – {p.label}</option>)}</select>
        <select value={f.category_id} onChange={set('category_id')}><option value="">Any category</option>{meta?.categories.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select>
        <select value={f.service_id} onChange={set('service_id')}><option value="">Any service</option>{meta?.services.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select>
        <select value={f.technician_id} onChange={set('technician_id')}><option value="">Any technician</option>{meta?.technicians.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}</select>
        <select value={f.sla_status} onChange={set('sla_status')}><option value="">Any SLA state</option>{['ON_TRACK', 'AT_RISK', 'BREACHED', 'MET'].map(s => <option key={s}>{s}</option>)}</select>
        <label className="inline">From<input type="date" value={f.date_from} onChange={set('date_from')} /></label>
        <label className="inline">To<input type="date" value={f.date_to} onChange={set('date_to')} /></label>
        <button className="btn primary">Apply</button>
        <button type="button" className="btn ghost" onClick={() => { setF(EMPTY); setApplied(EMPTY) }}>Reset</button>
      </form>
      <ErrorBox error={error} />
      <section className="card">
        <h3>{loading ? 'Loading…' : `${data?.length ?? 0} incidents`}</h3>
        <IncidentTable rows={data} />
      </section>
    </>
  )
}
