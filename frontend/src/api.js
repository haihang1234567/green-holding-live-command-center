const API_BASE = import.meta.env.VITE_API_URL || '/api'

export function getToken() { return localStorage.getItem('lcc_token') }
export function getSessionUser() {
  try { return JSON.parse(localStorage.getItem('lcc_user') || 'null') } catch { return null }
}
export function saveSession(token, user) {
  localStorage.setItem('lcc_token', token)
  localStorage.setItem('lcc_user', JSON.stringify(user))
}
export function clearSession() {
  localStorage.removeItem('lcc_token')
  localStorage.removeItem('lcc_user')
}

async function request(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) }
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers })
  if (res.status === 401) { clearSession(); window.location.href = '/login'; throw new Error('Phiên đăng nhập đã hết hạn') }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `HTTP ${res.status}`)
  }
  return res.json()
}

export const api = {
  login: (username, password) => request('/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) }),
  me: () => request('/auth/me'),
  overview: (snapshot='T3H') => request(`/admin/overview?snapshot_type=${snapshot}`),
  ranking: (snapshot='T3H') => request(`/admin/ranking?snapshot_type=${snapshot}`),
  sessions: (snapshot='T3H') => request(`/admin/sessions?snapshot_type=${snapshot}`),
  session: (id, snapshot='T3H') => request(`/admin/sessions/${id}?snapshot_type=${snapshot}`),
  alerts: () => request('/admin/alerts'),
  ackAlert: (id) => request(`/admin/alerts/${id}/ack`, { method: 'POST' }),
  directory: () => request('/admin/directory'),
  status: () => request('/config/status'),
  teamDashboard: (snapshot='T3H') => request(`/team/dashboard?snapshot_type=${snapshot}`),
  mock: (action, body) => request(`/mock/${action}`, { method: 'POST', body: JSON.stringify(body) }),
}

export function connectRealtime(onMessage) {
  const token = getToken()
  if (!token) return () => {}
  const base = import.meta.env.VITE_WS_URL || `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}`
  const ws = new WebSocket(`${base}/ws/dashboard?token=${encodeURIComponent(token)}`)
  ws.onmessage = (event) => { try { onMessage(JSON.parse(event.data)) } catch {} }
  const ping = setInterval(() => { if (ws.readyState === WebSocket.OPEN) ws.send('ping') }, 25000)
  return () => { clearInterval(ping); ws.close() }
}
