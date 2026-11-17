import { API_BASE_URL } from './api.js'
import { CLASSES } from './monitoringOutlook.js'

export const INTENSITIES = ['none', 'light', 'moderate', 'heavy']
const local = value => typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value)

// Next 3 h and 3-6 h of forecast rain, and today's category from the same model as tomorrow.
export function parseTodayOutlook(payload) {
  const fail = () => { throw new Error('Same-day outlook could not be verified.') }
  if (payload?.contract_version !== 'today-rainfall-outlook-v1' || !/^\d{4}-\d{2}-\d{2}$/.test(payload.today ?? '') ||
      !Array.isArray(payload.areas) || payload.windows?.length !== 2 || payload.windows.some(w => !local(w.start) || !local(w.end))) fail()
  for (const a of payload.areas) {
    if (typeof a.area_id !== 'string') fail()
    if (a.status !== 'AVAILABLE') continue
    if (!CLASSES.includes(a.category) || a.windows?.length !== 2) fail()
    for (const w of a.windows) {
      if (w.rain_mm === null) continue
      if (!Number.isFinite(w.rain_mm) || w.rain_mm < 0 || !INTENSITIES.includes(w.intensity)) fail()
    }
  }
  return payload
}

export async function fetchTodayOutlook({ signal } = {}) {
  const response = await fetch(`${API_BASE_URL}/monitoring-areas/today`, { signal, cache: 'no-store' })
  if (!response.ok) throw new Error('Same-day outlook unavailable')
  return parseTodayOutlook(await response.json())
}

export const todayPoint = (data, id) => data?.areas.find(a => a.area_id === id && a.status === 'AVAILABLE') ?? null

// Same shape as the tomorrow outlook, so pins and the legend can show either day.
export function todayAsOutlook(today, tomorrow) {
  if (!today) return null
  const areas = today.areas.map(a => ({ area_id: a.area_id, status: a.status, proxy_class: a.status === 'AVAILABLE' ? a.category : null }))
  return { areas, available_count: today.available_count, located_count: today.located_count,
    collection: { target_start: `${today.today}T00:00:00+03:00`, received_at: today.forecast.received_at },
    collection_automatic: tomorrow?.collection_automatic ?? false, configured_interval_hours: tomorrow?.configured_interval_hours ?? null }
}

// "14:00–17:00" from local window labels.
export const windowLabel = w => `${w.start.slice(11, 16)}–${w.end.slice(11, 16)}`
