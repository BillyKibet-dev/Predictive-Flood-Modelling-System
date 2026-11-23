import assert from 'node:assert/strict'
import test from 'node:test'
import { findingsCount, parseRoute, pinnedPlace, tapTarget } from '../src/services/routes.js'
import { parseAdvisories } from '../src/services/advisories.js'
import { checkReportStatus, cleanReference, uploadReportPhoto } from '../src/services/reports.js'
import { forgetReport, rememberReport, savedReports } from '../src/services/myReports.js'

const route = { contract_version: 'route-check-v1', geometry: [[-1.31, 36.81], [-1.29, 36.82]], distance_m: 3800, duration_s: 420,
  reports: [], advisories: [], crossings: [], places: [{ name: 'Uhuru', category: 'Moderate', susceptibility: 'Medium' }], avoided: { requested: false } }

test('a route with only ordinary places reports nothing to know, but never calls it safe', () => {
  assert.equal(findingsCount(parseRoute(route)), 0)
  assert.equal(findingsCount({ ...route, crossings: [{ name: 'Ngong River' }], places: [{ category: 'Moderate', susceptibility: 'Higher' }] }), 2)
  assert.throws(() => parseRoute({ ...route, geometry: [[-1.3, 36.8]] }))
})

test('tapping the map fills the chosen end, else the first empty one, else nothing', () => {
  const a = { latitude: -1.31, longitude: 36.81 }
  assert.equal(tapTarget(null, null, null), 'start')
  assert.equal(tapTarget(null, a, null), 'end')
  assert.equal(tapTarget(null, a, a), null, 'both set: a stray tap changes nothing')
  assert.equal(tapTarget('start', a, a), 'start', 'unless the person asked to re-choose one')
  const pinned = pinnedPlace({ lat: -1.310123456, lng: 36.813749 }, 'Point on the map')
  assert.deepEqual(pinned, { label: 'Point on the map', latitude: -1.3101, longitude: 36.8137, pinned: true })
})

test('advisories: expired ones drop out and staff names are refused', () => {
  const now = Date.parse('2026-11-15T12:00:00Z')
  const item = { id: 1, area_id: 'a', message: 'Avoid the underpass', level: 'Warning', expires_at: '2026-11-15T13:00:00Z', latitude: null, longitude: null }
  assert.equal(parseAdvisories({ contract_version: 'officer-advisories-v1', items: [item] }, now).items.length, 1)
  assert.equal(parseAdvisories({ contract_version: 'officer-advisories-v1', items: [{ ...item, expires_at: '2026-11-15T11:00:00Z' }] }, now).items.length, 0)
  assert.throws(() => parseAdvisories({ contract_version: 'officer-advisories-v1', items: [{ ...item, issued_by: 'Officer' }] }, now))
})

test('a reference is cleaned however it is typed; impossible ones are refused before sending', () => {
  for (const typed of ['FW-K7Q2M9', 'fw k7q2m9', 'K7Q2M9', ' #FW-K7Q2M9 ']) assert.equal(cleanReference(typed), 'FW-K7Q2M9')
  assert.equal(cleanReference('k7q2 m9xd'), 'K7Q2-M9XD', 'older 8-character codes still work')
  for (const bad of ['', '42', 'FW-K7Q', 'FW-K7Q2M0', 'FW-K7Q2MIX', 'hello world']) assert.equal(cleanReference(bad), null, bad)
})

test('status check sends only the reference, in the body', async (t) => {
  await assert.rejects(checkReportStatus('abc'), /FW-K7Q2M9/)
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.ok(url.endsWith('/citizen-report/status') && !url.includes('K7Q2'))
    assert.deepEqual(JSON.parse(options.body), { reference: 'FW-K7Q2M9' })
    return { ok: true, status: 200, json: async () => ({ reference: 'FW-K7Q2M9', status_text: 'Received.', review_status: 'New' }) }
  })
  assert.equal((await checkReportStatus('fw-k7q2m9')).review_status, 'New')
})

test('older reports can still be checked with their number and code', async (t) => {
  await assert.rejects(checkReportStatus('abc', 'K7Q2-M9XD'), /reference number/)
  await assert.rejects(checkReportStatus('42', 'short'), /8-character code/)
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.deepEqual(JSON.parse(options.body), { reference: 42, code: 'K7Q2-M9XD' })
    return { ok: true, status: 200, json: async () => ({ reference: '42', status_text: 'Received.', review_status: 'New' }) }
  })
  assert.equal((await checkReportStatus('#42', ' K7Q2-M9XD ')).review_status, 'New')
})

test('references sent from this device are remembered newest first, without duplicates', () => {
  const store = new Map(), storage = { getItem: k => store.get(k) ?? null, setItem: (k, v) => store.set(k, v) }
  rememberReport({ reference: 'FW-AAAAAA', sentAt: '2026-11-20T10:00:00Z' }, storage)
  rememberReport({ reference: 'FW-BBBBBB', sentAt: '2026-11-21T10:00:00Z' }, storage)
  rememberReport({ reference: 'FW-AAAAAA', sentAt: '2026-11-20T10:00:00Z' }, storage)
  assert.deepEqual(savedReports(storage).map(i => i.reference), ['FW-AAAAAA', 'FW-BBBBBB'])
  assert.deepEqual(forgetReport('FW-AAAAAA', storage).map(i => i.reference), ['FW-BBBBBB'])
  const broken = { getItem: () => { throw new Error('blocked') }, setItem: () => { throw new Error('blocked') } }
  assert.deepEqual(savedReports(broken), [], 'blocked storage never breaks the page')
  assert.doesNotThrow(() => rememberReport({ reference: 'FW-CCCCCC', sentAt: 'x' }, broken))
})

test('photos are checked for type and size before upload', async () => {
  await assert.rejects(uploadReportPhoto(1, 'K7Q2-M9XD', { type: 'application/pdf', size: 10 }), /JPEG, PNG or WebP/)
  await assert.rejects(uploadReportPhoto(1, 'K7Q2-M9XD', { type: 'image/jpeg', size: 9 * 1024 * 1024 }), /8 MB/)
})
