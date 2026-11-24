import assert from 'node:assert/strict'
import test from 'node:test'
import { parseVerification, share, trackRecordHeadline } from '../src/services/staffData.js'

const block = (hits, misses, falseAlarms, quiet) => {
  const n = hits + misses + falseAlarms + quiet
  return { n, hits, misses, false_alarms: falseAlarms, correct_quiet: quiet, pod: null, far: null, csi: null, exact: 0.9, within_one: 1,
    wet: { hits: 0, misses: 0, false_alarms: 0, correct_quiet: n, pod: null, far: null, csi: null },
    confusion: [[n, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]] }
}
const sample = (shown = block(0, 0, 0, 36)) => ({ contract_version: 'live-verification-v1', classes: ['Low', 'Moderate', 'High', 'Extreme'],
  daily: [], place_days: shown.n, days_verified: 1, days_waiting: 0, cell_days: 6, amounts: { mae_mm: 3, bias_mm: 1 }, model_versions: [],
  shown, rule: shown, model_only: shown, method: 'm', limitations: [] })

test('a track record whose counts do not add up is refused', () => {
  assert.equal(parseVerification(sample()).place_days, 36)
  const broken = sample(); broken.shown = { ...broken.shown, hits: 5 }
  assert.throws(() => parseVerification(broken))
  const wrongTotal = sample(); wrongTotal.place_days = 40
  assert.throws(() => parseVerification(wrongTotal))
})

test('the headline is honest about dry spells and small samples', () => {
  assert.match(trackRecordHeadline({ ...sample(), days_verified: 0 }), /No days checked yet/)
  assert.match(trackRecordHeadline(sample()), /cannot be judged yet/)
  assert.match(trackRecordHeadline(sample(block(0, 0, 4, 32))), /false alarms/)
  assert.match(trackRecordHeadline({ ...sample(block(3, 1, 0, 32)), days_verified: 5 }), /5 days checked\. Heavy rain fell on 4 place-days and the map had flagged 3/)
  assert.equal(share(3, 4), '3 of 4'); assert.equal(share(0, 0), '—')
})
