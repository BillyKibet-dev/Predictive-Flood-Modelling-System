import { API_BASE_URL } from './api.js'
export { EVIDENCE_LABELS } from './hotspots.js'

const REFERENCE_TYPES = new Set(['LANDMARK_REFERENCE','NEIGHBORHOOD_REFERENCE','RELATED_LANDMARK_REFERENCE','RELATED_WATERBODY_REFERENCE','USER_REPORTED_LOCATION'])
export const REFERENCE_LABELS = {
  LANDMARK_REFERENCE: 'Landmark reference',
  NEIGHBORHOOD_REFERENCE: 'Neighbourhood reference',
  RELATED_LANDMARK_REFERENCE: 'Related landmark reference',
  RELATED_WATERBODY_REFERENCE: 'Waterbody reference',
  UNLOCATED: 'Location pending review',
  USER_REPORTED_LOCATION: 'User-supplied monitoring point',
}

export function nearbyWaterSummary(context) {
  if (!context || context.information_type !== 'historical_nearby_water_reference' || context.observation_date !== '2024-05-01' ||
      context.operational_use_allowed !== false || context.confirmed_flood_free != null || context.search_radius_m !== 500) throw new Error('Invalid historical water reference')
  const distance=context.distance_m, status=context.status
  if (['MAPPED_WATER_WITHIN_250M_OF_REFERENCE','MAPPED_WATER_WITHIN_500M_OF_REFERENCE','REFERENCE_INSIDE_2024_MAPPED_WATER'].includes(status)) {
    if (!Number.isFinite(distance) || distance < 0 || distance > 500 ||
        (status === 'MAPPED_WATER_WITHIN_250M_OF_REFERENCE' && distance > 250) ||
        (status === 'MAPPED_WATER_WITHIN_500M_OF_REFERENCE' && distance <= 250) ||
        (status === 'REFERENCE_INSIDE_2024_MAPPED_WATER' && distance !== 0)) throw new Error('Invalid historical water distance')
    return distance === 0 ? 'Reference intersects satellite-mapped water in this historical scene.' : `Satellite-mapped water was approximately ${Math.round(distance)} m from this reference point.`
  }
  if (distance != null) throw new Error('Unknown historical context cannot report a distance')
  const labels={
    REFERENCE_UNLOCATED:'Location unresolved; this historical scene cannot be assessed at the site.',
    REFERENCE_OUTSIDE_2024_SCENE:'This monitoring point is outside the historical scene’s analysis coverage.',
    REFERENCE_IN_2024_CLOUD:'Cloud obscures this reference point in the historical scene.',
    NO_WATER_WITHIN_500M_IN_2024_SCENE:'No water was mapped within the 500 m search window in this scene. This does not establish that the area was flood-free.',
  }
  if (!labels[status]) throw new Error('Unknown historical water state')
  return labels[status]
}

export function parseMonitoringAreas(payload) {
  if (payload?.schema_version !== 'monitoring-area-inventory-v1' || payload.information_type !== 'monitoring_area_inventory' ||
      !Array.isArray(payload.sites) || !Array.isArray(payload.groups) || !Array.isArray(payload.sources)) throw new Error('Invalid monitored areas')
  const groups = new Map(payload.groups.map(g => [g.id,g])), seen = new Set()
  if (groups.size !== payload.groups.length) throw new Error('Repeated parent zone')
  const sites = payload.sites.map(site => {
    if (!site || !/^NFW-S\d{3}$/.test(site.id) || seen.has(site.id) || !site.display_name ||
        groups.get(site.parent_zone_id)?.name !== site.parent_zone_name || !site.location || site.location.field_verified !== false ||
        !site.terrain || !site.vegetation || !site.drainage || !Array.isArray(site.source_ids) ||
        !Array.isArray(site.administrative_context) || ['risk_score','live_flood_status','flood_extent','flood_depth'].some(k => site[k] != null)) throw new Error('Invalid monitored area')
    seen.add(site.id)
    let point = null
    if (site.geometry != null) {
      const c = site.geometry.coordinates
      if (site.geometry.type !== 'Point' || !Array.isArray(c) || c.length !== 2 ||
          !Number.isFinite(c[0]) || Math.abs(c[0]) > 180 || !Number.isFinite(c[1]) || Math.abs(c[1]) > 90 ||
          !REFERENCE_TYPES.has(site.location.status) || JSON.stringify(site.location.coordinates) !== JSON.stringify(c) ||
          site.parent_assignment !== 'REFERENCE_POINT_SPATIAL_JOIN' || site.administrative_context.length !== 1 ||
          site.administrative_context[0].id !== site.parent_zone_id) throw new Error('Invalid area location')
      point = { lat:c[1], lon:c[0] }
    } else if (site.location.status !== 'UNLOCATED' || site.parent_assignment !== 'INVENTORY_GROUP_PENDING_LOCATION' ||
        ['terrain','vegetation','drainage'].some(k => site[k].status !== 'UNAVAILABLE')) throw new Error('Unlocated area contains geographic attributes')
    nearbyWaterSummary(site.nearby_water_reference)
    if (JSON.stringify(site.nearby_water_reference.reference_coordinates) !== JSON.stringify(site.geometry?.coordinates ?? null)) throw new Error('Historical water reference belongs to another point')
    return { ...site, point }
  })
  return { ...payload, sites }
}

export function filterMonitoringAreas(sites, { zone = '', query = '', location = '' } = {}) {
  const text = query.trim().toLowerCase()
  return sites.filter(s => (!zone || s.parent_zone_id === zone) &&
    (!text || `${s.display_name} ${s.name} ${s.id} ${s.parent_zone_name}`.toLowerCase().includes(text)) &&
    (!location || Boolean(s.point) === (location === 'located')))
}

// Shared neighbourhood references remain one physical pin with multiple records.
export function groupAreaPoints(sites) {
  const points = new Map()
  for (const site of sites.filter(s => s.point)) {
    const key = JSON.stringify([site.point.lon,site.point.lat])
    if (!points.has(key)) points.set(key,{ key, point:site.point, sites:[] })
    points.get(key).sites.push(site)
  }
  return [...points.values()]
}

export async function fetchMonitoringAreas({ signal } = {}) {
  const response = await fetch(`${API_BASE_URL}/monitoring-areas`,{ signal })
  if (!response.ok) throw new Error('Monitored areas could not be loaded')
  return parseMonitoringAreas(await response.json())
}
