import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { ago } from './ui'

export default function NotificationBell() {
  const [data, setData] = useState({ unread: 0, items: [] })
  const [open, setOpen] = useState(false)
  const nav = useNavigate()
  const ref = useRef()

  const load = () => api.get('/notifications').then(setData).catch(() => {})
  useEffect(() => {
    load()
    const t = setInterval(load, 15000) // in-app notifications are polled
    return () => clearInterval(t)
  }, [])
  useEffect(() => {
    const close = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])

  const openItem = async (n) => {
    if (!n.is_read) await api.post(`/notifications/${n.id}/read`)
    setOpen(false); load()
    if (n.incident_id) nav(`/incidents/${n.incident_id}`)
  }

  return (
    <div className="bell" ref={ref}>
      <button className="bell-btn" onClick={() => setOpen(!open)} aria-label="Notifications">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" /><path d="M13.7 21a2 2 0 0 1-3.4 0" /></svg>
        {data.unread > 0 && <span className="bell-count">{data.unread}</span>}
      </button>
      {open && (
        <div className="bell-panel">
          <div className="bell-head">
            <strong>Notifications</strong>
            {data.unread > 0 && <button className="link" onClick={async () => { await api.post('/notifications/read-all'); load() }}>Mark all read</button>}
          </div>
          {data.items.length === 0 && <div className="empty sm">Nothing yet.</div>}
          {data.items.map(n => (
            <button key={n.id} className={`bell-item ${n.is_read ? '' : 'unread'}`} onClick={() => openItem(n)}>
              <span className="bell-event">{n.event.replaceAll('_', ' ').toLowerCase()}</span>
              <span className="bell-msg">{n.message}</span>
              <span className="bell-time">{ago(n.created_at)}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
