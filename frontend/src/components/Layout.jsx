import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../auth'
import NotificationBell from './NotificationBell'

const NAV = {
  EMPLOYEE: [
    { to: '/', label: 'My incidents', end: true },
    { to: '/report', label: 'Report an incident' },
  ],
  TECHNICIAN: [
    { to: '/', label: 'My queue', end: true },
    { to: '/incidents', label: 'All incidents' },
  ],
  ADMIN: [
    { to: '/', label: 'Operations dashboard', end: true },
    { to: '/incidents', label: 'Incidents' },
    { to: '/report', label: 'Log incident' },
    { section: 'Configuration' },
    { to: '/admin/users', label: 'Users & technicians' },
    { to: '/admin/services', label: 'IT services' },
    { to: '/admin/categories', label: 'Categories' },
    { to: '/admin/sla', label: 'SLA policies' },
    { to: '/admin/settings', label: 'Strategies' },
    { section: 'Monitoring' },
    { to: '/admin/violations', label: 'SLA violations' },
    { to: '/admin/audit', label: 'Audit log' },
    { to: '/admin/outbox', label: 'Email outbox' },
  ],
}

const ROLE_LABEL = { EMPLOYEE: 'Employee portal', TECHNICIAN: 'Support console', ADMIN: 'Service management' }

export default function Layout() {
  const { user, logout } = useAuth()
  return (
    <div className={`shell role-${user.role.toLowerCase()}`}>
      <aside className="side">
        <div className="brand">
          <span className="brand-mark">I/</span>
          <div>
            <div className="brand-name">I-ITSM</div>
            <div className="brand-sub">{ROLE_LABEL[user.role]}</div>
          </div>
        </div>
        <nav>
          {NAV[user.role].map((n, i) => n.section
            ? <div key={i} className="nav-section">{n.section}</div>
            : <NavLink key={n.to} to={n.to} end={n.end} className="nav-link">{n.label}</NavLink>)}
        </nav>
        <div className="side-foot">
          <div className="who">
            <div className="avatar">{user.name.split(' ').map(p => p[0]).slice(0, 2).join('')}</div>
            <div>
              <div className="who-name">{user.name}</div>
              <div className="who-sub">{user.code} · {user.title?.replace('_', ' ').toLowerCase() || user.role.toLowerCase()}</div>
            </div>
          </div>
          <button className="btn ghost sm" onClick={logout}>Sign out</button>
        </div>
      </aside>
      <main className="main">
        <header className="topbar">
          <div className="topbar-role">{ROLE_LABEL[user.role]}</div>
          <NotificationBell />
        </header>
        <div className="content"><Outlet /></div>
      </main>
    </div>
  )
}
