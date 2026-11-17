import { useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { fetchHistoricalEvidence } from '../services/historicalFloods'

export default function useHistoricalFloods() {
  const { user, authorizedRequest } = useAuth()
  const allowed = user && ['officer', 'admin'].includes(user.role)
  const [enabled, setEnabled] = useState(false)
  const [visible, setVisible] = useState({ flood: true, coverage: true, cloud: true })
  const [state, setState] = useState({ data: null, error: '', loading: false })
  const [reload, setReload] = useState(0)
  const [fitRequest, setFitRequest] = useState(0)
  useEffect(() => {
    setState({ data: null, error: '', loading: Boolean(allowed && enabled) })
    if (!allowed || !enabled) return
    let active = true
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), 45000)
    fetchHistoricalEvidence(authorizedRequest, controller.signal).then(data => {
      if (active && !controller.signal.aborted) setState({ data, error: '', loading: false })
    }).catch(() => {
      if (active) setState({ data: null, error: 'Historical UNOSAT evidence is unavailable or invalid. No observation layer is shown.', loading: false })
    }).finally(() => clearTimeout(timer))
    return () => { active = false; clearTimeout(timer); controller.abort() }
  }, [allowed, enabled, authorizedRequest, reload])
  return { ...state, data: allowed && enabled ? state.data : null, allowed, enabled, setEnabled,
    visible, setVisible, fitRequest, fit: () => setFitRequest(n => n + 1), retry: () => setReload(n => n + 1) }
}
