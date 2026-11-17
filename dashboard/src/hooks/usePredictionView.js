import { useMemo, useState } from 'react'
import { DEFAULT_REPLAY_DATE, predictionViewConfiguration } from '../services/proxyPredictions'
import useProxyPredictions from './useProxyPredictions'

export default function usePredictionView() {
  const [view, setView] = useState('v1_replay')
  const [inputDate, setInputDate] = useState(DEFAULT_REPLAY_DATE)
  const configuration = useMemo(() => predictionViewConfiguration(view, inputDate), [view, inputDate])
  const proxy = useProxyPredictions(configuration)
  return {
    ...proxy,
    selection: { view, inputDate, setView, setInputDate },
  }
}
