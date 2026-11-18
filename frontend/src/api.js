// Thin REST client. Every error from the backend has the shape {error, message, details}.
export class ApiError extends Error {
  constructor(status, body) {
    super(body?.message || `Request failed (${status})`)
    this.status = status
    this.code = body?.error
    this.details = body?.details || {}
  }
}

// Local / Docker: same origin ("/api"). Vercel: set VITE_API_URL to the backend's URL.
const API_BASE = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')

const TOKEN_KEY = 'itsm_token'
export const getToken = () => { try { return localStorage.getItem(TOKEN_KEY) } catch { return null } }
export const setToken = (t) => { try { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY) } catch { /* ignore */ } }

async function request(method, path, body) {
  const headers = { 'Content-Type': 'application/json' }
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  let res
  try {
    res = await fetch(`${API_BASE}/api${path}`, { method, headers, body: body ? JSON.stringify(body) : undefined })
  } catch {
    throw new ApiError(0, { error: 'NETWORK_FAILURE', message: 'Cannot reach the server. Check your connection.' })
  }
  if (res.status === 204) return null
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    if (res.status === 401 && path !== '/auth/login') {
      setToken(null)
      window.dispatchEvent(new Event('itsm:logout'))
    }
    throw new ApiError(res.status, data)
  }
  return data
}

export const api = {
  get: (p) => request('GET', p),
  post: (p, b = {}) => request('POST', p, b),
  put: (p, b) => request('PUT', p, b),
  patch: (p, b) => request('PATCH', p, b),
  del: (p) => request('DELETE', p),
}

export const qs = (obj) => {
  const s = new URLSearchParams()
  Object.entries(obj).forEach(([k, v]) => { if (v !== '' && v !== null && v !== undefined) s.set(k, v) })
  const str = s.toString()
  return str ? `?${str}` : ''
}
