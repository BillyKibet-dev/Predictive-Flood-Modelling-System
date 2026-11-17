import assert from 'node:assert/strict'
import test from 'node:test'
import { fetchReportingAreas, locateReportingArea, submitCitizenReport, validateCitizenReport } from '../src/services/reports.js'

const form = {
  area_id: 'nairobi-subcounty-kibra', observed_condition: 'Street flooding',
  perceived_severity: 'Serious', description: '  Water near the bridge  ',
}
const savedReport = { id: 42, area_id: 'nairobi-subcounty-kibra', timestamp: '2026-10-18T09:00:00Z' }

test('specific location is required in the new form and partial or invalid coordinates are rejected', () => {
  assert.ok(validateCitizenReport({...form,location_description:''},['nairobi-subcounty-kibra']).location_description)
  const precise={...form,location_description:'Outside Tmall',latitude:'-1.31',longitude:'36.81'}
  assert.deepEqual(validateCitizenReport(precise,['nairobi-subcounty-kibra']),{})
  assert.ok(validateCitizenReport({...precise,longitude:''},['nairobi-subcounty-kibra']).longitude)
  assert.ok(validateCitizenReport({...precise,latitude:'91'},['nairobi-subcounty-kibra']).latitude)
  assert.ok(validateCitizenReport({...precise,latitude:'not-a-number'},['nairobi-subcounty-kibra']).latitude)
})

test('requires a supported sub-county, condition, severity, and description length before submission', () => {
  assert.deepEqual(validateCitizenReport(form, ['nairobi-subcounty-kibra']), {})
  assert.deepEqual(validateCitizenReport({ ...form, description: '' }, ['nairobi-subcounty-kibra']), {})
  const errors = validateCitizenReport({
    area_id: 'Other', observed_condition: 'Unknown condition', perceived_severity: 'High', description: 'x'.repeat(201),
  }, ['nairobi-subcounty-kibra'])
  assert.deepEqual(Object.keys(errors), ['area_id', 'observed_condition', 'perceived_severity', 'description'])
  assert.ok(validateCitizenReport(form, []).area_id)
})

test('sends an anonymous report using the sub-county ID and returns the saved reference', async (t) => {
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

test('returns a sub-county error when the chosen sub-county is unknown', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => ({ status: 404 }))
  await assert.rejects(submitCitizenReport(form), (error) => {
    assert.match(error.message, /sub-county is not available/)
    assert.ok(error.fieldErrors.area_id)
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
  for (const report of [{}, { ...savedReport, id: 0 }, { ...savedReport, area_id: 'nairobi-subcounty-langata' }, { ...savedReport, timestamp: 'bad' }]) {
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

test('a pin outside the chosen sub-county is explained in words next to the sub-county field', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => ({
    status: 422, json: async () => ({ detail: 'The pin is in Langata, not Kibra. Choose the sub-county that matches the pin.' }),
  }))
  await assert.rejects(submitCitizenReport(form), (error) => {
    assert.match(error.message, /pin is in Langata/)
    assert.match(error.fieldErrors.area_id, /pin is in Langata/)
    return true
  })
})

test('sub-counties load from the public list and a pin is located with a POST body, never the URL', async (t) => {
  t.mock.method(globalThis, 'fetch', async (url, options = {}) => {
    if (url.endsWith('/reporting-areas')) return { ok: true, json: async () => [{ id: 'nairobi-subcounty-kibra', name: 'Kibra' }] }
    assert.equal(url, 'http://localhost:8000/reporting-areas/locate')
    assert.equal(options.method, 'POST')
    assert.deepEqual(JSON.parse(options.body), { latitude: -1.31, longitude: 36.79 })
    return { ok: true, json: async () => ({ id: 'nairobi-subcounty-kibra', name: 'Kibra' }) }
  })
  assert.equal((await fetchReportingAreas())[0].name, 'Kibra')
  assert.equal((await locateReportingArea('-1.31', '36.79')).id, 'nairobi-subcounty-kibra')
})

test('an empty or malformed sub-county list is rejected rather than shown', async (t) => {
  for (const body of [[], [{ id: 1, name: 'x' }], {}]) {
    const mocked = t.mock.method(globalThis, 'fetch', async () => ({ ok: true, json: async () => body }))
    await assert.rejects(fetchReportingAreas())
    mocked.mock.restore()
  }
})
