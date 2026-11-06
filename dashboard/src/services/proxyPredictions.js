import { API_BASE_URL } from './api.js'
import { formatConfidence, isPredictionStale } from './predictions.js'

export const PROXY_CLASSES = ['Low', 'Moderate', 'High', 'Extreme']
export const PROXY_TASK = 'next_day_proxy_risk'
export const DEFAULT_REPLAY_DATE = '2024-04-30'
export const PREDICTION_VIEWS = [
  { value: 'legacy', label: 'Legacy shared weather indication' },
  { value: 'v1_live', label: 'v1 next-day research — live status' },
  { value: 'v1_replay', label: 'v1 historical research replay' },
]
const STATUSES = ['SUCCESS', 'PARTIAL', 'INSUFFICIENT_DATA', 'STALE_DATA', 'MODEL_UNAVAILABLE', 'FAILED']
const PROBABILITY_REASON = 'NOT_CALIBRATED_TO_OBSERVED_FLOODS'

function nonempty(value) {
  return typeof value === 'string' && value.trim().length > 0
}

function textList(value, name) {
  if (!Array.isArray(value) || value.some((item) => !nonempty(item))) throw new Error(`Invalid ${name}`)
  return [...value]
}

export function validCalendarDate(value) {
  return typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value) && Number(value.slice(0, 4)) >= 1 &&
    Number.isFinite(Date.parse(`${value}T00:00:00Z`)) &&
    new Date(`${value}T00:00:00Z`).toISOString().slice(0, 10) === value
}

function calendarDate(value, name) {
  if (value === null) return null
  if (!validCalendarDate(value)) throw new Error(`Invalid ${name}`)
  return value
}

function timestamp(value, name) {
  if (value === null) return null
  if (typeof value !== 'string' || !/(?:Z|[+-]\d{2}:\d{2})$/.test(value) || !Number.isFinite(Date.parse(value))) {
    throw new Error(`Invalid ${name}`)
  }
  return value
}

function boundedScore(value) {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1
}

export function nextCalendarDate(value) {
  if (!validCalendarDate(value)) return null
  return new Date(Date.parse(`${value}T00:00:00Z`) + 86_400_000).toISOString().slice(0, 10)
}

export function formatTargetDate(value) {
  if (!validCalendarDate(value)) return 'Unavailable'
  // A calendar target is not an instant; keep its date unchanged in every browser timezone.
  return new Intl.DateTimeFormat('en-GB', { timeZone: 'UTC', day: '2-digit', month: 'short', year: 'numeric' })
    .format(new Date(`${value}T00:00:00Z`))
}

export function predictionViewConfiguration(view, inputDate = DEFAULT_REPLAY_DATE) {
  if (!PREDICTION_VIEWS.some((item) => item.value === view)) throw new Error('Unsupported prediction view')
  if (view === 'legacy') return { view, mode: 'legacy', inputDate: null, key: 'legacy' }
  if (view === 'v1_live') return { view, mode: 'live', inputDate: null, key: 'live' }
  if (!validCalendarDate(inputDate)) throw new Error('Choose a valid historical input date')
  return { view, mode: 'historical_replay', inputDate, key: `historical_replay:${inputDate}` }
}

function timingFields(payload) {
  const result = {
    issuedAt: timestamp(payload.issued_at, 'issue time'),
    executedAt: timestamp(payload.executed_at, 'execution time'),
    inputDate: calendarDate(payload.input_date, 'input date'),
    forecastTargetDate: calendarDate(payload.forecast_target_date, 'target date'),
    dataAsOf: timestamp(payload.data_as_of, 'data-as-of time'),
    forecastHorizon: payload.forecast_horizon,
  }
  if (result.forecastHorizon !== 'next_calendar_day' ||
      (result.inputDate && result.forecastTargetDate && nextCalendarDate(result.inputDate) !== result.forecastTargetDate)) {
    throw new Error('Invalid next-calendar-day horizon')
  }
  return result
}

