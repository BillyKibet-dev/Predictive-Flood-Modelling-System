import { useState } from 'react'
import { riskColor } from '../../constants/colors'

const SLIDER_CONFIG = [
  { key: 'moderate', label: 'MODERATE', risk: 'Moderate', min: 10, max: 50, defaultValue: 25 },
  { key: 'high', label: 'HIGH', risk: 'High', min: 30, max: 70, defaultValue: 50 },
  { key: 'extreme', label: 'EXTREME', risk: 'Extreme', min: 60, max: 95, defaultValue: 75 },
]

// Admin section — configure the flood probability thresholds used to trigger each risk level
export default function AlertThresholds({ showToast }) {
  const [values, setValues] = useState(() =>
    Object.fromEntries(SLIDER_CONFIG.map((s) => [s.key, s.defaultValue]))
  )

  function handleSave() {
    showToast('Thresholds updated successfully', 'success')
  }

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h2 className="text-xl font-bold text-gray-800">Configure Alert Thresholds</h2>
        <p className="text-sm text-gray-500">Set flood probability thresholds per risk level</p>
      </div>

      <div className="bg-white rounded-lg shadow p-6 space-y-6">
        {SLIDER_CONFIG.map((s) => (
          <div key={s.key}>
            <div className="flex items-center justify-between mb-2">
              <span className="font-semibold text-sm" style={{ color: riskColor(s.risk) }}>
                {s.label} threshold
              </span>
              <span className="text-sm font-medium text-gray-700">≥ {values[s.key]}% probability</span>
            </div>
            <input
              type="range"
              min={s.min}
              max={s.max}
              value={values[s.key]}
              onChange={(e) => setValues({ ...values, [s.key]: Number(e.target.value) })}
              className="w-full"
              style={{ accentColor: riskColor(s.risk) }}
            />
            <div className="flex justify-between text-xs text-gray-400">
              <span>{s.min}%</span>
              <span>{s.max}%</span>
            </div>
          </div>
        ))}

        <button
          onClick={handleSave}
          className="bg-teal-600 hover:bg-teal-700 text-white font-semibold px-5 py-2.5 rounded-lg"
        >
          Save Thresholds ✓
        </button>
      </div>
    </div>
  )
}
