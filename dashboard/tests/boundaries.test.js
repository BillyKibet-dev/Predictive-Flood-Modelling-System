import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { fetchBoundaries, getBoundaryBounds, normalizeBoundaries, safeSourceUrl, summarizeBoundary } from '../src/services/boundaries.js'
import { STALE_AFTER_MS } from '../src/services/predictions.js'

function collection() {
  const data = JSON.parse(readFileSync(new URL('../../data/boundaries/nairobi_subcounties.geojson', import.meta.url)))
  for (const feature of data.features) feature.properties.monitoring_zone_ids = []
  return data
}
const now = Date.parse('2026-10-25T12:00:00Z')
const zone = (id, risk, timestamp = new Date(now).toISOString()) => ({ id, risk, timestamp })
const feature = (ids) => ({ properties: { monitoring_zone_ids: ids } })

test('accepts all 17 packaged polygons and an empty collection', () => {
  assert.equal(normalizeBoundaries(collection()).features.length, 17)
  assert.deepEqual(normalizeBoundaries({ type: 'FeatureCollection', features: [] }).features, [])
})

test('rejects invalid GeoJSON before it reaches Leaflet', () => {
  for (const payload of [null, {}, { type: 'FeatureCollection', features: null }]) {
    assert.throws(() => normalizeBoundaries(payload))
  }
  const changes = [
    (data) => { data.features.push(data.features[0]) },
    (data) => { data.features[0].properties.monitoring_zone_ids = null },
    (data) => { data.features[0].geometry.type = 'Point' },
    (data) => { data.features[0].geometry.coordinates = [] },
    (data) => { data.features[0].geometry.coordinates[0][0] = [200, -1] },
    (data) => { data.features[0].geometry.coordinates[0].pop() },
    (data) => { data.crs = { type: 'name' } },
  ]
  for (const change of changes) {
    const payload = collection()
    change(payload)
    assert.throws(() => normalizeBoundaries(payload))
  }
})

test('uses spatially assigned IDs, with highest monitored risk across multiple points', () => {
  const data = feature(['a', 'b', 'a'])
  data.properties.name = 'Unrelated administrative name'
  const zones = [zone('a', 'Low'), zone('b', 'High'), zone('outside', 'Extreme')]
  const summary = summarizeBoundary(data, zones, now)
  assert.equal(summary.risk, 'High')
  assert.equal(summary.monitoringCount, 2)
  assert.equal(summary.missingCount, 0)
  assert.deepEqual(summary.monitoredZones, zones.slice(0, 2))
  assert.equal(summary.stale, false)
  assert.equal(summarizeBoundary(data, [zone('a', 'Extreme'), zone('b', 'High')], now).risk, 'Extreme')
})

test('distinguishes unmonitored, missing, partial, and stale predictions without inventing Low', () => {
  assert.equal(summarizeBoundary(feature([]), [], now).risk, 'Unknown')
  const missing = summarizeBoundary(feature(['a']), [], now)
  assert.equal(missing.risk, 'Unknown')
  assert.equal(missing.missingCount, 1)
  assert.equal(summarizeBoundary(feature(['a']), [zone('a', 'Low', null)], now).risk, 'Unknown')
  const partial = summarizeBoundary(feature(['a', 'b']), [zone('a', 'Moderate')], now)
  assert.equal(partial.risk, 'Moderate')
  assert.equal(partial.missingCount, 1)
  const oldTime = new Date(now - STALE_AFTER_MS - 1).toISOString()
  const stale = summarizeBoundary(feature(['a', 'b']), [zone('a', 'High', oldTime), zone('b', 'Low')], now)
  assert.equal(stale.risk, 'High')
  assert.equal(stale.stale, true)
})

test('fits the county in Leaflet latitude/longitude order, falling back to sub-counties', () => {
  const county = JSON.parse(readFileSync(new URL('../../data/boundaries/nairobi_county.geojson', import.meta.url)))
  const expected = getBoundaryBounds(county)
  assert.deepEqual(getBoundaryBounds({ type: 'FeatureCollection', features: [...county.features, ...collection().features] }), expected)
  assert.ok(expected[0][0] < -1 && expected[0][1] > 36)
  assert.ok(expected[1][0] > expected[0][0] && expected[1][1] > expected[0][1])
  assert.ok(getBoundaryBounds(collection()))
  assert.equal(getBoundaryBounds({ features: [] }), null)
  assert.equal(getBoundaryBounds(null), null)
})

test('allows only HTTP source links in popups', () => {
  assert.equal(safeSourceUrl('https://www.geoboundaries.org/'), 'https://www.geoboundaries.org/')
  for (const value of ['javascript:alert(1)', 'data:text/html,test', '/relative', null, 'bad URL']) {
    assert.equal(safeSourceUrl(value), null)
  }
})

test('fetches boundaries independently of predictions and forwards cancellation', async (t) => {
  const controller = new AbortController()
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.equal(url, 'http://localhost:8000/boundaries')
    assert.equal(options.signal, controller.signal)
    assert.equal(options.cache, 'no-store')
    return { ok: true, json: async () => collection() }
  })
  assert.equal((await fetchBoundaries({ signal: controller.signal })).features.length, 17)
})

test('propagates HTTP, invalid response, and network errors for the marker fallback', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => ({ ok: false, status: 503 }))
  await assert.rejects(fetchBoundaries(), /503/)
  globalThis.fetch = async () => ({ ok: true, json: async () => ({}) })
  await assert.rejects(fetchBoundaries(), /Invalid/)
  globalThis.fetch = async () => { throw new TypeError('Failed to fetch') }
  await assert.rejects(fetchBoundaries(), /Failed to fetch/)
})
