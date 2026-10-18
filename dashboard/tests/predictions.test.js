import assert from 'node:assert/strict'
import test from 'node:test'
import {
  fetchDashboard, formatConfidence, formatPredictionTime,
  isPredictionStale, normalizeDashboard, STALE_AFTER_MS,
} from '../src/services/predictions.js'

function dashboard(overrides = {}) {
  return {
    zones: [{
      zone: { id: 'mathare', name: 'Mathare', sub_county: 'Starehe', latitude: -1.26, longitude: 36.86 },
      risk_level: 'High', risk_class: 2, confidence_score: 0.81,
      timestamp: '2026-10-18T09:00:00Z',
    }],
    last_updated: '2026-10-18T09:00:00Z', active_alerts: 2, highest_risk: 'High',
    ...overrides,
  }
}

test('maps a real API snapshot to the shared zone view and live alert count', () => {
  const result = normalizeDashboard(dashboard())
  assert.equal(result.activeAlerts, 2)
  assert.equal(result.lastUpdated, '2026-10-18T09:00:00Z')
  assert.deepEqual(result.zones[0], {
    id: 'mathare', name: 'Mathare', subCounty: 'Starehe', lat: -1.26, lon: 36.86,
    risk: 'High', confidence: 0.81, timestamp: '2026-10-18T09:00:00Z',
  })
})

test('missing predictions do not become Low or inherit the API current-time fallback', () => {
  const payload = dashboard()
  payload.zones[0] = { ...payload.zones[0], timestamp: null, risk_level: 'Low', confidence_score: null }
  const result = normalizeDashboard(payload)
  assert.equal(result.zones[0].risk, 'Unknown')
  assert.equal(result.zones[0].confidence, null)
  assert.equal(result.lastUpdated, null)
})

test('empty results stay empty, with no invented last-updated time', () => {
  assert.deepEqual(normalizeDashboard(dashboard({ zones: [], active_alerts: 0 })), {
    zones: [], lastUpdated: null, activeAlerts: 0,
  })
})

test('partial coverage preserves missing zones and chooses the newest real timestamp', () => {
  const payload = dashboard()
  payload.zones.push({
    ...payload.zones[0], zone: { ...payload.zones[0].zone, id: 'kibera' },
    timestamp: '2026-10-18T09:30:00Z',
  }, {
    ...payload.zones[0], zone: { ...payload.zones[0].zone, id: 'cbd' }, timestamp: null,
  })
  payload.last_updated = '2030-01-01T00:00:00Z'
  const result = normalizeDashboard(payload)
  assert.equal(result.lastUpdated, '2026-10-18T09:30:00Z')
  assert.equal(result.zones[2].risk, 'Unknown')
})

test('rejects malformed responses instead of replacing saved data with invalid predictions', () => {
  for (const payload of [null, {}, { zones: [], active_alerts: -1 }, { zones: [], active_alerts: '2' }]) {
    assert.throws(() => normalizeDashboard(payload))
  }
  for (const update of [{ timestamp: 'bad-date' }, { risk_level: 'Severe' }, { zone: null }]) {
    const payload = dashboard()
    payload.zones[0] = { ...payload.zones[0], ...update }
    assert.throws(() => normalizeDashboard(payload))
  }
})

test('staleness uses prediction time rather than the time a request completed', () => {
  const timestamp = '2026-10-18T09:00:00Z'
  const now = Date.parse(timestamp)
  assert.equal(isPredictionStale(timestamp, now + STALE_AFTER_MS), false)
  assert.equal(isPredictionStale(timestamp, now + STALE_AFTER_MS + 1), true)
  assert.equal(isPredictionStale(null, now), false)
})

test('formats prediction times explicitly in Nairobi and handles unavailable values', () => {
  assert.equal(formatPredictionTime('2026-10-18T09:00:00Z'), '18 Oct 2026, 12:00 EAT')
  assert.equal(formatPredictionTime(null), 'Unavailable')
  assert.equal(formatConfidence(null), 'Unavailable')
  assert.equal(formatConfidence(0), '0%')
  assert.equal(formatConfidence(0.81), '81%')
})

test('fetches only the public dashboard, bypassing caches and forwarding cancellation', async (t) => {
  const controller = new AbortController()
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.equal(url, 'http://localhost:8000/dashboard')
    assert.equal(options.cache, 'no-store')
    assert.equal(options.signal, controller.signal)
    assert.equal(options.method, undefined)
    return { ok: true, json: async () => dashboard() }
  })
  const result = await fetchDashboard({ signal: controller.signal })
  assert.equal(result.zones[0].risk, 'High')
})

test('rejects HTTP errors so polling can preserve the previous snapshot', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => ({ ok: false, status: 503 }))
  await assert.rejects(fetchDashboard(), /503/)
})
