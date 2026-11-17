import { normalizeBoundaries } from './boundaries.js'

export const HISTORICAL_PATH = '/api/v1/geospatial/historical-floods/unosat-20240501-nairobi-kiambu'
export const HISTORICAL_STYLES = {
  flood: { color: '#0369a1', fillColor: '#0ea5e9', weight: 1, fillOpacity: .65 },
  coverage: { color: '#7c3aed', fillColor: '#7c3aed', weight: 2, dashArray: '8 5', fillOpacity: .035 },
  cloud: { color: '#475569', fillColor: '#94a3b8', weight: 1, dashArray: '3 3', fillOpacity: .5 },
}
export const POINT_LABELS = {
  OUTSIDE_ANALYSIS: 'Unknown: outside analysed area',
  CLOUD_OBSCURED: 'Unknown: mapped cloud obstruction',
  DETECTION_INTERSECTION: 'Historical detection at this point (not field validated)',
  NO_DETECTION_REPORTED: 'Usable coverage; no detection polygon at this point. Flood absence is unconfirmed.',
}
export function validateHistoricalDataset(body) {
  if (body?.dataset_id !== 'unosat-20240501-nairobi-kiambu' || body.information_type !== 'historical_satellite_observation' ||
    body.acquired_at !== '2024-05-01T08:06:00Z' || body.provider !== 'UNITAR-UNOSAT' || body.product_id !== '3833' ||
    !Array.isArray(body.monitoring_points) || body.monitoring_points.length !== 8 ||
    new Set(body.monitoring_points.map(p => p.zone_id)).size !== 8 || !Array.isArray(body.limitations) ||
    body.monitoring_points.some(p => !POINT_LABELS[p.observation_state] || p.confirmed_flood_free !== null ||
      !Number.isFinite(p.latitude) || !Number.isFinite(p.longitude)) || !Array.isArray(body.administrative_context)) {
    throw new Error('Invalid historical satellite metadata. No layer confirmed.')
  }
  return body
}
export function validateHistoricalLayer(body, kind, metadata) {
  if (!Object.hasOwn(HISTORICAL_STYLES, kind) || body?.dataset_id !== metadata.dataset_id ||
    body.layer_kind !== kind || body.information_type !== 'historical_satellite_observation' ||
    body.acquired_at !== metadata.acquired_at || !Array.isArray(body.features) || !body.features.length || body.features.length > 4 ||
    body.features.some(f => f.properties?.layer_kind !== kind || f.properties?.acquired_at !== metadata.acquired_at)) {
    throw new Error('Invalid historical geometry identity. No layer confirmed.')
  }
  // Reuse existing strict RFC7946 polygon/ring validation through a structural property adapter.
  // The returned features retain their historical properties, not administrative meaning.
  normalizeBoundaries({ ...body, features: body.features.map(f => ({ ...f,
    properties: { ...f.properties, name: 'Historical satellite geometry', admin_level: 0, monitoring_zone_ids: [] } })) })
  return body
}
export async function fetchHistoricalEvidence(authorizedRequest, signal) {
  const [raw, ...layers] = await Promise.all([HISTORICAL_PATH, ...Object.keys(HISTORICAL_STYLES).map(k => HISTORICAL_PATH + '/' + k)]
    .map(path => authorizedRequest(path, { signal })))
  const metadata = validateHistoricalDataset(raw)
  return { metadata, layers: Object.fromEntries(Object.keys(HISTORICAL_STYLES).map((kind, i) => [kind, validateHistoricalLayer(layers[i], kind, metadata)])) }
}
