import assert from 'node:assert/strict'
import test from 'node:test'
import { submitCitizenReport, validateCitizenReport } from '../src/services/reports.js'

const form = {
  zone_id: 'mathare', observed_condition: 'Street flooding',
  perceived_severity: 'Serious', description: '  Water near the bridge  ',
}
const savedReport = { id: 42, zone_id: 'mathare', timestamp: '2026-10-18T09:00:00Z' }

test('requires a supported zone, condition, severity, and description length before submission', () => {
  assert.deepEqual(validateCitizenReport(form, ['mathare']), {})
  assert.deepEqual(validateCitizenReport({ ...form, description: '' }, ['mathare']), {})
  const errors = validateCitizenReport({
    zone_id: 'Other', observed_condition: 'Unknown condition', perceived_severity: 'High', description: 'x'.repeat(201),
  }, ['mathare'])
  assert.deepEqual(Object.keys(errors), ['zone_id', 'observed_condition', 'perceived_severity', 'description'])
  assert.ok(validateCitizenReport(form, []).zone_id)
})

test('sends an anonymous report using the backend zone ID and returns the saved reference', async (t) => {
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.equal(url, 'http://localhost:8000/citizen-report')
    assert.equal(options.method, 'POST')
    assert.deepEqual(options.headers, { 'Content-Type': 'application/json' })
    assert.deepEqual(JSON.parse(options.body), { ...form, description: 'Water near the bridge' })
    assert.ok(options.signal instanceof AbortSignal)
    return { status: 201, json: async () => savedReport }
  })
  assert.deepEqual(await submitCitizenReport(form), savedReport)
})

test('normalizes an optional blank description to null', async (t) => {
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.equal(JSON.parse(options.body).description, null)
    return { status: 201, json: async () => savedReport }
  })
  await submitCitizenReport({ ...form, description: '   ' })
})

test('returns a zone-specific error when the selected zone has been removed', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => ({ status: 404 }))
  await assert.rejects(submitCitizenReport(form), (error) => {
    assert.match(error.message, /zone is no longer available/)
    assert.ok(error.fieldErrors.zone_id)
    return true
  })
})

test('maps backend validation errors to accessible form fields', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => ({
    status: 422, json: async () => ({ detail: [{ loc: ['body', 'description'], msg: 'Too long' }] }),
  }))
  await assert.rejects(submitCitizenReport(form), (error) => {
    assert.match(error.fieldErrors.description, /200 characters/)
    assert.match(error.message, /check the report details/)
    return true
  })
})

test('an unexpected server response cannot appear as a saved report', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => ({ status: 500 }))
  await assert.rejects(submitCitizenReport(form), /could not confirm your report/)
})

test('missing or mismatched save confirmation is reported as unconfirmed', async (t) => {
  for (const report of [{}, { ...savedReport, id: 0 }, { ...savedReport, zone_id: 'kibera' }, { ...savedReport, timestamp: 'bad' }]) {
    const mocked = t.mock.method(globalThis, 'fetch', async () => ({ status: 201, json: async () => report }))
    await assert.rejects(submitCitizenReport(form), /could not confirm whether/)
    mocked.mock.restore()
  }
})

test('a lost response is never retried automatically or reported as confirmed success', async (t) => {
  let calls = 0
  t.mock.method(globalThis, 'fetch', async () => { calls++; throw new TypeError('Failed to fetch') })
  await assert.rejects(submitCitizenReport(form), /could not confirm whether/)
  assert.equal(calls, 1)
})

test('a stalled submission times out so the form can recover', async (t) => {
  let signal
  t.mock.method(globalThis, 'fetch', (url, options) => {
    signal = options.signal
    return new Promise((resolve, reject) => signal.addEventListener('abort', () => reject(new Error('aborted')), { once: true }))
  })
  await assert.rejects(submitCitizenReport(form, { timeoutMs: 10 }), /could not confirm whether/)
  assert.equal(signal.aborted, true)
})

test('cancellation on navigation aborts the pending submission', async (t) => {
  let requestSignal
  t.mock.method(globalThis, 'fetch', (url, options) => {
    requestSignal = options.signal
    return new Promise((resolve, reject) => requestSignal.addEventListener('abort', () => reject(new Error('aborted')), { once: true }))
  })
  const controller = new AbortController()
  const request = submitCitizenReport(form, { signal: controller.signal })
  controller.abort()
  await assert.rejects(request, /could not confirm whether/)
  assert.equal(requestSignal.aborted, true)
})
