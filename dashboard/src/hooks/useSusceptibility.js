import { useEffect, useState } from 'react'
import { fetchSusceptibility } from '../services/susceptibility'

// Static per-place data: fetched once per page.
export default function useSusceptibility() {
  const [state, setState] = useState({ data: null, loading: true, error: '' })
  useEffect(() => {
    const controller = new AbortController()
    fetchSusceptibility({ signal: controller.signal })
      .then(data => { if (!controller.signal.aborted) setState({ data, loading: false, error: '' }) })
      .catch(error => { if (!controller.signal.aborted) setState({ data: null, loading: false, error: error.message }) })
    return () => controller.abort()
  }, [])
  return state
}
