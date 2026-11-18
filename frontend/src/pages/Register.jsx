import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth'
import { ErrorBox } from '../components/ui'

export default function Register() {
  const { register } = useAuth()
  const [f, setF] = useState({ name: '', email: '', password: '', department: '' })
  const [error, setError] = useState(null)
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })

  const submit = async (e) => {
    e.preventDefault(); setError(null)
    if (!/^(?=.*[A-Za-z])(?=.*\d).{8,}$/.test(f.password)) {
      return setError({ code: 'INVALID_INPUT', message: 'Password needs 8+ characters with letters and digits.' })
    }
    try { await register({ ...f, department: f.department || null }) } catch (err) { setError(err) }
  }

  return (
    <div className="auth-page">
      <form className="auth-card" onSubmit={submit}>
        <div className="auth-brand">
          <span className="brand-mark">I/</span>
          <span className="auth-title">I-ITSM</span>
        </div>
        <p className="auth-sub">Create your account</p>
        <ErrorBox error={error} />
        <label>Full name<input value={f.name} onChange={set('name')} required minLength={2} /></label>
        <label>Work email<input type="email" value={f.email} onChange={set('email')} required /></label>
        <label>Department<input value={f.department} onChange={set('department')} /></label>
        <label>Password<input type="password" value={f.password} onChange={set('password')} required />
          <small className="muted">At least 8 characters, letters and digits.</small></label>
        <button className="btn primary block">Create account</button>
        <p className="muted center sm">Already registered? <Link to="/login">Sign in</Link></p>
      </form>
    </div>
  )
}
