import { translate } from '../i18n/strings.js'
import { API_BASE_URL } from './api.js'

// How easily each monitored place floods compared with the others (terrain, rivers, the 2024
// satellite water map, sealed ground, past flooding). It does not change with the weather.
export const LEVELS = ['Lower', 'Medium', 'Higher']

export function parseSusceptibility(payload) {
  if (payload?.contract_version !== 'monitoring-susceptibility-v1' || !Array.isArray(payload.rows) || !payload.rows.length)
    throw new Error('Local susceptibility could not be verified.')
  const byArea = {}
  for (const r of payload.rows) {
    if (typeof r.area_id !== 'string' || !LEVELS.includes(r.level) || !Number.isInteger(r.score) || r.score < 0 || r.score > r.max_score ||
        !Array.isArray(r.factors) || r.factors.reduce((s, f) => s + f.points, 0) !== r.score || byArea[r.area_id])
      throw new Error('Local susceptibility could not be verified.')
    byArea[r.area_id] = r
  }
  return { ...payload, byArea }
}

export async function fetchSusceptibility({ signal } = {}) {
  const response = await fetch(`${API_BASE_URL}/monitoring-areas/susceptibility`, { signal })
  if (!response.ok) throw new Error('Local susceptibility unavailable')
  return parseSusceptibility(await response.json())
}

// The highest level among records sharing one pin (they share coordinates, so normally equal).
export function pointSusceptibility(data, ids) {
  const rows = ids.map(id => data?.byArea[id]).filter(Boolean)
  return rows.sort((a, b) => b.score - a.score)[0] ?? null
}

// One plain sentence a resident can understand, in English or Kiswahili.
export function susceptibilityText(row, lang = 'en') {
  if (!row) return null
  const t = (key, values) => translate(lang, key, values)
  const reasons = []
  if (row.height_above_river_m <= 5) reasons.push(t('local.lowGround', { m: row.river_distance_m, river: row.river_name }))
  else if (row.relief_m <= -1) reasons.push(t('local.lower'))
  if (row.satellite_water_m != null && row.satellite_water_m <= 250) reasons.push(t('local.satellite'))
  if (row.observed_flooding) reasons.push(t('local.flooded'))
  return t(`local.${row.level}`, { why: reasons.length ? `: ${reasons.join(', ')}` : '' })
}

// Heavy rain on a place that floods easily: the combination officers should look at first.
export function watchClosely(category, row) {
  return ['High', 'Extreme'].includes(category) && row?.level === 'Higher'
}

// Sort for staff lists: worst rainfall first, then the place that floods most easily.
export function watchOrder(category, row) {
  return (['Low', 'Moderate', 'High', 'Extreme'].indexOf(category) + 1) * 100 + (row?.score ?? 0)
}
