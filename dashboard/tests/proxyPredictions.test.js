import assert from 'node:assert/strict'
import test from 'node:test'
import {
  DEFAULT_REPLAY_DATE, fetchProxyDashboard, fetchProxyModel, formatTargetDate, formatZoneScore,
  isZonePredictionStale, nextCalendarDate, normalizeProxyDashboard, normalizeProxyModel,
  predictionViewConfiguration, PROXY_CLASSES, PROXY_TASK, readableReason, validCalendarDate, zoneStatusLabel,
} from '../src/services/proxyPredictions.js'
import { createPredictionPoller } from '../src/services/predictionPolling.js'
import { summarizeBoundary } from '../src/services/boundaries.js'

const timing = {
  issued_at: '2024-05-01T00:00:00+03:00', executed_at: '2026-11-06T12:00:00+03:00',
  input_date: '2024-04-30', forecast_target_date: '2024-05-01', forecast_horizon: 'next_calendar_day',
  data_as_of: null,
}
const zoneInfo = { id: 'mathare', name: 'Mathare', sub_county: 'Starehe', latitude: -1.26, longitude: 36.86 }

function zone(overrides = {}) {
  return {
    zone: { ...zoneInfo }, status: 'SUCCESS', reason_codes: [], risk_class: 2, risk_level: 'High',
    model_class_score: 0.6, proxy_class_scores: { Low: 0.1, Moderate: 0.2, High: 0.6, Extreme: 0.1 },
    flood_probability: null, flood_probability_reason: 'NOT_CALIBRATED_TO_OBSERVED_FLOODS',
    freshness: 'HISTORICAL_REPLAY', source_metadata: { rainfall: 'historical zone-associated CHIRPS' },
    limitation_flags: ['STATIC_TERRAIN_PROXY', 'COARSE_WEATHER_GRID'], ...timing, ...overrides,
  }
}

function snapshot(overrides = {}) {
  return { mode: 'historical_replay', status: 'SUCCESS', model_version: 'nextday_proxy_v1',
    model_task_type: PROXY_TASK, ...timing, blockers: ['CHIRPS_RELEASE_TIMES_UNVERIFIED'],
    limitation_flags: ['NOT_OBSERVED_FLOOD_LABELS'], zones: [zone()], ...overrides }
}

function model(overrides = {}) {
  return { model_version: 'nextday_proxy_v1', model_task_type: PROXY_TASK, artifact_hash: 'a'.repeat(64),
    loaded: true, status: 'AVAILABLE', feature_count: 20, classes: [...PROXY_CLASSES],
    operational_status: 'INSUFFICIENT_DATA', emergency_alert_delivery_enabled: false,
    evaluation: { rows: 4, test_target_dates: ['2024-01-01', '2025-12-31'],
      metrics: { accuracy: 0.8117305061559508, macro_f1: 0.6481525953286972, weighted_f1: 0.816837238590005,
        high_recall: 0.6262975778546713, extreme_recall: 0.3377777777777778 },
      per_class: PROXY_CLASSES.map((name) => ({ proxy_class: name, precision: 0.5, recall: 0.5, 'f1-score': 0.5, support: 1 })) },
    blockers: ['CHIRPS_RELEASE_TIMES_UNVERIFIED'], limitations: ['Scores are not calibrated flood probabilities.'],
    runtime: { python: '3.12.1', xgboost: '3.1.3' }, ...overrides }
}

test('keeps the legacy, v1 live status and explicitly dated replay selections separate', () => {
  assert.deepEqual(predictionViewConfiguration('legacy'), { view: 'legacy', mode: 'legacy', inputDate: null, key: 'legacy' })
  assert.deepEqual(predictionViewConfiguration('v1_live'), { view: 'v1_live', mode: 'live', inputDate: null, key: 'live' })
  assert.equal(predictionViewConfiguration('v1_replay').inputDate, DEFAULT_REPLAY_DATE)
  assert.notEqual(predictionViewConfiguration('v1_replay', '2024-04-30').key,
    predictionViewConfiguration('v1_replay', '2024-05-01').key)
  for (const view of ['automatic', 'next_6_hours', undefined]) assert.throws(() => predictionViewConfiguration(view))
  assert.throws(() => predictionViewConfiguration('v1_replay', '2024-02-30'))
})

