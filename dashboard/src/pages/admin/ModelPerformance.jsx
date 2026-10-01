import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { riskColor } from '../../constants/colors'
import { MODEL_METRICS, PER_CLASS_RECALL } from '../../data/mockData'

// Admin section — XGBoost test-set performance metrics and per-class recall chart
export default function ModelPerformance() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-gray-800">XGBoost Model Performance</h2>
        <p className="text-sm text-gray-500">Test Set 2024–2026</p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {MODEL_METRICS.map((m) => (
          <div key={m.label} className="bg-white rounded-lg shadow p-4 text-center">
            <p className="text-xs font-semibold text-gray-500">{m.label}</p>
            <p className="text-xl font-bold text-gray-800 mt-1">
              {m.value.toFixed(4)} {m.ok ? '✅' : '⚠'}
            </p>
          </div>
        ))}
      </div>

      <div className="bg-white rounded-lg shadow p-4">
        <h3 className="font-semibold text-gray-800 mb-3">Per-Class Recall</h3>
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={PER_CLASS_RECALL}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="name" />
            <YAxis domain={[0, 1]} />
            <Tooltip formatter={(v) => v.toFixed(4)} />
            <Bar dataKey="recall" radius={[4, 4, 0, 0]}>
              {PER_CLASS_RECALL.map((entry) => (
                <Cell key={entry.name} fill={riskColor(entry.name)} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
        <p className="text-xs text-gray-500 mt-3">
          ⚠ Moderate and High recall below target due to data scarcity. Will improve with TAHMO integration.
        </p>
      </div>
    </div>
  )
}
