import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './auth'
import Layout from './components/Layout'
import Login from './pages/Login'
import Register from './pages/Register'
import EmployeeHome from './pages/EmployeeHome'
import ReportIncident from './pages/ReportIncident'
import TechnicianHome from './pages/TechnicianHome'
import AdminDashboard from './pages/AdminDashboard'
import IncidentsPage from './pages/IncidentsPage'
import IncidentDetail from './pages/IncidentDetail'
import { AuditPage, CategoriesPage, OutboxPage, ServicesPage, SettingsPage, SlaPage, UsersPage, ViolationsPage } from './pages/AdminPages'

function Guard({ roles, children }) {
  const { user } = useAuth()
  if (!user) return <Navigate to="/login" replace />
  if (roles && !roles.includes(user.role)) return <Navigate to="/" replace />
  return children
}

function Home() {
  const { user } = useAuth()
  if (!user) return <Navigate to="/login" replace />
  return { EMPLOYEE: <EmployeeHome />, TECHNICIAN: <TechnicianHome />, ADMIN: <AdminDashboard /> }[user.role]
}

export default function App() {
  const { user, loading } = useAuth()
  if (loading) return <div className="boot">Loading…</div>
  return (
    <Routes>
      <Route path="/login" element={user ? <Navigate to="/" /> : <Login />} />
      <Route path="/register" element={user ? <Navigate to="/" /> : <Register />} />
      <Route element={<Guard><Layout /></Guard>}>
        <Route index element={<Home />} />
        <Route path="report" element={<Guard roles={['EMPLOYEE', 'ADMIN']}><ReportIncident /></Guard>} />
        <Route path="incidents" element={<IncidentsPage />} />
        <Route path="incidents/:id" element={<IncidentDetail />} />
        <Route path="admin/users" element={<Guard roles={['ADMIN']}><UsersPage /></Guard>} />
        <Route path="admin/services" element={<Guard roles={['ADMIN']}><ServicesPage /></Guard>} />
        <Route path="admin/categories" element={<Guard roles={['ADMIN']}><CategoriesPage /></Guard>} />
        <Route path="admin/sla" element={<Guard roles={['ADMIN']}><SlaPage /></Guard>} />
        <Route path="admin/settings" element={<Guard roles={['ADMIN']}><SettingsPage /></Guard>} />
        <Route path="admin/audit" element={<Guard roles={['ADMIN']}><AuditPage /></Guard>} />
        <Route path="admin/violations" element={<Guard roles={['ADMIN']}><ViolationsPage /></Guard>} />
        <Route path="admin/outbox" element={<Guard roles={['ADMIN']}><OutboxPage /></Guard>} />
      </Route>
      <Route path="*" element={<Navigate to="/" />} />
    </Routes>
  )
}
