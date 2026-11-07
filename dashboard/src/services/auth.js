import { API_BASE_URL } from './api.js'

// Bearer credentials exist only in this closure. Reloading requires another sign-in.
// Backend /auth/me and every protected request remain the authority on permissions.
export function createAuthSession({ baseUrl = API_BASE_URL, fetchImpl = fetch, now = Date.now } = {}) {
  let token = null, user = null, generation = 0, expiry = 0, timer
  const listeners = new Set()
  function clear() {
    generation += 1
    clearTimeout(timer)
    token = null; user = null; expiry = 0
    listeners.forEach(listener => listener(null))
  }
  async function request(path, { signal, ...options } = {}, credential = token) {
    if (!path.startsWith('/') || path.startsWith('//')) throw new Error('Invalid API path')
    const controller = new AbortController()
    const abort = () => controller.abort()
    if (signal?.aborted) controller.abort()
    signal?.addEventListener('abort', abort, { once: true })
    const timeout = setTimeout(abort, 15000)
    try {
      const response = await fetchImpl(baseUrl + path, { ...options, signal: controller.signal,
        headers: { ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...options.headers,
          ...(credential ? { Authorization: `Bearer ${credential}` } : {}) } })
      if (response.status === 401) {
        if (credential === token) clear()
        throw new Error('Session expired or credentials rejected. Sign in again.')
      }
      if (!response.ok) throw new Error(response.status === 403 ? 'Your account cannot perform this action.' : `Request failed (${response.status}). No successful change is confirmed.`)
      return await response.json()
    } catch (error) {
      if (error.name === 'AbortError') throw error
      if (error instanceof TypeError) throw new Error('API unavailable. Check the connection and try again.')
      throw error
    } finally {
      clearTimeout(timeout)
      signal?.removeEventListener('abort', abort)
    }
  }
  return {
    subscribe(listener) { listeners.add(listener); return () => listeners.delete(listener) },
    logout: clear,
    async login(email, password) {
      clear()
      const current = generation
      const result = await request('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) }, null)
      if (typeof result.access_token !== 'string' || result.token_type !== 'bearer') throw new Error('Invalid authentication response')
      const verified = await request('/auth/me', {}, result.access_token)
      if (verified.status !== 'Active' || !['admin', 'officer'].includes(verified.role)) throw new Error('An active approved role is required.')
      let expires
      try { expires = JSON.parse(atob(result.access_token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/'))).exp * 1000 } catch { throw new Error('Invalid authentication expiry') }
      if (!Number.isFinite(expires) || expires <= now()) throw new Error('Authentication has expired')
      if (current !== generation) throw new Error('Sign-in cancelled')
      token = result.access_token; user = verified; expiry = expires
      timer = setTimeout(clear, Math.min(2147483647, expiry - now()))
      listeners.forEach(listener => listener(user))
      return user.role
    },
    async authorizedRequest(path, options) {
      if (!token || now() >= expiry) { clear(); throw new Error('Sign in to access environmental data.') }
      return request(path, options)
    },
  }
}
