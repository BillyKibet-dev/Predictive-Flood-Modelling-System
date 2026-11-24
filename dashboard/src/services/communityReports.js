import { translate } from '../i18n/strings.js'
import { API_BASE_URL } from './api.js'
import { REPORT_CONDITIONS, REPORT_SEVERITIES } from './reports.js'

const VERSION = 'community-reports-public-v1'
const DAY = 24 * 3600000
const time = value => typeof value === 'string' && Number.isFinite(Date.parse(value))

// Staff-checked community reports for the public map. Anything unexpected is rejected rather
// than shown; reports leave the map 24 hours after they were made.
export function parseCommunityReports(payload, now = Date.now()) {
  if (payload?.contract_version !== VERSION || payload.window_hours !== 24 || !Array.isArray(payload.items))
    throw new Error('Community reports could not be verified.')
  const ids = new Set()
  for (const r of payload.items) {
    if (!Number.isInteger(r.id) || ids.has(r.id) || !REPORT_CONDITIONS.includes(r.observed_condition) ||
        !REPORT_SEVERITIES.includes(r.perceived_severity) || !Number.isFinite(r.latitude) || !Number.isFinite(r.longitude) ||
        Math.abs(r.latitude) > 90 || Math.abs(r.longitude) > 180 || !time(r.reported_at) || !time(r.checked_at) || !time(r.visible_until) ||
        Date.parse(r.visible_until) - Date.parse(r.reported_at) !== DAY ||
        !(r.location_description === null || (typeof r.location_description === 'string' && r.location_description.length <= 250)) ||
        'description' in r || 'review_note' in r)
      throw new Error('Community reports could not be verified.')
    ids.add(r.id)
  }
  return { ...payload, items: activeReports(payload.items, now) }
}

export function activeReports(items, now = Date.now()) {
  return items.filter(r => Date.parse(r.reported_at) <= now && now < Date.parse(r.visible_until))
}

export function timeAgo(value, now = Date.now(), lang = 'en') {
  const minutes = Math.max(0, Math.round((now - Date.parse(value)) / 60000))
  if (minutes < 1) return translate(lang, 'ago.now')
  if (minutes < 60) return translate(lang, 'ago.min', { n: minutes })
  const hours = Math.round(minutes / 60)
  // Past two days, days read better than "386 hours".
  if (hours >= 48) return translate(lang, 'ago.days', { n: Math.round(hours / 24) })
  return translate(lang, hours === 1 ? 'ago.hour' : 'ago.hours', { n: hours })
}

export async function fetchCommunityReports({ signal } = {}) {
  const response = await fetch(`${API_BASE_URL}/community-reports/recent`, { signal, cache: 'no-store' })
  if (!response.ok) throw new Error('Community reports unavailable')
  return parseCommunityReports(await response.json())
}
