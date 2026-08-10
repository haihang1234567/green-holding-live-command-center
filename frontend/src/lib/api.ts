export const API_BASE = import.meta.env.VITE_API_URL || '/api'

export type User = { id: number; username: string; role: 'ADMIN' | 'TEAM'; team_id?: number | null; team_name?: string | null }

export function token() { return localStorage.getItem('gh_token') || '' }
export function user(): User | null {
  try { return JSON.parse(localStorage.getItem('gh_user') || 'null') } catch { return null }
}
export function logout() { localStorage.removeItem('gh_token'); localStorage.removeItem('gh_user') }

export async function login(username: string, password: string) {
  const body = new URLSearchParams({ username, password })
  const res = await fetch(`${API_BASE}/auth/login`, { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body })
  if (!res.ok) throw new Error((await res.json()).detail || 'Đăng nhập thất bại')
  const data = await res.json()
  localStorage.setItem('gh_token', data.access_token)
  localStorage.setItem('gh_user', JSON.stringify(data.user))
  return data
}

export async function api<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers || {})
  if (token()) headers.set('Authorization', `Bearer ${token()}`)
  if (options.body && !(options.body instanceof FormData) && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers })
  if (res.status === 401) { logout(); window.location.href = '/login'; throw new Error('Phiên đăng nhập đã hết hạn') }
  if (!res.ok) {
    let message = `HTTP ${res.status}`
    try { message = (await res.json()).detail || message } catch {}
    throw new Error(message)
  }
  const type = res.headers.get('content-type') || ''
  if (!type.includes('application/json')) return res as unknown as T
  return res.json()
}

export function json(method: string, body?: unknown): RequestInit {
  return { method, body: body === undefined ? undefined : JSON.stringify(body) }
}

export function connectDashboardWS(onEvent: (event: string, payload: any) => void) {
  const explicit = import.meta.env.VITE_WS_URL as string | undefined
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const base = explicit || `${protocol}//${window.location.host}/ws/dashboard`
  const url = `${base}${base.includes('?') ? '&' : '?'}token=${encodeURIComponent(token())}`
  let closed = false
  let socket: WebSocket | null = null
  let retry: number | undefined
  let keepAlive: number | undefined
  const stopKeepAlive = () => { if (keepAlive) { clearInterval(keepAlive); keepAlive = undefined } }
  const open = () => {
    if (closed) return
    socket = new WebSocket(url)
    socket.onmessage = (e) => { try { const x = JSON.parse(e.data); onEvent(x.event, x.payload) } catch {} }
    socket.onopen = () => {
      socket?.send('ready')
      stopKeepAlive()
      // Keeps the connection active on hosts that idle-suspend free web services.
      keepAlive = window.setInterval(() => {
        if (socket?.readyState === WebSocket.OPEN) socket.send('ping')
      }, 5 * 60 * 1000)
    }
    socket.onclose = () => {
      stopKeepAlive()
      if (!closed) retry = window.setTimeout(open, 2500)
    }
  }
  open()
  return () => { closed = true; if (retry) clearTimeout(retry); stopKeepAlive(); socket?.close() }
}
