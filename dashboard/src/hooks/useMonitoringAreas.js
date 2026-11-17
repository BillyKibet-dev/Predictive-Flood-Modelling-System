import { useEffect, useState } from 'react'
import { fetchMonitoringAreas } from '../services/monitoringAreas'

export default function useMonitoringAreas() {
  const [state, setState] = useState({ data: null, loading: true, error: '' })
  const [revision, setRevision] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    setState({ data: null, loading: true, error: '' })
    fetchMonitoringAreas({ signal: controller.signal }).then(data => {
      if (!controller.signal.aborted) setState({ data, loading: false, error: '' })
    }).catch(error => {
      if (!controller.signal.aborted) setState({ data: null, loading: false, error: error.message })
    })
    return () => controller.abort()
  }, [revision])
  return { ...state, refresh: () => setRevision(n => n + 1) }
}
