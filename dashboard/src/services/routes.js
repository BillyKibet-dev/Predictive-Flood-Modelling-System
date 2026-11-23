import { API_BASE_URL } from './api.js'

async function post(path, body, { signal } = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal })
  const result = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Request failed')
  return result
}

// Place search within Nairobi (the server holds the routing key). Called on submit only.
export async function searchPlaces(text, options) {
  const result = await post('/routes/places', { text: text.trim() }, options)
  if (!Array.isArray(result.items) || result.items.some(p => !Number.isFinite(p.latitude) || !Number.isFinite(p.longitude) || typeof p.label !== 'string'))
    throw new Error('Place search could not be verified.')
  return result.items
}

// Street or place name for a point tapped on the map; null when nothing is nearby.
export async function namePoint(latitude, longitude, options) {
  const result = await post('/routes/place-name', { latitude, longitude }, options)
  if (result.label !== null && typeof result.label !== 'string') throw new Error('Place name could not be verified.')
  return result.label
}

// A tapped point, rounded to about 10 m (enough to route, no more precise than needed).
export function pinnedPlace(latlng, label) {
  return { label, latitude: Math.round(latlng.lat * 1e4) / 1e4, longitude: Math.round(latlng.lng * 1e4) / 1e4, pinned: true }
}

// Which end a tap sets: the one being chosen, else the first empty one, else none.
export function tapTarget(picking, start, end) {
  if (picking) return picking
  if (!start) return 'start'
  if (!end) return 'end'
  return null
}

export function parseRoute(result) {
  if (result?.contract_version !== 'route-check-v1' || !Array.isArray(result.geometry) || result.geometry.length < 2 ||
      !['reports', 'advisories', 'crossings', 'places'].every(k => Array.isArray(result[k])) || !Number.isFinite(result.distance_m))
    throw new Error('The route could not be verified.')
  return result
}

export async function checkRoute({ start, end, profile, avoid }, options) {
  return parseRoute(await post('/routes/check', {
    start: { latitude: start.latitude, longitude: start.longitude }, end: { latitude: end.latitude, longitude: end.longitude },
    profile, avoid_reports: Boolean(avoid),
  }, options))
}

// Nothing found is never "safe"; count the things worth knowing.
export function findingsCount(route) {
  const places = route.places.filter(p => ['High', 'Extreme'].includes(p.category) || p.susceptibility === 'Higher')
  return route.reports.length + route.advisories.length + route.crossings.length + places.length
}
