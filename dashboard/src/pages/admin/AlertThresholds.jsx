import { useState } from 'react'

const SLIDER_CONFIG = [
  { key: 'moderate', label: 'MODERATE', color: 'var(--risk-mod)', min: 10, max: 50, defaultValue: 25 },
  { key: 'high', label: 'HIGH', color: 'var(--risk-high)', min: 30, max: 70, defaultValue: 50 },
  { key: 'extreme', label: 'EXTREME', color: 'var(--risk-extreme)', min: 60, max: 95, defaultValue: 75 },
]

// Admin section — define when the XGBoost model triggers an alert for each risk level
export default function AlertThresholds({ showToast }) {
  const [values, setValues] = useState(() => Object.fromEntries(SLIDER_CONFIG.map((s) => [s.key, s.defaultValue])))

  function handleSave() {
    showToast('Thresholds updated successfully', 'success')
  }

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight text-ink">Alert Thresholds</h2>
        <p className="text-muted mt-1">Define when the XGBoost model triggers alerts</p>
      </div>

      <div className="space-y-4">
        {SLIDER_CONFIG.map((s) => (
          <div
            key={s.key}
            className="bg-surface rounded-card p-6 border-l-4 border-t border-r border-b border-border shadow-card-rest"
            style={{ borderLeftColor: s.color }}
          >
            <p className="text-xs font-semibold uppercase tracking-wide text-muted">{s.label} Threshold</p>
            <p className="text-2xl font-bold mt-1 mb-4" style={{ color: s.color }}>
              ≥ {values[s.key]}% flood probability
            </p>
            <input
              type="range"
              min={s.min}
              max={s.max}
              value={values[s.key]}
              onChange={(e) => setValues({ ...values, [s.key]: Number(e.target.value) })}
              className="w-full"
              style={{ accentColor: s.color }}
            />
            <div className="flex justify-between text-xs text-muted mt-1">
              <span>{s.min}%</span>
              <span>{s.max}%</span>
            </div>
          </div>
        ))}
      </div>

      <button
        onClick={handleSave}
        className="w-full h-12 rounded-card bg-brand text-white font-semibold hover:bg-brand-light transition-colors"
      >
        Save Thresholds
      </button>
    </div>
  )
}
