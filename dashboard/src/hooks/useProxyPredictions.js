import { useCallback, useEffect, useRef, useState } from 'react'
import { createPredictionPoller } from '../services/predictionPolling'
import { fetchProxyDashboard } from '../services/proxyPredictions'

const EMPTY = { data: null, error: null, isRefreshing: true }

export default function useProxyPredictions(configuration) {
  const key = configuration?.key ?? null
  const mode = configuration?.mode
  const inputDate = configuration?.inputDate
  const [snapshot, setSnapshot] = useState({ key: null, ...EMPTY })
  const pollerRef = useRef(null)

  useEffect(() => {
    if (!key || mode === 'legacy') return undefined
    const poller = createPredictionPoller({
      load: ({ signal }) => fetchProxyDashboard({ mode, inputDate, signal }),
      onChange: (state) => setSnapshot({ key, ...state }),
    })
    pollerRef.current = poller
    setSnapshot({ key, ...EMPTY })
    void poller.refresh()
    const visible = () => { if (document.visibilityState === 'visible') void poller.refresh() }
    const online = () => { void poller.refresh() }
    document.addEventListener('visibilitychange', visible)
    window.addEventListener('online', online)
    return () => {
      pollerRef.current = null
      poller.stop()
      document.removeEventListener('visibilitychange', visible)
      window.removeEventListener('online', online)
    }
  }, [key, mode, inputDate])

  const refresh = useCallback(() => pollerRef.current?.refresh(), [])
  // A date/mode change must not momentarily display the previous request's forecast.
  return { ...(snapshot.key === key ? snapshot : EMPTY), refresh }
}