test('validates true calendar days and next-day horizon across leap/month/year boundaries', () => {
  for (const date of ['2024-02-29', '2024-04-30', '2025-12-31']) assert.equal(validCalendarDate(date), true)
  for (const date of ['2023-02-29', '2024-02-30', '2024-13-01', '0000-01-01', '', null, '2024-04-30T12:00:00Z']) {
    assert.equal(validCalendarDate(date), false)
  }
  assert.equal(nextCalendarDate('2024-02-28'), '2024-02-29')
  assert.equal(nextCalendarDate('2024-02-29'), '2024-03-01')
  assert.equal(nextCalendarDate('2025-12-31'), '2026-01-01')
  assert.equal(nextCalendarDate('invalid'), null)
  assert.equal(formatTargetDate('2024-05-01'), '01 May 2024')
  assert.equal(formatTargetDate(null), 'Unavailable')
})

test('normalizes historical per-zone proxy scores without a flood-probability or legacy fallback', () => {
  const data = normalizeProxyDashboard(snapshot(), { mode: 'historical_replay', inputDate: '2024-04-30' })
  assert.equal(data.mode, 'historical_replay')
  assert.equal(data.forecastTargetDate, '2024-05-01')
  assert.equal(data.activeAlerts, null)
  assert.equal(data.dataAsOf, null)
  assert.equal(data.zones[0].risk, 'High')
  assert.equal(data.zones[0].confidence, 0.6)
  assert.equal(data.zones[0].floodProbability, null)
  assert.equal(data.zones[0].floodProbabilityReason, 'NOT_CALIBRATED_TO_OBSERVED_FLOODS')
  assert.deepEqual(Object.keys(data.zones[0].proxyClassScores), PROXY_CLASSES)
  assert.deepEqual(data.zones[0].sourceMetadata, { rainfall: 'historical zone-associated CHIRPS' })
  assert.equal(formatZoneScore(data.zones[0]), '0.6000')
  assert.equal(data.lastUpdated, timing.executed_at)
})

test('current v1 live status stays unavailable and never accepts an unapproved live success', () => {
  const unavailable = zone({ status: 'INSUFFICIENT_DATA', risk_class: null, risk_level: 'Unknown', model_class_score: null,
    proxy_class_scores: null, freshness: 'UNAVAILABLE', reason_codes: ['MISSING_ZONE_TERRAIN'], executed_at: null })
  const data = normalizeProxyDashboard(snapshot({ mode: 'live', status: 'INSUFFICIENT_DATA', executed_at: null, zones: [unavailable] }))
  assert.equal(data.zones[0].risk, 'Unknown')
  assert.equal(data.zones[0].confidence, null)
  assert.equal(data.zones[0].timestamp, null)
  assert.equal(data.lastUpdated, null)
  assert.deepEqual(data.zones[0].reasonCodes, ['MISSING_ZONE_TERRAIN'])
  assert.throws(() => normalizeProxyDashboard(snapshot({ mode: 'live' })), /not been enabled/)
})

test('stale and failed per-zone results are Unknown even if a response contains an older score', () => {
  for (const status of ['STALE_DATA', 'INSUFFICIENT_DATA', 'MODEL_UNAVAILABLE', 'FAILED']) {
    const data = normalizeProxyDashboard(snapshot({ status: 'PARTIAL', zones: [zone({ status, freshness: status })] }))
    assert.equal(data.zones[0].risk, 'Unknown')
    assert.equal(data.zones[0].confidence, null)
    assert.equal(data.zones[0].proxyClassScores, null)
    assert.equal(data.zones[0].timestamp, null)
    assert.equal(data.lastUpdated, null)
  }
})

test('research replay age is not converted into a current stale forecast or emergency warning', () => {
  const data = normalizeProxyDashboard(snapshot())
  const replay = data.zones[0]
  assert.equal(isZonePredictionStale(replay, Date.parse('2030-01-01T00:00:00Z')), false)
  assert.equal(zoneStatusLabel(replay), 'Historical research replay')
  assert.equal(isZonePredictionStale({ ...replay, status: 'STALE_DATA' }), true)
  assert.match(zoneStatusLabel({ ...replay, status: 'STALE_DATA' }), /Stale/)
  assert.equal(isZonePredictionStale({ timestamp: '2024-01-01T00:00:00Z' }, Date.parse('2026-01-01')), true)
  assert.equal(formatZoneScore({ confidence: 0.6 }), '60%') // Existing legacy display is retained.
  assert.equal(formatZoneScore({ ...replay, confidence: null }), 'Unavailable')
})

