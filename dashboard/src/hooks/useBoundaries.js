import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchBoundaries } from '../services/boundaries'

// Boundaries change independently of hourly predictions; fetch on map entry or explicit reload.
export default function useBoundaries() {
  const [state, setState] = useState({ data: null, error: null, isLoading: true, revision: 0 })
  const mounted = useRef(false)
  const requestRef = useRef(null)

  const reload = useCallback(async () => {
    if (requestRef.current) return
    const controller = new AbortController()
    requestRef.current = controller
    setState((previous) => ({ ...previous, isLoading: true }))
    const timeout = setTimeout(() => controller.abort(), 15_000)
    try {
      const data = await fetchBoundaries({ signal: controller.signal })
      if (mounted.current && requestRef.current === controller) {
        setState((previous) => ({ data, error: null, isLoading: false, revision: previous.revision + 1 }))
      }
    } catch {
      if (mounted.current && requestRef.current === controller) {
        setState((previous) => ({ ...previous, error: 'Boundaries could not be loaded.', isLoading: false }))
      }
    } finally {
      clearTimeout(timeout)
      if (requestRef.current === controller) requestRef.current = null
    }
  }, [])

  useEffect(() => {
    mounted.current = true
    void reload()
    return () => {
      mounted.current = false
      requestRef.current?.abort()
      requestRef.current = null
    }
  }, [reload])

  return { ...state, reload }
}
