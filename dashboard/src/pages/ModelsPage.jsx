import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import ChartTooltip, { ChartLegend, axisProps } from '../components/ChartTooltip'
import StaffLayout, { PageHeader, buttonClass } from '../components/StaffLayout'
import useStaffList from '../hooks/useStaffList'
import { parseModelCard, percent } from '../services/staffData'

const RULE = { label: 'Stage 1 rule', color: 'var(--chart-1)' }, MODEL = { label: 'Stage 2 model', color: 'var(--chart-2)' }
const STATUS = { APPLIED: 'model applied', INPUTS_INCOMPLETE: 'rule used (inputs incomplete)', MODEL_UNAVAILABLE: 'rule used (model unavailable)', MODEL_INPUT_REJECTED: 'rule used (inputs rejected)', NO_FORECAST: 'no forecast' }
const date = value => new Intl.DateTimeFormat('en-KE', { day: 'numeric', month: 'short', year: 'numeric' }).format(new Date(value))

function Compare({ label, help, model, rule, better }) {
  const improved = better === 'higher' ? model > rule : model < rule
  return <div className="panel p-5">
    <p className="eyebrow">{label}</p>
    <p className="text-3xl font-semibold tracking-tight mt-2 tabular">{model}</p>
    <p className="text-sm text-muted mt-1 tabular">Rule: {rule} <span className={improved ? 'text-risk-low' : 'text-risk-high'}>· {improved ? 'better' : 'worse'}</span></p>
    <p className="text-xs text-muted mt-3">{help}</p>
  </div>
}

function MetricsTable({ v }) {
  const rows = [
    ['High-or-above days caught (POD)', 'high_or_above', 'pod', percent], ['High-or-above false alarms (FAR)', 'high_or_above', 'far', percent],
    ['High-or-above skill (CSI)', 'high_or_above', 'csi', x => x.toFixed(2)], ['Extreme days caught (POD)', 'extreme', 'pod', percent],
    ['Extreme skill (CSI)', 'extreme', 'csi', x => x.toFixed(2)],
  ]
  return <div className="overflow-x-auto"><table className="w-full text-sm tabular">
    <thead><tr className="text-left text-muted">{['Measure', 'Rule', 'Model', 'Rule (forward)', 'Model (forward)'].map(h => <th key={h} scope="col" className="py-2 pr-4 font-medium">{h}</th>)}</tr></thead>
    <tbody>{rows.map(([label, group, key, f]) => <tr key={label} className="border-t border-border">
      <th scope="row" className="py-2 pr-4 text-left font-normal">{label}</th>
      {[v.rule, v.model, v.forward_rule, v.forward_model].map((m, i) => <td key={i} className="py-2 pr-4">{f(m[group][key])}</td>)}
    </tr>)}
      <tr className="border-t border-border"><th scope="row" className="py-2 pr-4 text-left font-normal">Macro F1 (all four categories)</th>
        {[v.rule, v.model, v.forward_rule, v.forward_model].map((m, i) => <td key={i} className="py-2 pr-4">{m.macro_f1.toFixed(2)}</td>)}</tr>
    </tbody></table></div>
}

