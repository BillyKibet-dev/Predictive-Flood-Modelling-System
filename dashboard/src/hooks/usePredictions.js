import { useCallback, useEffect, useRef, useState } from 'react'
import { createPredictionPoller } from '../services/predictionPolling'

export default function usePredictions() {
  const [state, setState] = useState({ data: null, error: null, isRefreshing: true })
  const pollerRef = useRef(null)

  useEffect(() => {
    const poller = createPredictionPoller({ onChange: setState })
    pollerRef.current = poller
    void poller.refresh()

    function refreshWhenVisible() {
      if (document.visibilityState === 'visible') void poller.refresh()
    }
    function refreshWhenOnline() {
      void poller.refresh()
    }
    document.addEventListener('visibilitychange', refreshWhenVisible)
    window.addEventListener('online', refreshWhenOnline)

    return () => {
      pollerRef.current = null
      poller.stop()
      document.removeEventListener('visibilitychange', refreshWhenVisible)
      window.removeEventListener('online', refreshWhenOnline)
    }
  }, [])

  const refresh = useCallback(() => pollerRef.current?.refresh(), [])
  return { ...state, refresh }
}
