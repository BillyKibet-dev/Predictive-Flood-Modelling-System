import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { riskColor } from '../../constants/colors'
import useProxyModel from '../../hooks/useProxyModel'
import { formatTargetDate } from '../../services/proxyPredictions'

const METRICS = [
  ['accuracy', 'Proxy-label accuracy'], ['macro_f1', 'Macro F1'],
  ['weighted_f1', 'Weighted F1'], ['extreme_recall', 'Extreme proxy recall'],
]

export default function ModelPerformance() {
  const { data, error, loading, refresh } = useProxyModel()
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight text-ink">v1 Proxy Model Evaluation</h2>
          <p className="text-muted mt-1">Stored historical test results against rule-generated environmental labels.</p>
        </div>
        <button type="button" onClick={refresh} disabled={loading} className="border border-border rounded-btn px-3 py-2 text-sm text-ink disabled:opacity-50">
          {loading ? 'Loading metadata...' : 'Refresh metadata'}
        </button>
      </div>
      {!data && <p role="status" className="text-sm text-muted">{error ?? 'Loading verified evaluation metadata...'}</p>}
      {error && data && <p role="alert" className="text-sm text-risk-mod">{error} Showing the last retrieved metadata.</p>}
      {data && <>
        <div className="rounded-card border border-border p-4 text-sm text-muted space-y-1">
          <p className="font-semibold text-ink">{data.modelVersion} · Next-calendar-day environmental proxy risk</p>
          <p>Test target dates: {formatTargetDate(data.evaluation.testTargetDates[0])} – {formatTargetDate(data.evaluation.testTargetDates[1])} · {data.evaluation.rows.toLocaleString('en-GB')} zone-days · {data.featureCount} features</p>
          <p>Artifact loaded: {data.loaded ? 'Yes' : 'No'} · Operational input status: {data.operationalStatus.replaceAll('_', ' ')}</p>
          <p>These scores do not measure prediction of observed floods, flood depth or inundation. Class scores are not calibrated flood occurrence probabilities.</p>
          <p>Emergency delivery is disabled. Native model loading alone does not establish live feature availability or operational readiness.</p>
        </div>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {METRICS.map(([key, label]) => <div key={key} className="bg-surface border border-border rounded-card p-5 shadow-card-rest">
            <p className="text-3xl font-bold text-ink">{data.evaluation.metrics[key].toFixed(4)}</p>
            <p className="text-xs font-semibold uppercase tracking-wide text-muted mt-1">{label}</p>
          </div>)}
        </div>
        <div className="bg-surface border border-border rounded-card p-6 shadow-card-rest">
          <h3 className="font-semibold text-ink mb-4">Recall by proxy class — held-out test zone-days</h3>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={data.evaluation.perClass}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
              <XAxis dataKey="name" tick={{ fill: 'var(--text-muted)', fontSize: 12 }} axisLine={false} tickLine={false} />
              <YAxis domain={[0, 1]} tick={{ fill: 'var(--text-muted)', fontSize: 12 }} axisLine={false} tickLine={false} />
              <Tooltip formatter={(value) => value.toFixed(4)} />
              <Bar dataKey="recall" radius={[4, 4, 0, 0]}>
                {data.evaluation.perClass.map((row) => <Cell key={row.name} fill={riskColor(row.name)} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <p className="text-sm text-muted mt-3">High proxy recall: {data.evaluation.metrics.high_recall.toFixed(4)}. Extreme proxy recall: {data.evaluation.metrics.extreme_recall.toFixed(4)} — approximately {(data.evaluation.metrics.extreme_recall * 100).toFixed(2)}% of Extreme-labelled test zone-days. This is a severe-class weakness, not evidence of emergency-warning reliability.</p>
          <div className="overflow-x-auto mt-4">
            <table className="w-full text-sm">
              <caption className="sr-only">Stored per-class evaluation on proxy labels</caption>
              <thead><tr className="text-left text-muted">{['Proxy class', 'Precision', 'Recall', 'F1', 'Support'].map((name) => <th key={name} scope="col" className="py-2 pr-3">{name}</th>)}</tr></thead>
              <tbody>{data.evaluation.perClass.map((row) => <tr key={row.name} className="border-t border-border text-ink">
                <th scope="row" className="py-2 pr-3 text-left">{row.name}</th>
                <td className="pr-3">{row.precision.toFixed(4)}</td><td className="pr-3">{row.recall.toFixed(4)}</td>
                <td className="pr-3">{row.f1.toFixed(4)}</td><td>{row.support}</td>
              </tr>)}</tbody>
            </table>
          </div>
        </div>
        <div className="text-sm text-muted space-y-2">
          <h3 className="font-semibold text-ink">Recorded limitations</h3>
          <ul className="list-disc pl-5 space-y-1">{data.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
          {data.artifactHash && <p className="text-xs break-all">Model SHA-256: {data.artifactHash}</p>}
        </div>
      </>}
    </div>
  )
}