function normalizeZone(entry, mode, modelVersion) {
  const zone = entry?.zone
  if (!zone || !nonempty(zone.id) || !nonempty(zone.name) || typeof zone.sub_county !== 'string' ||
      !Number.isFinite(zone.latitude) || Math.abs(zone.latitude) > 90 ||
      !Number.isFinite(zone.longitude) || Math.abs(zone.longitude) > 180 || !STATUSES.includes(entry.status) ||
      entry.flood_probability !== null || entry.flood_probability_reason !== PROBABILITY_REASON ||
      typeof entry.freshness !== 'string' || !entry.source_metadata || typeof entry.source_metadata !== 'object' ||
      Array.isArray(entry.source_metadata)) throw new Error('Invalid v1 zone status')
  const timing = timingFields(entry)
  const available = entry.status === 'SUCCESS' && mode === 'historical_replay' && entry.freshness === 'HISTORICAL_REPLAY'
  let scores = null
  if (entry.status === 'SUCCESS') {
    // This release deliberately has no operational v1 inference path.
    if (!available) throw new Error('Operational v1 inference has not been enabled')
    scores = entry.proxy_class_scores
    if (!Number.isInteger(entry.risk_class) || PROXY_CLASSES[entry.risk_class] !== entry.risk_level ||
        !scores || Object.keys(scores).length !== 4 || PROXY_CLASSES.some((name) => !boundedScore(scores[name])) ||
        Math.abs(PROXY_CLASSES.reduce((sum, name) => sum + scores[name], 0) - 1) > 1e-5 ||
        !boundedScore(entry.model_class_score) ||
        Math.abs(scores[entry.risk_level] - entry.model_class_score) > 1e-6 ||
        Math.abs(Math.max(...PROXY_CLASSES.map((name) => scores[name])) - entry.model_class_score) > 1e-6 ||
        !timing.issuedAt || !timing.executedAt || !timing.inputDate || !timing.forecastTargetDate) {
      throw new Error('Invalid v1 proxy scores or forecast context')
    }
  }
  return {
    id: zone.id, name: zone.name, subCounty: zone.sub_county, lat: zone.latitude, lon: zone.longitude,
    risk: available ? entry.risk_level : 'Unknown',
    confidence: available ? entry.model_class_score : null,
    // Used only for presence/order in common views. Replay age is handled explicitly below.
    timestamp: available ? timing.executedAt : null,
    mode, modelVersion, modelTaskType: PROXY_TASK, status: entry.status,
    reasonCodes: textList(entry.reason_codes, 'zone reason codes'),
    proxyClassScores: available ? Object.fromEntries(PROXY_CLASSES.map((name) => [name, scores[name]])) : null,
    floodProbability: null, floodProbabilityReason: PROBABILITY_REASON,
    freshness: entry.freshness, sourceMetadata: { ...entry.source_metadata },
    limitationFlags: textList(entry.limitation_flags, 'zone limitations'), ...timing,
  }
}

export function normalizeProxyDashboard(payload, expected = {}) {
  if (!payload || !['live', 'historical_replay'].includes(payload.mode) || !STATUSES.includes(payload.status) ||
      payload.model_task_type !== PROXY_TASK || !nonempty(payload.model_version) || !Array.isArray(payload.zones)) {
    throw new Error('Invalid v1 dashboard response')
  }
  if (expected.mode && expected.mode !== payload.mode) throw new Error('Prediction mode does not match the request')
  if (expected.inputDate && expected.inputDate !== payload.input_date) throw new Error('Replay date does not match the request')
  const timing = timingFields(payload)
  const zones = payload.zones.map((entry) => normalizeZone(entry, payload.mode, payload.model_version))
  if (new Set(zones.map((zone) => zone.id)).size !== zones.length) throw new Error('Duplicate v1 zone')
  if (zones.some((zone) => zone.inputDate !== timing.inputDate || zone.forecastTargetDate !== timing.forecastTargetDate)) {
    throw new Error('Mixed forecast dates in v1 dashboard')
  }
  const outputs = zones.map((zone) => zone.timestamp).filter(Boolean)
  return {
    mode: payload.mode, status: payload.status, modelVersion: payload.model_version, modelTaskType: PROXY_TASK,
    zones, lastUpdated: outputs.length ? outputs.reduce((a, b) => Date.parse(a) > Date.parse(b) ? a : b) : null,
    // The v1 research model does not generate emergency alerts. Do not borrow the legacy alert count.
    activeAlerts: null, blockers: textList(payload.blockers, 'live blockers'),
    limitationFlags: textList(payload.limitation_flags, 'limitations'), ...timing,
    predictionContext: { spatialScope: 'zone_associated_proxy', locationSpecific: false, calibratedProbability: false },
  }
}

