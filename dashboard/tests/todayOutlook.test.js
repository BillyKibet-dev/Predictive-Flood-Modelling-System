import assert from 'node:assert/strict'
import test from 'node:test'
import { parseTodayOutlook, todayAsOutlook, todayPoint, windowLabel } from '../src/services/todayOutlook.js'
import { pointCategory } from '../src/services/monitoringOutlook.js'

const payload = () => ({ contract_version: 'today-rainfall-outlook-v1', today: '2026-11-16', available_count: 1, located_count: 2,
  windows: [{ window: 'next_3h', start: '2026-11-16T14:00', end: '2026-11-16T17:00' }, { window: 'next_3_6h', start: '2026-11-16T17:00', end: '2026-11-16T20:00' }],
  forecast: { run_at: '2026-11-16T00:00:00+00:00', received_at: '2026-11-16T08:05:00+00:00' },
  areas: [{ area_id: 'NFW-S001', status: 'AVAILABLE', category: 'High', windows: [
    { window: 'next_3h', start: '2026-11-16T14:00', end: '2026-11-16T17:00', rain_mm: 12.4, intensity: 'heavy' },
    { window: 'next_3_6h', start: '2026-11-16T17:00', end: '2026-11-16T20:00', rain_mm: null, intensity: null }] },
    { area_id: 'NFW-S002', status: 'UNAVAILABLE' }] })

test('a valid same-day outlook parses; a missing hour stays unknown, never zero', () => {
  const data = parseTodayOutlook(payload())
  assert.equal(todayPoint(data, 'NFW-S001').windows[1].rain_mm, null)
  assert.equal(todayPoint(data, 'NFW-S002'), null)
  assert.equal(windowLabel(data.windows[0]), '14:00–17:00')
})

test('bad categories, intensities or windows are refused', () => {
  for (const broken of [p => { p.areas[0].category = 'Severe' }, p => { p.areas[0].windows[0].intensity = 'torrential' },
    p => { p.windows.pop() }, p => { p.areas[0].windows[0].rain_mm = -1 }]) {
    const p = payload(); broken(p)
    assert.throws(() => parseTodayOutlook(p))
  }
})

test("today's categories colour the same pins as tomorrow's", () => {
  const shaped = todayAsOutlook(parseTodayOutlook(payload()), { collection_automatic: true, configured_interval_hours: 1 })
  assert.equal(pointCategory(shaped, ['NFW-S001']), 'High')
  assert.equal(pointCategory(shaped, ['NFW-S002']), null)
  assert.equal(shaped.collection.target_start, '2026-11-16T00:00:00+03:00')
  assert.equal(shaped.collection_automatic, true)
})
