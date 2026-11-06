import { useCallback, useEffect, useState } from 'react'
import { fetchProxyModel } from '../services/proxyPredictions'

export default function useProxyModel() {
  const [revision, setRevision] = useState(0)
  const [state, setState] = useState({ data: null, error: null, loading: true })
  useEffect(() => {
    let active = true
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), 15_000)
    setState((previous) => ({ ...previous, loading: true, error: null }))
    fetchProxyModel({ signal: controller.signal })
      .then((data) => { if (active) setState({ data, error: null, loading: false }) })
      .catch(() => { if (active) setState((previous) => ({ ...previous, error: 'v1 model metadata is unavailable.', loading: false })) })
      .finally(() => clearTimeout(timeout))
    return () => { active = false; controller.abort(); clearTimeout(timeout) }
  }, [revision])
  const refresh = useCallback(() => setRevision((value) => value + 1), [])
  return { ...state, refresh }
}
