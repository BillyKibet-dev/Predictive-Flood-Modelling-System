import { useEffect, useState } from 'react'
import { activeAdvisories, fetchAdvisories } from '../services/advisories'

// Active officer advisories: refreshed every 2 minutes, expired ones dropped each minute.
export default function useAdvisories() {
  const [state, setState] = useState({ data: null, error: '' }), [revision, setRevision] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    fetchAdvisories({ signal: controller.signal })
      .then(data => { if (!controller.signal.aborted) setState({ data, error: '' }) })
      .catch(error => { if (!controller.signal.aborted) setState(s => ({ ...s, error: error.message })) })
    const timer = setTimeout(() => setRevision(n => n + 1), 120000)
    return () => { controller.abort(); clearTimeout(timer) }
  }, [revision])
  useEffect(() => {
    const timer = setInterval(() => setState(s => s.data ? { ...s, data: { ...s.data, items: activeAdvisories(s.data.items) } } : s), 60000)
    return () => clearInterval(timer)
  }, [])
  return { ...state, refresh: () => setRevision(n => n + 1) }
}
