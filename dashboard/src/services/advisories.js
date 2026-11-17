import { API_BASE_URL } from './api.js'

// Short, time-limited messages officers post for an area. Expired ones never show.
export function parseAdvisories(payload, now = Date.now()) {
  if (payload?.contract_version !== 'officer-advisories-v1' || !Array.isArray(payload.items)) throw new Error('Advisories could not be verified.')
  for (const a of payload.items) {
    if (!Number.isInteger(a.id) || typeof a.area_id !== 'string' || typeof a.message !== 'string' || !['Advice', 'Warning'].includes(a.level) ||
        !Number.isFinite(Date.parse(a.expires_at)) || 'issued_by' in a || (a.latitude == null) !== (a.longitude == null))
      throw new Error('Advisories could not be verified.')
  }
  return { ...payload, items: activeAdvisories(payload.items, now) }
}

export const activeAdvisories = (items, now = Date.now()) => items.filter(a => Date.parse(a.expires_at) > now)

export async function fetchAdvisories({ signal } = {}) {
  const response = await fetch(`${API_BASE_URL}/advisories/active`, { signal, cache: 'no-store' })
  if (!response.ok) throw new Error('Advisories unavailable')
  return parseAdvisories(await response.json())
}

export const ADVISORY_COLOR = { Advice: '#0369a1', Warning: '#b45309' }
