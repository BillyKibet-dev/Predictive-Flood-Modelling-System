import assert from 'node:assert/strict'
import test from 'node:test'
import { snapshotPath, validateOutlook, validateSnapshots, nairobiTime, rainfallText, periodLabel } from '../src/services/forecastOutlook.js'

// Explicit synthetic DTO for client contract tests, not source or performance evidence.
const start = Date.parse('2026-11-08T21:00:00Z')
const stamp = hours => new Date(start + hours * 3600000).toISOString()
const sid = 'd2b44d6c-b5ef-5a3b-b731-c80db64857ce'
function fixture() {
  const zones = ['cbd', 'dagoretti', 'embakasi', 'kasarani', 'kibera', 'mathare', 'ruaraka', 'westlands'].map(zone_id => ({
    zone_id, name: zone_id, monitoring_point: { latitude: -1.2, longitude: 36.8 },
    returned_grid_point: { latitude: -1.25, longitude: 36.75 }, returned_elevation_m: 1700,
    source_quality: 'PARTIAL', target_quality: 'PASSED', warnings: ['MISSING_OR_INVALID_VALUES_OUTSIDE_TARGET'],
    rainfall_mm: 0, valid_rainfall_intervals: 24,
    hourly_rainfall: Array.from({ length: 24 }, (_, i) => ({ interval_start: stamp(i), interval_end: stamp(i + 1), precipitation_mm: 0 })),
    hourly_weather: Array.from({ length: 24 }, (_, i) => ({ valid_at: stamp(i), temperature_2m: 20, relative_humidity_2m: 80, wind_speed_10m: 4, soil_moisture_0_to_7cm: .3 })),
    shared_grid_zone_ids: ['cbd', zone_id], identical_weather_zone_ids: ['cbd', zone_id],
  }))
  return { information_type: 'numerical_weather_forecast', status: 'AVAILABLE', selection: 'current_or_upcoming',
    checked_at: stamp(1), timezone: 'Africa/Nairobi', model_inference_performed: false, collection_automatic: false,
    limitations: ['Weather, not flood risk.'], explanation: 'Synthetic contract fixture only.',
    snapshot: { snapshot_id: sid, source_model: 'ecmwf_ifs', forecast_initialization: '2026-11-07T12:00:00Z',
      issue_cutoff: '2026-11-08T03:00:00Z', target_start: stamp(0), target_end: stamp(24), period_status: 'CURRENT_PERIOD',
      effective_readiness: 'READY_FOR_SHADOW_SNAPSHOT', source_quality: 'PARTIAL', target_quality: 'PASSED',
      source_received_at: '2026-11-07T21:21:44.888183Z', source_request_started_at: '2026-11-07T21:21:40Z',
      source_stored_at: '2026-11-07T21:21:45Z', source_publication_at: null, receipt_age_hours: 26, run_age_hours: 40,
      weather_units: { precipitation: 'mm', temperature_2m: '°C', relative_humidity_2m: '%', wind_speed_10m: 'km/h', soil_moisture_0_to_7cm: 'm³/m³' }, zones } }
}

test('partial source with complete target preserves zero and shared values', () => {
  const body = fixture()
  assert.equal(validateOutlook(body).snapshot.zones[0].rainfall_mm, 0)
  assert.equal(rainfallText(0), '0.00 mm')
  for (const value of [null, undefined, NaN, -1, '0']) assert.equal(rainfallText(value), 'Unavailable')
  assert.ok(body.snapshot.zones[1].shared_grid_zone_ids.includes('cbd'))
})
test('explicit archive requires matching snapshot and never passes as current', () => {
  const b = fixture(); b.snapshot.period_status = 'ARCHIVED'; b.checked_at = stamp(24)
  assert.throws(() => validateOutlook(b))
  b.selection = 'explicit_snapshot'
  assert.equal(validateOutlook(b, sid).snapshot.period_status, 'ARCHIVED')
  assert.throws(() => validateOutlook(b, 'a'.repeat(36)))
  assert.match(periodLabel('ARCHIVED'), /Archived/)
})
test('no current or corrupt evidence cannot carry stale weather values', () => {
  for (const status of ['NO_CURRENT_FORECAST', 'UNAVAILABLE']) {
    const b = { ...fixture(), status, snapshot: null }
    assert.equal(validateOutlook(b).snapshot, null)
    assert.throws(() => validateOutlook({ ...b, snapshot: fixture().snapshot }))
  }
})
test('expired target cannot masquerade as current even if its status flag says current', () => {
  const b = fixture(); b.checked_at = stamp(24)
  assert.throws(() => validateOutlook(b))
  assert.throws(() => validateSnapshots({ items: [b.snapshot], total: 1, checked_at: b.checked_at }))
})
test('target must contain the exact 24 preceding-hour amounts in mm', () => {
  for (const mutate of [
    b => b.snapshot.weather_units.precipitation = 'mm/hr',
    b => b.snapshot.zones[0].hourly_rainfall.pop(),
    b => b.snapshot.zones[0].hourly_rainfall[0].precipitation_mm = null,
    b => b.snapshot.zones[0].hourly_rainfall[0].interval_start = stamp(-1),
    b => b.snapshot.zones[0].hourly_rainfall[1] = b.snapshot.zones[0].hourly_rainfall[0],
    b => b.snapshot.zones[0].rainfall_mm = 2,
    b => b.snapshot.target_end = stamp(23),
    b => b.snapshot.target_quality = 'FAILED',
    b => b.snapshot.zones[0].target_quality = 'FAILED',
  ]) { const b = fixture(); mutate(b); assert.throws(() => validateOutlook(b)) }
})
test('unsupported instantaneous fields, unverified sources and model substitution are rejected', () => {
  for (const mutate of [
    b => b.information_type = 'historical_proxy_risk',
    b => b.model_inference_performed = true,
    b => b.collection_automatic = true,
    b => b.snapshot.source_model = 'best_match',
    b => b.snapshot.effective_readiness = 'READY_AS_RECORDED',
    b => b.snapshot.zones[0].hourly_weather[0].soil_moisture_0_to_7cm = null,
    b => b.snapshot.zones[0].hourly_weather[0].relative_humidity_2m = 101,
    b => b.snapshot.zones[0].shared_grid_zone_ids = ['unknown'],
    b => b.snapshot.zones[0].returned_grid_point.latitude = NaN,
    b => b.snapshot.zones[1].zone_id = 'cbd',
  ]) { const b = fixture(); mutate(b); assert.throws(() => validateOutlook(b)) }
})
test('catalogue is metadata only; query isolates exact snapshot and EAT formatting is explicit', () => {
  const b = fixture()
  const list = { items: [b.snapshot], total: 1, checked_at: b.checked_at }
  assert.equal(validateSnapshots(list).items.length, 1)
  assert.throws(() => validateSnapshots({ ...list, total: 0 }))
  assert.equal(new URLSearchParams(snapshotPath(sid).split('?')[1]).get('snapshot_id'), sid)
  assert.equal(snapshotPath(), '/api/v1/weather-outlook')
  assert.match(nairobiTime(stamp(0)), /9 Nov 2026, 00:00 EAT/)
  assert.equal(nairobiTime(null), 'Unavailable')
})
