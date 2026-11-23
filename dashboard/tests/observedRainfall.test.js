import assert from 'node:assert/strict'
import test from 'node:test'
import { areaGrid, collectedMonthly, dailyWindow, parseObservedRainfall, recentStats } from '../src/services/staffData.js'

// Five collected days with 3 Nov missing; per-area values for the last days only.
const sample = () => ({
  contract_version: 'observed-rainfall-v1', first_day: '2026-11-01', last_day: '2026-11-06', thresholds_mm: { heavy: 20, very_heavy: 40 },
  areas: [{ id: 'a', name: 'Kibra' }, { id: 'b', name: 'Westlands' }],
  daily: [
    { date: '2026-11-01', nairobi_mm: 2, by_area: null },
    { date: '2026-11-02', nairobi_mm: 24, by_area: null },
    { date: '2026-11-04', nairobi_mm: null, by_area: [null, 3] },
    { date: '2026-11-05', nairobi_mm: 0.4, by_area: [0, 1] },
    { date: '2026-11-06', nairobi_mm: 5, by_area: [9, 1] },
  ],
  monthly: [{ month: '2026-10', total_mm: 120, days: 31 }, { month: '2026-11', total_mm: 31.4, days: 4 }],
  climatology: [...Array(12)].map((_, i) => ({ month: i + 1, average_mm: (i + 1) * 10 })),
})

test('collected rainfall is refused when a day is malformed or negative', () => {
  assert.equal(parseObservedRainfall(sample()).daily.length, 5)
  const bad = sample(); bad.daily[0].nairobi_mm = -1
  assert.throws(() => parseObservedRainfall(bad))
  const wrongWidth = sample(); wrongWidth.daily[4].by_area = [1]
  assert.throws(() => parseObservedRainfall(wrongWidth))
})

test('a day that was never collected is a gap, not a dry day', () => {
  const window = dailyWindow(sample(), 6)
  assert.deepEqual(window.map(d => d.date), ['2026-11-01', '2026-11-02', '2026-11-03', '2026-11-04', '2026-11-05', '2026-11-06'])
  assert.equal(window[2].mm, null); assert.equal(window[2].collected, false)
  assert.equal(window[3].mm, null); assert.equal(window[3].collected, true, 'collected but incomplete is still a gap')
  assert.equal(dailyWindow(sample()).length, 6, 'no range: the whole record')
})

test('tiles: latest day, recent totals over collected days, and days since heavy rain', () => {
  const stats = recentStats(sample())
  assert.equal(stats.latest.date, '2026-11-06')
  assert.equal(stats.week.mm, 31.4); assert.equal(stats.week.days, 4)
  assert.equal(stats.lastHeavy.date, '2026-11-02'); assert.equal(stats.daysSinceHeavy, 4)
  assert.equal(stats.wettest.nairobi_mm, 24); assert.equal(stats.rainyDays30, 3)
})

test('months sit next to the usual amount; part-collected months are flagged', () => {
  const [oct, nov] = collectedMonthly(sample())
  assert.deepEqual([oct.label, oct.average, oct.complete], ['Oct ’26', 100, true])
  assert.deepEqual([nov.label, nov.average, nov.complete, nov.days], ['Nov ’26', 110, false, 4])
})

test('the sub-county grid uses only days with per-area values, wettest area first', () => {
  const grid = areaGrid(sample(), 14)
  assert.deepEqual(grid.dates, ['2026-11-04', '2026-11-05', '2026-11-06'])
  assert.deepEqual(grid.rows.map(r => [r.name, r.total]), [['Kibra', 9], ['Westlands', 5]])
  assert.deepEqual(grid.rows[0].values, [null, 0, 9])
})
