import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth'
import { ErrorBox } from '../components/ui'

export default function Login() {
  const { login } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setError(null)
    try { await login(email, password) } catch (err) { setError(err) } finally { setBusy(false) }
  }

  return (
    <div className="auth-page">
      <form className="auth-card" onSubmit={submit}>
        <div className="auth-brand">
          <span className="brand-mark">I/</span>
          <span className="auth-title">I-ITSM</span>
        </div>
        <p className="auth-sub">Sign in to continue</p>
        <ErrorBox error={error} />
        <label>Email<input type="email" value={email} onChange={e => setEmail(e.target.value)} required autoFocus /></label>
        <label>Password<input type="password" value={password} onChange={e => setPassword(e.target.value)} required /></label>
        <button className="btn primary block" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
        <p className="muted center sm">New here? <Link to="/register">Create an account</Link></p>
      </form>
    </div>
  )
}
