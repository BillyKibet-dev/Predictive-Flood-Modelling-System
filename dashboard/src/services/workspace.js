// Presentation boundaries: geographic locations never inherit a model's risk fields.
export function monitoringLocations(payload) {
  const seen = new Set()
  if (!Array.isArray(payload)) throw new Error('Invalid monitoring locations')
  return payload.map(zone => {
    if (!zone || typeof zone.id !== 'string' || !zone.id || seen.has(zone.id) ||
        typeof zone.name !== 'string' || !zone.name ||
        !Number.isFinite(zone.latitude) || Math.abs(zone.latitude) > 90 ||
        !Number.isFinite(zone.longitude) || Math.abs(zone.longitude) > 180) throw new Error('Invalid monitoring location')
    seen.add(zone.id)
    return { id: zone.id, name: zone.name, subCounty: zone.sub_county ?? '', lat: zone.latitude, lon: zone.longitude }
  })
}

export function apiStatus(payload) {
  if (payload?.status !== 'online') throw new Error('API status is unavailable')
  const n = payload.binary_rainfall_research
  if (n && (typeof n.status !== 'string' || typeof n.model_version !== 'string')) throw new Error('Invalid service status')
  return { checkedAt: new Date().toISOString(), environment: typeof payload.environment === 'string' ? payload.environment : 'Not reported',
    modelStatus: n?.status ?? null, modelVersion: n?.model_version ?? null }
}
