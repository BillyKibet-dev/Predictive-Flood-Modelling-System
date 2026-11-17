import { useEffect, useState } from 'react'
import { activeReports, fetchCommunityReports } from '../services/communityReports'

const REFRESH_MS = 5 * 60000

// Checked community reports for the public map: refreshed every 5 minutes, and each report
// disappears exactly 24 hours after it was made, even between refreshes.
export default function useCommunityReports() {
  const [state, setState] = useState({ data: null, loading: true, error: '' }), [revision, setRevision] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    fetchCommunityReports({ signal: controller.signal })
      .then(data => { if (!controller.signal.aborted) setState({ data, loading: false, error: '' }) })
      .catch(error => { if (!controller.signal.aborted) setState(s => ({ ...s, loading: false, error: error.message })) })
    const timer = setTimeout(() => setRevision(n => n + 1), REFRESH_MS)
    return () => { controller.abort(); clearTimeout(timer) }
  }, [revision])
  useEffect(() => {
    const timer = setInterval(() => setState(s => s.data ? { ...s, data: { ...s.data, items: activeReports(s.data.items) } } : s), 60000)
    return () => clearInterval(timer)
  }, [])
  return { ...state, refresh: () => setRevision(n => n + 1) }
}
