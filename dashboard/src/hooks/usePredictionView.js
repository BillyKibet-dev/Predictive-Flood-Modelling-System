import { useMemo, useState } from 'react'
import { DEFAULT_REPLAY_DATE, predictionViewConfiguration } from '../services/proxyPredictions'
import usePredictions from './usePredictions'
import useProxyPredictions from './useProxyPredictions'

export default function usePredictionView() {
  const [view, setView] = useState('legacy')
  const [inputDate, setInputDate] = useState(DEFAULT_REPLAY_DATE)
  const configuration = useMemo(() => predictionViewConfiguration(view, inputDate), [view, inputDate])
  const legacy = usePredictions(view === 'legacy')
  const proxy = useProxyPredictions(view === 'legacy' ? null : configuration)
  return {
    ...(view === 'legacy' ? legacy : proxy),
    selection: { view, inputDate, setView, setInputDate },
  }
}