test('rejects wrong classes, non-finite/out-of-range scores and invalid probability sums', () => {
  const variants = [
    { risk_level: 'Very High' }, { risk_class: 3 }, { model_class_score: 0.8 }, { model_class_score: NaN },
    { proxy_class_scores: { Low: 0.2, Moderate: 0.2, High: 0.6, Extreme: 0.2 } },
    { proxy_class_scores: { Low: 0.1, Moderate: 0.2, High: Infinity, Extreme: 0.1 } },
    { proxy_class_scores: { Low: -0.1, Moderate: 0.4, High: 0.6, Extreme: 0.1 } },
    { proxy_class_scores: { Low: 0.1, Moderate: 0.2, High: 0.6 } },
    { proxy_class_scores: { Low: 0.1, Moderate: 0.2, High: 0.6, Extreme: 0.1, Extra: 0 } },
    { flood_probability: 0.6 }, { flood_probability_reason: 'CALIBRATED' },
  ]
  for (const change of variants) assert.throws(() => normalizeProxyDashboard(snapshot({ zones: [zone(change)] })))
})

test('rejects mismatched request dates, mixed forecast days and undefined/naive times', () => {
  assert.throws(() => normalizeProxyDashboard(snapshot(), { mode: 'live' }), /mode/)
  assert.throws(() => normalizeProxyDashboard(snapshot(), { inputDate: '2024-05-01' }), /date/)
  assert.throws(() => normalizeProxyDashboard(snapshot({ forecast_target_date: '2024-05-02' })), /horizon/)
  for (const change of [{ issued_at: '2024-05-01T00:00:00' }, { executed_at: undefined }, { input_date: '2024-04-31' },
    { forecast_horizon: 'next_6_hours' }, { forecast_target_date: null }, { issued_at: null }]) {
    assert.throws(() => normalizeProxyDashboard(snapshot({ zones: [zone(change)] })))
  }
})

test('rejects malformed v1 metadata and preserves empty results without invented timestamps', () => {
  for (const value of [null, {}, snapshot({ zones: null }), snapshot({ mode: 'automatic' }), snapshot({ status: 'ONLINE' }),
    snapshot({ model_task_type: 'flood_probability' }), snapshot({ zones: [zone(), zone()] }),
    snapshot({ zones: [zone({ zone: { ...zoneInfo, latitude: 200 } })] }), snapshot({ blockers: null })]) {
    assert.throws(() => normalizeProxyDashboard(value))
  }
  const empty = normalizeProxyDashboard(snapshot({ status: 'INSUFFICIENT_DATA', zones: [], executed_at: null }))
  assert.deepEqual(empty.zones, [])
  assert.equal(empty.lastUpdated, null)
})

test('a partial replay computes boundary colours from eligible records and excludes stale/unavailable ones', () => {
  const data = normalizeProxyDashboard(snapshot({ status: 'PARTIAL', zones: [zone(),
    zone({ zone: { ...zoneInfo, id: 'kibera' }, risk_level: 'Extreme', risk_class: 3, model_class_score: 0.9,
      proxy_class_scores: { Low: 0.03, Moderate: 0.03, High: 0.04, Extreme: 0.9 } }),
    zone({ zone: { ...zoneInfo, id: 'missing' }, status: 'INSUFFICIENT_DATA' })] }))
  const feature = { properties: { monitoring_zone_ids: ['mathare', 'kibera', 'missing'] } }
  const summary = summarizeBoundary(feature, data.zones, Date.parse('2030-01-01'))
  assert.equal(summary.risk, 'Extreme')
  assert.equal(summary.missingCount, 1)
  assert.equal(summary.stale, false)
  const stale = data.zones.map((entry) => ({ ...entry, status: 'STALE_DATA' }))
  const unavailable = summarizeBoundary(feature, stale)
  assert.equal(unavailable.risk, 'Unknown')
  assert.equal(unavailable.missingCount, 3)
  assert.equal(unavailable.stale, true)
})

test('identical zone inputs/scores remain visibly identical without client perturbation', () => {
  const data = normalizeProxyDashboard(snapshot({ zones: [zone(), zone({ zone: { ...zoneInfo, id: 'kibera' } })] }))
  assert.equal(data.zones[0].confidence, data.zones[1].confidence)
  assert.deepEqual(data.zones[0].proxyClassScores, data.zones[1].proxyClassScores)
  assert.notEqual(data.zones[0].id, data.zones[1].id)
})

test('fetches only versioned reads with requested mode/date and forwards abort/no-store', async (t) => {
  const controller = new AbortController()
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.equal(url, 'http://localhost:8000/api/v1/dashboard?mode=historical_replay&input_date=2024-04-30')
    assert.equal(options.signal, controller.signal)
    assert.equal(options.cache, 'no-store')
    assert.equal(options.method, undefined)
    return { ok: true, json: async () => snapshot() }
  })
  assert.equal((await fetchProxyDashboard({ mode: 'historical_replay', inputDate: '2024-04-30', signal: controller.signal })).mode, 'historical_replay')
})

