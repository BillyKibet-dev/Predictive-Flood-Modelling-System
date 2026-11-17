import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { exportPath, historyHighlights, monthlyComparison, parseModelCard, parseRainfallHistory } from '../src/services/staffData.js'

// Real server output (generated from the pinned model and CHIRPS files).
const fixture = JSON.parse(readFileSync(new URL('../scripts/fixtures/staff_data.json', import.meta.url), 'utf8'))
const clone = value => JSON.parse(JSON.stringify(value))

test('the model card is accepted only when every metric and the calibration status are present', () => {
  const card = parseModelCard(clone(fixture.model_card))
  assert.equal(card.calibration.calibrated, false)
  assert.equal(card.validation.seasons[0].season, '2024-MAM', 'seasons run in date order')
  for (const broken of [
    c => { c.contract_version = 'model-card-v0' },
    c => { c.live.model_sha256 = 'abc' },
    c => { delete c.validation.model.high_or_above.pod },
    c => { c.calibration.calibrated = true },
    c => { c.validation.seasons[0].model_csi = null },
  ]) {
    const card = clone(fixture.model_card); broken(card)
    assert.throws(() => parseModelCard(card), /could not be verified/)
  }
})

test('rainfall history highlights use complete years only', () => {
  const history = parseRainfallHistory(clone(fixture.rainfall_history))
  const h = historyHighlights(history)
  assert.equal(h.wettestYear.year, 2024)
  assert.ok(h.averageYear > 800 && h.averageYear < 1200)
  assert.equal(h.wettestDay.date, '2021-11-28')
  const months = monthlyComparison(history, 2024)
  assert.equal(months.length, 12)
  assert.equal(months[3].month, 'Apr')
  assert.ok(months[3].year > months[3].average, 'April 2024 was wetter than average')
  assert.equal(monthlyComparison(history, 2026)[11].year, null, 'months not yet recorded are left empty, not zero')
})

test('a changed or partial rainfall history is refused', () => {
  for (const broken of [h => { h.monthly_average.pop() }, h => { h.monthly[0].total_mm = -1 }, h => { h.yearly[0].complete = 'yes' }]) {
    const history = clone(fixture.rainfall_history); broken(history)
    assert.throws(() => parseRainfallHistory(history))
  }
})

test('download addresses leave out empty filters', () => {
  assert.equal(exportPath('/exports/citizen-reports.csv', { start: '', end: '', review_status: '' }), '/exports/citizen-reports.csv')
  assert.equal(exportPath('/exports/citizen-reports.csv', { start: '2026-01-01', end: '', review_status: 'New' }),
    '/exports/citizen-reports.csv?start=2026-01-01&review_status=New')
})
