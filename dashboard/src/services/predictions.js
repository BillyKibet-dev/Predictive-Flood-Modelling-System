const env = import.meta.env ?? {}

function positiveMilliseconds(value, fallback) {
  const parsed = Number(value)
  return Number.isFinite(parsed) && parsed >= 1000 && parsed <= 86_400_000 ? parsed : fallback
}

export const POLL_INTERVAL_MS = positiveMilliseconds(env.VITE_PREDICTION_POLL_INTERVAL_MS, 60_000)
export const STALE_AFTER_MS = positiveMilliseconds(env.VITE_PREDICTION_STALE_AFTER_MS, 65 * 60_000)
const API_BASE_URL = (env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/+$/, '')
const RISK_LEVELS = ['Low', 'Moderate', 'High', 'Extreme']

// Keep the API contract at the boundary; pages share one normalized snapshot.
export function normalizeDashboard(payload) {
  if (!Array.isArray(payload?.zones) || !Number.isInteger(payload.active_alerts) || payload.active_alerts < 0) {
    throw new Error('Invalid dashboard response')
  }

  const zones = payload.zones.map((entry) => {
    const zone = entry.zone
    const timestamp = entry.timestamp ?? null
    if (
      !zone || typeof zone.id !== 'string' || typeof zone.name !== 'string' ||
      !Number.isFinite(zone.latitude) || !Number.isFinite(zone.longitude) ||
      (timestamp !== null && !Number.isFinite(Date.parse(timestamp))) ||
      (timestamp !== null && !RISK_LEVELS.includes(entry.risk_level))
    ) {
      throw new Error('Invalid zone prediction')
    }

    return {
      id: zone.id,
      name: zone.name,
      subCounty: zone.sub_county,
      lat: zone.latitude,
      lon: zone.longitude,
      // The API defaults missing predictions to Low. A missing timestamp means unknown risk.
      risk: timestamp === null ? 'Unknown' : entry.risk_level,
      confidence: timestamp === null ? null : (entry.confidence_score ?? null),
      timestamp,
    }
  })

  const timestamps = zones.map((zone) => zone.timestamp).filter(Boolean)
  const lastUpdated = timestamps.length
    ? timestamps.reduce((latest, timestamp) => Date.parse(timestamp) > Date.parse(latest) ? timestamp : latest)
    : null

  // Derive this from actual zone predictions, not the API's current-time fallback.
  return { zones, lastUpdated, activeAlerts: payload.active_alerts }
}

export async function fetchDashboard({ signal } = {}) {
  const response = await fetch(`${API_BASE_URL}/dashboard`, { signal, cache: 'no-store' })
  if (!response.ok) throw new Error(`Dashboard request failed (${response.status})`)
  return normalizeDashboard(await response.json())
}

export function isPredictionStale(timestamp, now = Date.now()) {
  return timestamp !== null && now - Date.parse(timestamp) > STALE_AFTER_MS
}

export function formatPredictionTime(timestamp) {
  if (!timestamp || !Number.isFinite(Date.parse(timestamp))) return 'Unavailable'
  return `${new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Africa/Nairobi', day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(new Date(timestamp))} EAT`
}

export function formatConfidence(value) {
  return typeof value === 'number' && Number.isFinite(value) ? `${Math.round(value * 100)}%` : 'Unavailable'
}
