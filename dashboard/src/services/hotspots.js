import { API_BASE_URL } from './api.js'

export const EVIDENCE_LABELS = {
  OBSERVED_FLOOD_OR_IMPACT: 'Reported historical flooding or impact',
  OFFICIAL_WARNING_NAMED_SITE: 'Named in a reported official warning',
}

export function parseHotspots(payload) {
  if (payload?.schema_version !== 'hotspot-inventory-v1' || payload.information_type !== 'candidate_hotspot_inventory' ||
      !Array.isArray(payload.sites) || !Array.isArray(payload.groups) || !Array.isArray(payload.sources)) throw new Error('Invalid hotspot inventory')
  const seen = new Set()
  const sites = payload.sites.map(site => {
    if (!site || !/^NFW-S\d{3}$/.test(site.id) || seen.has(site.id) || !site.name || !site.group ||
        !EVIDENCE_LABELS[site.evidence_category] || !site.location || !site.terrain || !site.vegetation || !site.drainage ||
        !Array.isArray(site.source_ids) || !Array.isArray(site.administrative_context) ||
        ['risk_score','live_flood_status','flood_extent','flood_depth'].some(k => site[k] != null)) throw new Error('Invalid hotspot site')
    seen.add(site.id)
    let point = null
    if (site.geometry != null) {
      const c = site.geometry.coordinates
      if (site.geometry.type !== 'Point' || !Array.isArray(c) || c.length !== 2 ||
          !Number.isFinite(c[0]) || Math.abs(c[0]) > 180 || !Number.isFinite(c[1]) || Math.abs(c[1]) > 90 ||
          site.location.status !== 'LANDMARK_REFERENCE' || site.location.field_verified !== false ||
          JSON.stringify(site.location.coordinates) !== JSON.stringify(c)) throw new Error('Invalid hotspot location')
      point = { lat: c[1], lon: c[0] }
    } else if (site.location.status !== 'UNLOCATED' || ['terrain','vegetation','drainage'].some(k => site[k].status !== 'UNAVAILABLE')) {
      throw new Error('Unlocated hotspot contains geographic attributes')
    }
    return { ...site, point }
  })
  return { ...payload, sites }
}

export function filterHotspots(sites, { group = '', query = '', location = '' } = {}) {
  const text = query.trim().toLowerCase()
  return sites.filter(s => (!group || s.group === group) && (!text || `${s.name} ${s.subarea_context} ${s.id}`.toLowerCase().includes(text)) &&
    (!location || Boolean(s.point) === (location === 'located')))
}

export async function fetchHotspots({ signal } = {}) {
  const response = await fetch(`${API_BASE_URL}/hotspots`, { signal })
  if (!response.ok) throw new Error('Hotspot inventory could not be loaded')
  return parseHotspots(await response.json())
}
