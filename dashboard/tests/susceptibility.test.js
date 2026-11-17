import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { parseSusceptibility, pointSusceptibility, susceptibilityText, watchClosely, watchOrder } from '../src/services/susceptibility.js'

// The real prepared file the API serves.
const real = JSON.parse(readFileSync(new URL('../../src/api/data/monitoring_susceptibility.json', import.meta.url), 'utf8'))
const clone = value => JSON.parse(JSON.stringify(value))

test('every place parses, and a score must equal its factor points', () => {
  const data = parseSusceptibility(clone(real))
  assert.equal(Object.keys(data.byArea).length, 36)
  const broken = clone(real); broken.rows[0].score += 1
  assert.throws(() => parseSusceptibility(broken), /could not be verified/)
  const dup = clone(real); dup.rows.push(dup.rows[0])
  assert.throws(() => parseSusceptibility(dup))
})

test('plain sentences explain why a place floods easily', () => {
  const data = parseSusceptibility(clone(real))
  assert.match(susceptibilityText(data.byArea['NFW-S013']), /^Floods more easily than most monitored places: low ground \d+ m from Ngong River/)
  assert.match(susceptibilityText(data.byArea['NFW-S021']), /^Higher ground/)
  assert.equal(pointSusceptibility(data, ['NFW-S011', 'NFW-S012']).level, 'Medium')
})

test('heavy rain on an easily flooded place is flagged and ranked first', () => {
  const data = parseSusceptibility(clone(real))
  const higher = data.byArea['NFW-S013'], lower = data.byArea['NFW-S021']
  assert.equal(watchClosely('High', higher), true)
  assert.equal(watchClosely('Moderate', higher), false)
  assert.equal(watchClosely('Extreme', lower), false)
  assert.ok(watchOrder('Moderate', higher) > watchOrder('Moderate', lower))
  assert.ok(watchOrder('High', lower) > watchOrder('Moderate', higher), 'rainfall category comes first')
})
