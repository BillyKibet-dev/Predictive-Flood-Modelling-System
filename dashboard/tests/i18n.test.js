import assert from 'node:assert/strict'
import test from 'node:test'
import { STRINGS, translate } from '../src/i18n/strings.js'
import { plainSummary } from '../src/services/monitoringOutlook.js'
import { timeAgo } from '../src/services/communityReports.js'

test('English and Kiswahili have exactly the same keys, all non-empty', () => {
  const en = Object.keys(STRINGS.en).sort(), sw = Object.keys(STRINGS.sw).sort()
  assert.deepEqual(sw, en)
  for (const lang of ['en', 'sw']) for (const [key, text] of Object.entries(STRINGS[lang])) assert.ok(text.trim(), `${lang}:${key}`)
})

test('placeholders match between languages so no value is lost in translation', () => {
  const names = text => (text.match(/\{\w+\}/g) ?? []).sort()
  for (const key of Object.keys(STRINGS.en)) assert.deepEqual(names(STRINGS.sw[key]), names(STRINGS.en[key]), key)
})

test('values are filled and unknown keys fall back to English, then the key', () => {
  assert.equal(translate('sw', 'route.summary', { km: '3.8', min: 7 }), 'km 3.8 · karibu dakika 7')
  assert.equal(translate('sw', 'not.a.key'), 'not.a.key')
})

test('rain summaries and times read naturally in Kiswahili', () => {
  const point = { status: 'AVAILABLE_FORECAST_RULE_CONTEXT', daily_forecast_rainfall_mm: 24, accumulation7dMm: 60, accumulationComplete: true }
  assert.equal(plainSummary(point, 'sw'), 'Mvua kubwa inatabiriwa kesho (karibu mm 24). Pamoja na mvua ya hivi karibuni, hiyo ni wiki yenye mvua nyingi: karibu mm 60 kwa siku 7.')
  assert.equal(plainSummary(point), 'Heavy rain is forecast tomorrow (about 24 mm). With recent rain, that makes a wet week: about 60 mm over 7 days.')
  const now = Date.parse('2026-11-15T12:00:00Z')
  assert.equal(timeAgo('2026-11-15T10:00:00Z', now, 'sw'), 'saa 2 zilizopita')
  assert.equal(timeAgo('2026-11-15T11:50:00Z', now), '10 min ago')
})