export async function fetchProxyDashboard({ mode = 'live', inputDate = null, signal } = {}) {
  if (!['live', 'historical_replay'].includes(mode) || (mode === 'historical_replay' && !validCalendarDate(inputDate))) {
    throw new Error('Choose a valid v1 mode and historical input date')
  }
  const query = new URLSearchParams({ mode })
  if (mode === 'historical_replay') query.set('input_date', inputDate)
  const response = await fetch(`${API_BASE_URL}/api/v1/dashboard?${query}`, { signal, cache: 'no-store' })
  if (!response.ok) throw new Error(`v1 dashboard request failed (${response.status})`)
  return normalizeProxyDashboard(await response.json(), { mode, inputDate: mode === 'historical_replay' ? inputDate : null })
}

export function normalizeProxyModel(payload) {
  const evaluation = payload?.evaluation
  if (!payload || !nonempty(payload.model_version) || payload.model_task_type !== PROXY_TASK ||
      typeof payload.loaded !== 'boolean' || !nonempty(payload.status) || payload.feature_count !== 20 ||
      JSON.stringify(payload.classes) !== JSON.stringify(PROXY_CLASSES) ||
      (payload.artifact_hash !== null && !/^[a-f0-9]{64}$/.test(payload.artifact_hash)) ||
      payload.operational_status !== 'INSUFFICIENT_DATA' || payload.emergency_alert_delivery_enabled !== false ||
      !evaluation || !Array.isArray(evaluation.test_target_dates) || evaluation.test_target_dates.length !== 2 ||
      evaluation.test_target_dates.some((date) => !validCalendarDate(date)) ||
      !Number.isInteger(evaluation.rows) || evaluation.rows < 1 || !evaluation.metrics ||
      ['accuracy', 'macro_f1', 'weighted_f1', 'high_recall', 'extreme_recall'].some((key) => !boundedScore(evaluation.metrics[key])) ||
      !Array.isArray(evaluation.per_class) || evaluation.per_class.length !== 4) throw new Error('Invalid v1 model metadata')
  const perClass = PROXY_CLASSES.map((name) => {
    const row = evaluation.per_class.find((entry) => entry.proxy_class === name)
    if (!row || !boundedScore(row.precision) || !boundedScore(row.recall) || !boundedScore(row['f1-score']) ||
        !Number.isInteger(row.support) || row.support < 0) throw new Error('Invalid v1 evaluation class report')
    return { name, precision: row.precision, recall: row.recall, f1: row['f1-score'], support: row.support }
  })
  if (perClass.reduce((sum, row) => sum + row.support, 0) !== evaluation.rows) throw new Error('Invalid v1 evaluation support')
  return {
    modelVersion: payload.model_version, modelTaskType: PROXY_TASK, artifactHash: payload.artifact_hash,
    loaded: payload.loaded, status: payload.status, featureCount: 20, classes: [...PROXY_CLASSES],
    operationalStatus: payload.operational_status, emergencyAlertDeliveryEnabled: false,
    blockers: textList(payload.blockers, 'model blockers'), limitations: textList(payload.limitations, 'model limitations'),
    runtime: payload.runtime && typeof payload.runtime === 'object' ? { ...payload.runtime } : {},
    evaluation: { testTargetDates: [...evaluation.test_target_dates], rows: evaluation.rows,
      metrics: { ...evaluation.metrics }, perClass },
  }
}

export async function fetchProxyModel({ signal } = {}) {
  const response = await fetch(`${API_BASE_URL}/api/v1/model`, { signal, cache: 'no-store' })
  if (!response.ok) throw new Error(`v1 model request failed (${response.status})`)
  return normalizeProxyModel(await response.json())
}

export function isZonePredictionStale(zone, now = Date.now()) {
  if (zone.modelTaskType !== PROXY_TASK) return isPredictionStale(zone.timestamp, now)
  return zone.status === 'STALE_DATA' || ['STALE', 'STALE_DATA'].includes(zone.freshness)
}

export function formatZoneScore(zone) {
  return zone.modelTaskType === PROXY_TASK
    ? (boundedScore(zone.confidence) ? zone.confidence.toFixed(4) : 'Unavailable')
    : formatConfidence(zone.confidence)
}

export function readableReason(value) {
  if (typeof value !== 'string') return 'Unavailable'
  return value.replace(/_/g, ' ').toLowerCase().replace(/^./, (letter) => letter.toUpperCase())
}

export function zoneStatusLabel(zone) {
  if (zone.modelTaskType !== PROXY_TASK) return zone.timestamp ? (isZonePredictionStale(zone) ? 'Older than expected' : 'Available') : 'Awaiting prediction'
  if (isZonePredictionStale(zone)) return 'Stale — indication unavailable'
  if (zone.status === 'SUCCESS' && zone.mode === 'historical_replay') return 'Historical research replay'
  return `Unavailable — ${readableReason(zone.status)}`
}