test('invalid selections and failed HTTP requests never fall back to legacy predictions', async (t) => {
  const urls = []
  t.mock.method(globalThis, 'fetch', async (url) => { urls.push(url); return { ok: false, status: 503 } })
  await assert.rejects(fetchProxyDashboard({ mode: 'historical_replay', inputDate: 'bad' }))
  assert.equal(urls.length, 0)
  await assert.rejects(fetchProxyDashboard({ mode: 'live' }), /503/)
  assert.deepEqual(urls, ['http://localhost:8000/api/v1/dashboard?mode=live'])
})

test('rejects server responses for a different replay than the requested date', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => ({ ok: true, json: async () => snapshot() }))
  await assert.rejects(fetchProxyDashboard({ mode: 'historical_replay', inputDate: '2024-05-01' }), /date/)
})

test('loaded model metadata retains the real stored severe-class weaknesses while live status stays blocked', () => {
  const data = normalizeProxyModel(model())
  assert.equal(data.loaded, true)
  assert.equal(data.operationalStatus, 'INSUFFICIENT_DATA')
  assert.equal(data.emergencyAlertDeliveryEnabled, false)
  assert.equal(data.evaluation.metrics.accuracy, 0.8117305061559508)
  assert.equal(data.evaluation.metrics.extreme_recall, 0.3377777777777778)
  assert.deepEqual(data.evaluation.perClass.map((row) => row.name), PROXY_CLASSES)
  assert.equal(normalizeProxyModel(model({ loaded: false, status: 'MODEL_UNAVAILABLE', artifact_hash: null })).loaded, false)
})

test('model panel cannot accept mock/incompatible evaluation, operational approval or emergency-delivery claims', () => {
  for (const change of [{ feature_count: 9 }, { classes: ['Low', 'Moderate', 'High', 'Very High'] },
    { operational_status: 'READY' }, { emergency_alert_delivery_enabled: true }, { artifact_hash: 'bad' },
    { evaluation: null }, { model_task_type: 'observed_flood' }]) assert.throws(() => normalizeProxyModel(model(change)))
  const bad = model()
  bad.evaluation.metrics.extreme_recall = 33.78
  assert.throws(() => normalizeProxyModel(bad))
  const support = model()
  support.evaluation.per_class[0].support = 2
  assert.throws(() => normalizeProxyModel(support), /support/)
})

test('fetches actual v1 metadata without admin credentials and reports endpoint failures', async (t) => {
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.equal(url, 'http://localhost:8000/api/v1/model')
    assert.equal(options.cache, 'no-store')
    assert.equal(options.headers, undefined)
    return { ok: true, json: async () => model() }
  })
  assert.equal((await fetchProxyModel()).featureCount, 20)
  globalThis.fetch = async () => ({ ok: false, status: 503 })
  await assert.rejects(fetchProxyModel(), /503/)
})

test('readable unavailable reasons and status labels never imply calibrated probabilities', () => {
  assert.equal(readableReason('MISSING_CHIRPS_HISTORY'), 'Missing chirps history')
  assert.equal(readableReason(null), 'Unavailable')
  const data = normalizeProxyDashboard(snapshot({ zones: [zone({ status: 'INSUFFICIENT_DATA', freshness: 'UNAVAILABLE' })] }))
  assert.match(zoneStatusLabel(data.zones[0]), /Unavailable/)
  assert.equal(zoneStatusLabel({ timestamp: null }), 'Awaiting prediction')
})

test('a failed replay refresh preserves only its own last successful snapshot', async () => {
  const first = normalizeProxyDashboard(snapshot())
  let calls = 0
  const states = []
  const timers = new Map()
  let id = 0
  const poller = createPredictionPoller({ onChange: (state) => states.push(state),
    load: async () => { if (calls++ === 0) return first; throw new Error('source unavailable') },
    schedule: (callback) => { timers.set(++id, callback); return id }, cancel: (handle) => timers.delete(handle) })
  await poller.refresh()
  await poller.refresh()
  const state = states.at(-1)
  assert.equal(state.data, first)
  assert.equal(state.data.mode, 'historical_replay')
  assert.equal(state.isRefreshing, false)
  assert.ok(state.error)
  poller.stop()
  assert.equal(timers.size, 0)
})
