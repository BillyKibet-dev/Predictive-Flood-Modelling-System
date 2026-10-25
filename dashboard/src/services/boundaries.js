import { RISK_ORDER } from '../constants/colors.js'
import { API_BASE_URL } from './api.js'
import { isPredictionStale } from './predictions.js'

export function normalizeBoundaries(payload) {
  if (payload?.type !== 'FeatureCollection' || !Array.isArray(payload.features) || payload.crs) {
    throw new Error('Invalid boundary collection')
  }
  const ids = new Set()
  for (const feature of payload.features) {
    const properties = feature?.properties
    const geometry = feature?.geometry
    if (
      feature?.type !== 'Feature' || typeof feature.id !== 'string' || ids.has(feature.id) ||
      !properties || typeof properties.name !== 'string' || !Number.isInteger(properties.admin_level) ||
      !Array.isArray(properties.monitoring_zone_ids) || properties.monitoring_zone_ids.some((id) => typeof id !== 'string') ||
      !geometry || !['Polygon', 'MultiPolygon'].includes(geometry.type) || geometry.crs || feature.crs
    ) throw new Error('Invalid administrative boundary')
    ids.add(feature.id)
    const polygons = geometry.type === 'Polygon' ? [geometry.coordinates] : geometry.coordinates
    if (!Array.isArray(polygons) || !polygons.length) throw new Error('Empty boundary geometry')
    for (const polygon of polygons) {
      if (!Array.isArray(polygon) || !polygon.length) throw new Error('Empty polygon')
      for (const ring of polygon) {
        if (!Array.isArray(ring) || ring.length < 4) throw new Error('Invalid polygon ring')
        for (const position of ring) {
          if (!Array.isArray(position) || position.length !== 2 ||
              !position.every(Number.isFinite) || Math.abs(position[0]) > 180 || Math.abs(position[1]) > 90) {
            throw new Error('Invalid longitude/latitude position')
          }
        }
        if (ring[0][0] !== ring.at(-1)[0] || ring[0][1] !== ring.at(-1)[1]) throw new Error('Unclosed polygon ring')
      }
    }
  }
  return payload
}

export async function fetchBoundaries({ signal } = {}) {
  const response = await fetch(`${API_BASE_URL}/boundaries`, { signal, cache: 'no-store' })
  if (!response.ok) throw new Error(`Boundary request failed (${response.status})`)
  return normalizeBoundaries(await response.json())
}

export function summarizeBoundary(feature, zones, now = Date.now()) {
  const ids = [...new Set(feature.properties.monitoring_zone_ids)]
  const monitoredZones = zones.filter((zone) => ids.includes(zone.id))
  const available = monitoredZones.filter((zone) => zone.timestamp && RISK_ORDER.includes(zone.risk))
  const highest = [...available].sort((a, b) => RISK_ORDER.indexOf(b.risk) - RISK_ORDER.indexOf(a.risk))[0]
  return {
    risk: highest?.risk ?? 'Unknown',
    monitoredZones,
    monitoringCount: ids.length,
    missingCount: ids.length - available.length,
    stale: available.some((zone) => isPredictionStale(zone.timestamp, now)),
  }
}

export function getBoundaryBounds(collection) {
  const features = collection?.features ?? []
  const county = features.filter((feature) => feature.properties.admin_level === 1)
  let south = Infinity, west = Infinity, north = -Infinity, east = -Infinity
  for (const feature of county.length ? county : features) {
    const polygons = feature.geometry.type === 'Polygon' ? [feature.geometry.coordinates] : feature.geometry.coordinates
    for (const polygon of polygons) for (const ring of polygon) for (const [lon, lat] of ring) {
      south = Math.min(south, lat); north = Math.max(north, lat)
      west = Math.min(west, lon); east = Math.max(east, lon)
    }
  }
  return Number.isFinite(south) ? [[south, west], [north, east]] : null
}

export function safeSourceUrl(value) {
  try {
    const url = new URL(value)
    return ['https:', 'http:'].includes(url.protocol) ? url.href : null
  } catch { return null }
}
