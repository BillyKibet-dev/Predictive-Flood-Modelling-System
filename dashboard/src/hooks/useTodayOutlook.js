import { useEffect, useState } from 'react'
import { fetchTodayOutlook } from '../services/todayOutlook'

// Rechecked every 10 minutes so the 3-hour blocks move with the clock.
export default function useTodayOutlook() {
  const [state, setState] = useState({ data: null, loading: true, error: '' }), [revision, setRevision] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    fetchTodayOutlook({ signal: controller.signal })
      .then(data => { if (!controller.signal.aborted) setState({ data, loading: false, error: '' }) })
      .catch(error => { if (!controller.signal.aborted) setState(s => ({ ...s, loading: false, error: error.message })) })
    const timer = setTimeout(() => setRevision(n => n + 1), 600000)
    return () => { controller.abort(); clearTimeout(timer) }
  }, [revision])
  return { ...state, refresh: () => setRevision(n => n + 1) }
}