export default function ModelsPage() {
  const state = useStaffList('/staff/model-card')
  const [card, invalid] = useMemo(() => {
    if (!state.data) return [null, '']
    try { return [parseModelCard(state.data), ''] } catch (error) { return [null, error.message] }
  }, [state.data])
  const live = card?.live_status, applied = live?.by_status?.APPLIED ?? 0
  return <StaffLayout>
    <PageHeader title="Models" description="The model behind tomorrow's rainfall categories, how it was tested, and what it is not.">
      <button className={buttonClass} onClick={state.refresh} disabled={state.loading}>{state.loading ? 'Checking…' : 'Refresh'}</button>
    </PageHeader>
    {(state.error || invalid) && <p role="alert" className="text-sm mb-4">{state.error || invalid}</p>}
    {!card && state.loading && <p role="status" className="text-sm text-muted">Loading model records…</p>}
    {card && <div className="space-y-8">
      <section className="panel p-5 sm:p-6 flex flex-wrap gap-x-10 gap-y-4 items-start" aria-label="Live model">
        <div className="min-w-0 flex-1 basis-72">
          <p className="flex items-center gap-2 text-sm font-medium"><span className={`w-2 h-2 rounded-full ${applied ? 'bg-risk-low' : 'bg-risk-mod'}`} aria-hidden="true" />{applied ? 'Live' : 'Live, rule fallback in use'}</p>
          <h2 className="text-xl font-semibold tracking-tight mt-2">{card.live.name}</h2>
          <p className="text-sm text-muted mt-1">{card.live.method}. {card.live.fallback}.</p>
        </div>
        <dl className="grid grid-cols-2 sm:grid-cols-4 gap-x-8 gap-y-3 text-sm">
          <div><dt className="eyebrow">Version</dt><dd className="font-mono mt-1">{card.live.version}</dd></div>
          <div><dt className="eyebrow">Trained</dt><dd className="mt-1">{date(card.live.trained_at)}</dd></div>
          <div><dt className="eyebrow">Training days</dt><dd className="mt-1 tabular">{card.live.training_rows.toLocaleString('en-GB')}</dd></div>
          <div><dt className="eyebrow">In use now</dt><dd className="mt-1 tabular">{live ? `${applied} of ${live.located} places` : 'Unknown'}</dd></div>
        </dl>
        {live && Object.keys(live.by_status).some(k => k !== 'APPLIED') && <p className="basis-full text-xs text-muted">
          {Object.entries(live.by_status).map(([k, n]) => `${n} ${STATUS[k] ?? k}`).join(' · ')}</p>}
      </section>

      <section aria-labelledby="skill-heading" className="space-y-4">
        <div><h2 id="skill-heading" className="text-lg font-semibold">How well it does</h2>
          <p className="text-sm text-muted mt-1">On High-or-above rainfall days, tested one season at a time on seasons the model never saw.</p></div>
        <div className="grid sm:grid-cols-3 gap-4">
          <Compare label="Heavy-rain days caught" model={percent(card.validation.model.high_or_above.pod)} rule={percent(card.validation.rule.high_or_above.pod)} better="higher" help="Of the days that turned out High or Extreme, how many it flagged the day before." />
          <Compare label="False alarms" model={percent(card.validation.model.high_or_above.far)} rule={percent(card.validation.rule.high_or_above.far)} better="lower" help="Of the days it flagged High or Extreme, how many were not." />
          <Compare label="Overall skill (CSI)" model={card.validation.model.high_or_above.csi.toFixed(2)} rule={card.validation.rule.high_or_above.csi.toFixed(2)} better="higher" help="Hits ÷ (hits + misses + false alarms). 1 is perfect." />
        </div>
      </section>

      <section className="panel p-5 sm:p-6 space-y-4" aria-labelledby="season-heading">
        <div className="flex flex-wrap justify-between gap-3 items-end">
          <div><h2 id="season-heading" className="font-semibold">Skill by season</h2><p className="text-sm text-muted mt-1">High-or-above CSI. Higher is better.</p></div>
          <ChartLegend items={[RULE, MODEL]} />
        </div>
        <div className="h-64" role="img" aria-label={`Skill by season: the model beats the rule in ${card.validation.seasons.filter(s => s.model_csi > s.rule_csi).length} of ${card.validation.seasons.length} seasons`}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={card.validation.seasons} barGap={2} margin={{ left: -16, right: 4 }}>
              <CartesianGrid stroke="var(--border)" vertical={false} />
              <XAxis dataKey="season" {...axisProps} interval={0} tick={{ ...axisProps.tick, fontSize: 11 }} />
              <YAxis domain={[0, 1]} ticks={[0, 0.25, 0.5, 0.75, 1]} {...axisProps} />
              <Tooltip cursor={{ fill: 'var(--surface-2)' }} content={<ChartTooltip format={v => v.toFixed(2)} />} />
              <Bar isAnimationActive={false} dataKey="rule_csi" name={RULE.label} fill={RULE.color} radius={[4, 4, 0, 0]} maxBarSize={18} />
              <Bar isAnimationActive={false} dataKey="model_csi" name={MODEL.label} fill={MODEL.color} radius={[4, 4, 0, 0]} maxBarSize={18} />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <details className="text-sm"><summary className="cursor-pointer text-accent font-medium">All validation numbers</summary>
          <div className="mt-3 space-y-2"><MetricsTable v={card.validation} />
            <p className="text-xs text-muted">"Forward" trains only on earlier seasons and tests on later ones: a stricter check. {card.validation.protocol}.</p></div>
        </details>
      </section>

      <div className="grid lg:grid-cols-2 gap-4">
        <section className="panel p-5 space-y-2" aria-labelledby="adopt-heading">
          <h2 id="adopt-heading" className="font-semibold">Why it went live</h2>
          <p className="text-sm text-muted">{card.adoption.rule}</p>
          <p className="text-sm">Result: skill gain <span className="tabular font-medium">+{card.adoption.csi_gain.toFixed(2)}</span> (95% range {card.adoption.csi_gain_95.map(v => v.toFixed(2)).join('–')}), Extreme catch rate {card.adoption.extreme_recall_change >= 0 ? '+' : ''}{card.adoption.extreme_recall_change.toFixed(2)}. {card.adoption.adopted ? 'Adopted.' : 'Not adopted.'}</p>
        </section>
        <section className="panel p-5 space-y-2" aria-labelledby="confidence-heading">
          <h2 id="confidence-heading" className="font-semibold">Confidence and probabilities</h2>
          <p className="text-sm text-muted">{card.calibration.note}</p>
          <p className="text-sm">The public map shows the category only. A calibrated "chance of High or above" needs a separate calibration step first.</p>
        </section>
      </div>

      <section aria-labelledby="other-heading" className="space-y-3">
        <h2 id="other-heading" className="text-lg font-semibold">Other models</h2>
        <ul className="panel divide-y divide-border">{card.retained.map(m => <li key={m.name} className="p-4 flex flex-wrap gap-x-4 gap-y-1 items-baseline">
          <span className="font-medium">{m.name}</span><span className="text-xs font-semibold px-2 py-0.5 rounded-badge bg-surface-2 text-muted">{m.status}</span>
          <span className="text-sm text-muted basis-full">{m.detail}</span></li>)}</ul>
        <Link to="/research" className="text-sm text-accent font-medium">Open research models →</Link>
      </section>

      <details className="panel p-5 text-sm"><summary className="cursor-pointer font-medium">Limits and technical details</summary>
        <ul className="list-disc pl-5 mt-3 space-y-1 text-muted">{card.limitations.map(l => <li key={l}>{l}</li>)}</ul>
        <dl className="mt-4 space-y-1 text-xs text-muted"><div><dt className="inline font-medium">Inputs: </dt><dd className="inline">{card.live.inputs}</dd></div>
          <div><dt className="inline font-medium">Label: </dt><dd className="inline">{card.live.label}</dd></div>
          <div><dt className="inline font-medium">Guard: </dt><dd className="inline">{card.live.guard}</dd></div>
          <div><dt className="inline font-medium">SHA-256: </dt><dd className="inline font-mono break-all">{card.live.model_sha256}</dd></div></dl>
      </details>
    </div>}
  </StaffLayout>
}
