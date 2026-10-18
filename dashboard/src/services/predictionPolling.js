import { fetchDashboard, POLL_INTERVAL_MS } from './predictions.js'

// Schedule after each request settles so slow requests and manual refreshes never overlap.
export function createPredictionPoller({
  onChange,
  load = fetchDashboard,
  intervalMs = POLL_INTERVAL_MS,
  requestTimeoutMs = 15_000,
  schedule = setTimeout,
  cancel = clearTimeout,
}) {
  let stopped = false
  let timer = null
  let activeRequest = null
  let state = { data: null, error: null, isRefreshing: false }

  function publish(update) {
    state = { ...state, ...update }
    onChange(state)
  }

  function refresh() {
    if (stopped) return Promise.resolve()
    if (activeRequest) return activeRequest.promise
    if (timer !== null) cancel(timer)
    timer = null

    const request = { controller: new AbortController(), promise: null, timeout: null }
    activeRequest = request
    publish({ isRefreshing: true })
    request.timeout = schedule(() => request.controller.abort(), requestTimeoutMs)
    request.promise = Promise.resolve()
      .then(() => load({ signal: request.controller.signal }))
      .then((data) => {
        if (!stopped) publish({ data, error: null })
      })
      .catch(() => {
        if (!stopped) publish({ error: 'Could not load predictions.' })
      })
      .finally(() => {
        cancel(request.timeout)
        activeRequest = null
        if (!stopped) {
          publish({ isRefreshing: false })
          timer = schedule(() => {
            timer = null
            void refresh()
          }, intervalMs)
        }
      })
    return request.promise
  }

  function stop() {
    stopped = true
    if (timer !== null) cancel(timer)
    if (activeRequest) {
      cancel(activeRequest.timeout)
      activeRequest.controller.abort()
    }
  }

  return { refresh, stop }
}
