import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api, getToken, setToken } from './api'

const AuthCtx = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [meta, setMeta] = useState(null)
  const [loading, setLoading] = useState(!!getToken())

  const loadMeta = useCallback(async () => setMeta(await api.get('/meta')), [])

  useEffect(() => {
    if (!getToken()) return
    api.get('/auth/me').then(async (u) => { setUser(u); await loadMeta() })
      .catch(() => setToken(null)).finally(() => setLoading(false))
  }, [loadMeta])

  useEffect(() => {
    const onLogout = () => { setUser(null); setMeta(null) }
    window.addEventListener('itsm:logout', onLogout)
    return () => window.removeEventListener('itsm:logout', onLogout)
  }, [])

  const login = async (email, password) => {
    const r = await api.post('/auth/login', { email, password })
    setToken(r.token); setUser(r.user); await loadMeta()
    return r.user
  }
  const register = async (body) => {
    const r = await api.post('/auth/register', body)
    setToken(r.token); setUser(r.user); await loadMeta()
    return r.user
  }
  const logout = () => { setToken(null); setUser(null); setMeta(null) }

  return (
    <AuthCtx.Provider value={{ user, meta, loading, login, register, logout, reloadMeta: loadMeta }}>
      {children}
    </AuthCtx.Provider>
  )
}

export const useAuth = () => useContext(AuthCtx)
