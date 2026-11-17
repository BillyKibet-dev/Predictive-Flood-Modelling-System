import { API_BASE_URL } from './api.js'

export const BINARY_RAINFALL_PATH = '/api/research/binary-rainfall/current'

function validScore(value) { return typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1 }

export function normalizeBinaryRainfall(payload) {
  if (!payload || !['AVAILABLE_RESEARCH_ONLY', 'PARTIAL_RESEARCH_ONLY', 'UNAVAILABLE'].includes(payload.status) ||
      !payload.model || !Array.isArray(payload.areas) || typeof payload.target !== 'string' ||
      typeof payload.output_interpretation !== 'string') throw new Error('Invalid binary rainfall research response')
  const areas = payload.areas.map(area => {
    if (!area || typeof area.area_id !== 'string' || typeof area.name !== 'string' || typeof area.status !== 'string') throw new Error('Invalid binary rainfall area')
    if (area.status === 'AVAILABLE_RESEARCH_ONLY' && (!validScore(area.raw_binary_score_uncalibrated) || !['AT_OR_ABOVE_5_MM', 'BELOW_5_MM'].includes(area.rainfall_proxy_class))) throw new Error('Invalid binary rainfall score')
    return { id: area.area_id, name: area.name, parentZoneId: area.parent_zone_id ?? null, status: area.status,
      score: area.raw_binary_score_uncalibrated ?? null, classification: area.rainfall_proxy_class ?? null,
      sharedAreaIds: Array.isArray(area.shared_area_ids) ? area.shared_area_ids : [], reason: area.reason ?? null, features: area.features ?? null }
  })
  return { status: payload.status, checkedAt: payload.checked_at ?? null, model: payload.model, target: payload.target,
    interpretation: payload.output_interpretation, source: payload.source ?? {}, areas,
    limitations: Array.isArray(payload.limitations) ? payload.limitations : [] }
}

export async function fetchBinaryRainfall({ authorizedRequest, signal } = {}) {
  if (authorizedRequest) return normalizeBinaryRainfall(await authorizedRequest(BINARY_RAINFALL_PATH, { signal }))
  const response = await fetch(`${API_BASE_URL}${BINARY_RAINFALL_PATH}`, { signal, cache: 'no-store' })
  if (!response.ok) throw new Error(`Binary rainfall request failed (${response.status})`)
  return normalizeBinaryRainfall(await response.json())
}
