import assert from 'node:assert/strict'
import test from 'node:test'
import { createPredictionPoller } from '../src/services/predictionPolling.js'

function deferred() {
  let resolve, reject
  const promise = new Promise((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

function timers() {
  const jobs = new Map()
  let nextId = 0
  return {
    schedule(callback, delay) {
      const id = ++nextId
      jobs.set(id, { callback, delay })
      return id
    },
    cancel(id) { jobs.delete(id) },
    delays() { return [...jobs.values()].map((job) => job.delay) },
    fire(delay) {
      const found = [...jobs].find(([, job]) => job.delay === delay)
      assert.ok(found, `Expected a timer for ${delay} ms`)
      jobs.delete(found[0])
      found[1].callback()
    },
  }
}

function setup(load) {
  const clock = timers()
  const changes = []
  const poller = createPredictionPoller({
    load, onChange: (state) => changes.push(state),
    intervalMs: 60_000, requestTimeoutMs: 15_000,
    schedule: clock.schedule, cancel: clock.cancel,
  })
  return { poller, clock, changes, latest: () => changes.at(-1) }
}

test('loads immediately and schedules the next poll only after a slow request settles', async () => {
  const pending = deferred()
  let calls = 0
  const { poller, clock, latest } = setup(() => { calls++; return pending.promise })
  const request = poller.refresh()
  await Promise.resolve()
  assert.equal(calls, 1)
  assert.equal(latest().isRefreshing, true)
  assert.deepEqual(clock.delays(), [15_000])
  pending.resolve({ zones: [], activeAlerts: 0 })
  await request
  assert.equal(latest().isRefreshing, false)
  assert.deepEqual(clock.delays(), [60_000])
  clock.fire(60_000)
  await poller.refresh()
  assert.equal(calls, 2)
  poller.stop()
})

test('manual and automatic refreshes share the in-flight request', async () => {
  const pending = deferred()
  let calls = 0
  const { poller } = setup(() => { calls++; return pending.promise })
  const first = poller.refresh()
  const second = poller.refresh()
  assert.equal(first, second)
  pending.resolve({ zones: [] })
  await first
  assert.equal(calls, 1)
  poller.stop()
})

test('manual refresh replaces the pending timer rather than adding a second polling loop', async () => {
  let calls = 0
  const { poller, clock } = setup(async () => { calls++; return { zones: [] } })
  await poller.refresh()
  await poller.refresh()
  assert.equal(calls, 2)
  assert.deepEqual(clock.delays(), [60_000])
  poller.stop()
})

test('a failed refresh preserves data, retries automatically, and clears the error on recovery', async () => {
  let calls = 0
  const saved = { zones: [{ id: 'mathare', risk: 'High' }] }
  const updated = { zones: [{ id: 'mathare', risk: 'Low' }] }
  const { poller, clock, latest } = setup(async () => {
    calls++
    if (calls === 2) throw new Error('offline')
    return calls === 1 ? saved : updated
  })
  await poller.refresh()
  await poller.refresh()
  assert.equal(latest().data, saved)
  assert.ok(latest().error)
  assert.equal(latest().isRefreshing, false)
  clock.fire(60_000)
  await poller.refresh()
  assert.equal(latest().data, updated)
  assert.equal(latest().error, null)
  poller.stop()
})

test('an initial failure leaves data unavailable and remains retryable', async () => {
  const { poller, clock, latest } = setup(async () => { throw new Error('unavailable') })
  await poller.refresh()
  assert.equal(latest().data, null)
  assert.ok(latest().error)
  assert.deepEqual(clock.delays(), [60_000])
  poller.stop()
})

test('request timeouts abort stalled fetches and allow the next scheduled retry', async () => {
  let signal
  const { poller, clock, latest } = setup((options) => {
    signal = options.signal
    return new Promise((resolve, reject) => {
      signal.addEventListener('abort', () => reject(new Error('aborted')), { once: true })
    })
  })
  const request = poller.refresh()
  await Promise.resolve()
  clock.fire(15_000)
  await request
  assert.equal(signal.aborted, true)
  assert.ok(latest().error)
  assert.deepEqual(clock.delays(), [60_000])
  poller.stop()
})

test('unmount cleanup aborts pending requests and ignores results arriving after stop', async () => {
  const pending = deferred()
  let signal
  const { poller, clock, changes } = setup((options) => { signal = options.signal; return pending.promise })
  const request = poller.refresh()
  await Promise.resolve()
  poller.stop()
  const count = changes.length
  assert.equal(signal.aborted, true)
  pending.resolve({ zones: [] })
  await request
  assert.equal(changes.length, count)
  assert.deepEqual(clock.delays(), [])
  await poller.refresh()
  assert.equal(changes.length, count)
})

test('unmount cleanup removes an already scheduled poll', async () => {
  const { poller, clock } = setup(async () => ({ zones: [] }))
  await poller.refresh()
  poller.stop()
  assert.deepEqual(clock.delays(), [])
})
