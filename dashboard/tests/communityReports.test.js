import test from 'node:test'
import assert from 'node:assert/strict'
import { parseCommunityReports, activeReports, timeAgo } from '../src/services/communityReports.js'

const now = Date.parse('2026-11-15T12:00:00Z')
const item = (changes = {}) => ({ id: 7, observed_condition: 'Street flooding', perceived_severity: 'Serious',
  location_description: 'Outering Road near the footbridge', latitude: -1.262, longitude: 36.86,
  reported_at: '2026-11-15T09:00:00+00:00', checked_at: '2026-11-15T09:30:00+00:00', visible_until: '2026-11-16T09:00:00+00:00', ...changes })
const payload = (items) => ({ contract_version: 'community-reports-public-v1', window_hours: 24, location_precision_m: 110, checked_at: '2026-11-15T12:00:00Z', items })

test('checked reports are shown only during their 24-hour window', () => {
  assert.equal(parseCommunityReports(payload([item()]), now).items.length, 1)
  const expired = item({ id: 8, reported_at: '2026-11-14T11:00:00+00:00', visible_until: '2026-11-15T11:00:00+00:00' })
  assert.deepEqual(parseCommunityReports(payload([item(), expired]), now).items.map(r => r.id), [7])
  assert.equal(activeReports([item()], Date.parse('2026-11-16T09:00:00Z')).length, 0)
  assert.equal(timeAgo('2026-11-15T09:00:00Z', now), '3 hours ago')
  assert.equal(timeAgo('2026-11-15T11:20:00Z', now), '40 min ago')
})

test('unexpected or private fields are rejected rather than shown', () => {
  for (const bad of [item({ description: 'private' }), item({ review_note: 'x' }), item({ observed_condition: 'Fire' }),
    item({ latitude: 'x' }), item({ visible_until: '2026-11-17T09:00:00+00:00' }), item({ location_description: 'x'.repeat(251) })])
    assert.throws(() => parseCommunityReports(payload([bad]), now))
  assert.throws(() => parseCommunityReports(payload([item(), item()]), now))
  assert.throws(() => parseCommunityReports({ ...payload([]), contract_version: 'other' }, now))
})
