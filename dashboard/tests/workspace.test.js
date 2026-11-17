import test from 'node:test'
import assert from 'node:assert/strict'
import { monitoringLocations, apiStatus } from '../src/services/workspace.js'

test('public geographic locations cannot carry model class or score fields', () => {
  const [zone] = monitoringLocations([{ id: 'cbd', name: 'CBD', latitude: -1.286, longitude: 36.817,
    risk: 'Extreme', confidence: 1, timestamp: new Date().toISOString() }])
  assert.deepEqual(zone, { id: 'cbd', name: 'CBD', subCounty: '', lat: -1.286, lon: 36.817 })
})

test('bad or duplicate monitoring points are rejected rather than drawn at invented coordinates', () => {
  const p = { id: 'cbd', name: 'CBD', latitude: -1.286, longitude: 36.817 }
  for (const points of [[p, p], [{ ...p, latitude: null }], [{ ...p, longitude: 190 }], [{ ...p, latitude: '-1.286' }]]) {
    assert.throws(() => monitoringLocations(points))
  }
  assert.deepEqual(monitoringLocations([]), [])
})

test('API reachability stays separate from the staff-only binary rainfall research model', () => {
  const result = apiStatus({ status: 'online', environment: 'development',
    binary_rainfall_research: { status: 'AVAILABLE', model_version: 'nextday-rainfall-binary-v1' } })
  assert.equal(result.environment, 'development')
  assert.equal(result.modelStatus, 'AVAILABLE')
  assert.equal(result.modelVersion, 'nextday-rainfall-binary-v1')
  const bare = apiStatus({ status: 'online' })
  assert.equal(bare.modelStatus, null)
  assert.equal(bare.environment, 'Not reported')
  assert.throws(() => apiStatus({ status: 'online', binary_rainfall_research: { status: 1, model_version: 'x' } }))
  assert.throws(() => apiStatus({ status: 'failed' }))
})
