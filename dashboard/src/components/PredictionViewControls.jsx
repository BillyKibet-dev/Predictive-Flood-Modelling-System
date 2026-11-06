import { useEffect, useId, useState } from 'react'
import { PREDICTION_VIEWS, validCalendarDate } from '../services/proxyPredictions'

export default function PredictionViewControls({ selection }) {
  const id = useId()
  const [draftDate, setDraftDate] = useState(selection.inputDate)
  useEffect(() => setDraftDate(selection.inputDate), [selection.inputDate])
  const valid = validCalendarDate(draftDate)
  return (
    <div className="flex flex-wrap items-end gap-3 text-xs">
      <label className="space-y-1 text-ink" htmlFor={`${id}-view`}>
        <span className="block font-medium">Prediction view</span>
        <select id={`${id}-view`} value={selection.view} onChange={(event) => selection.setView(event.target.value)}
          className="max-w-full h-10 rounded-btn border border-border bg-surface px-2 text-ink">
          {PREDICTION_VIEWS.map((view) => <option key={view.value} value={view.value}>{view.label}</option>)}
        </select>
      </label>
      {selection.view === 'v1_replay' && <form className="flex flex-wrap items-end gap-2" onSubmit={(event) => {
        event.preventDefault()
        if (valid) selection.setInputDate(draftDate)
      }}>
        <label className="space-y-1 text-ink" htmlFor={`${id}-date`}>
          <span className="block font-medium">Historical input day (Nairobi)</span>
          <input id={`${id}-date`} type="date" value={draftDate} onChange={(event) => setDraftDate(event.target.value)}
            required aria-invalid={!valid} className="h-10 rounded-btn border border-border bg-surface px-2 text-ink" />
        </label>
        <button type="submit" disabled={!valid || draftDate === selection.inputDate}
          className="h-10 rounded-btn border border-border px-3 text-ink disabled:opacity-50">Load replay date</button>
      </form>}
    </div>
  )
}
