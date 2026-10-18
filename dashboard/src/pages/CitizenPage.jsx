import { AlertTriangle, CheckCircle2, Phone } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import Footer from '../components/Footer'
import PredictionStatus from '../components/PredictionStatus'
import TopNav from '../components/TopNav'
import ZoneCard from '../components/ZoneCard'
import { formatPredictionTime, isPredictionStale } from '../services/predictions'
import { MAX_DESCRIPTION_LENGTH, REPORT_CONDITIONS, submitCitizenReport, validateCitizenReport } from '../services/reports'

const SEVERITY_OPTIONS = [
  { label: 'Mild', color: '#16A34A' },
  { label: 'Serious', color: '#EA580C' },
  { label: 'Dangerous', color: '#DC2626' },
]
const EMPTY_FORM = { zone_id: '', observed_condition: 'Street flooding', perceived_severity: 'Mild', description: '' }

// Citizens page — public flood warnings by zone + anonymous flood condition reporting
export default function CitizenPage({ predictions, showToast }) {
  const zones = predictions.data?.zones ?? []
  const warningZones = zones.filter((z) => z.risk === 'High' || z.risk === 'Extreme')
  const hasOldWarnings = warningZones.some((zone) => isPredictionStale(zone.timestamp))
  const [zoneFilter, setZoneFilter] = useState('')
  const filteredZone = zones.find((zone) => zone.id === zoneFilter)
  const visibleZones = filteredZone ? [filteredZone] : zones

  const [form, setForm] = useState(EMPTY_FORM)
  const [submittedReport, setSubmittedReport] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [fieldErrors, setFieldErrors] = useState({})
  const [submitError, setSubmitError] = useState('')
  const submissionRef = useRef(null)

  useEffect(() => () => submissionRef.current?.abort(), [])

  // Smooth-scroll to a hash target (e.g. #report, #zone-mathare) once content has rendered
  useEffect(() => {
    if (window.location.hash) {
      const el = document.getElementById(window.location.hash.slice(1))
      el?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, [zones.length])

  function updateField(field, value) {
    setForm((previous) => ({ ...previous, [field]: value }))
    setFieldErrors((previous) => ({ ...previous, [field]: null }))
    setSubmitError('')
  }

  const reportZone = useCallback((zoneId) => {
    if (!submissionRef.current) {
      setForm((previous) => ({ ...previous, zone_id: zoneId }))
      setSubmittedReport(null)
      setFieldErrors({})
      setSubmitError('')
    }
    document.getElementById('report')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [])

  async function handleSubmit(e) {
    e.preventDefault()
    if (submissionRef.current) return
    const errors = validateCitizenReport(form, zones.map((zone) => zone.id))
    setFieldErrors(errors)
    setSubmitError('')
    if (Object.keys(errors).length) {
      document.getElementById(`report-${Object.keys(errors)[0]}`)?.focus()
      return
    }

    const controller = new AbortController()
    submissionRef.current = controller
    setSubmitting(true)
    const zoneName = zones.find((zone) => zone.id === form.zone_id)?.name
    try {
      const report = await submitCitizenReport(form, { signal: controller.signal })
      if (controller.signal.aborted) return
      setSubmittedReport({ ...report, zoneName })
      showToast?.('Report received. Thank you.', 'success')
      requestAnimationFrame(() => document.getElementById('report-success')?.focus())
    } catch (error) {
      if (controller.signal.aborted) return
      setSubmitError(error.message)
      setFieldErrors(error.fieldErrors ?? {})
      requestAnimationFrame(() => document.getElementById('report-error')?.focus())
    } finally {
      if (!controller.signal.aborted) setSubmitting(false)
      if (submissionRef.current === controller) submissionRef.current = null
    }
  }

  function startAnotherReport() {
    setForm({ ...EMPTY_FORM, zone_id: submittedReport.zone_id })
    setSubmittedReport(null)
    setFieldErrors({})
    setSubmitError('')
    requestAnimationFrame(() => document.getElementById('report-zone_id')?.focus())
  }

  return (
    <div id="top" className="min-h-screen flex flex-col page-transition">
      <TopNav variant="public" active="citizen" />

      {/* Hero */}
      <section
        className="py-20 px-6 text-white"
        style={{ background: 'linear-gradient(135deg, #0F2D5C 0%, #1E4080 100%)' }}
      >
        <div className="max-w-content mx-auto space-y-4">
          <h1 className="text-4xl font-bold tracking-tight">Nairobi County Flood Warnings</h1>
          <p className="text-white/80">View the latest saved warnings and report conditions in your area. Predictions run hourly.</p>
          <a href="#report" className="inline-flex rounded-btn border border-white/50 px-4 py-2 text-sm font-semibold hover:bg-white/10">
            Report a flood condition
          </a>

          {warningZones.length > 0 && (
            <div className="bg-red-600 rounded-card px-4 py-3 text-sm font-medium inline-block">
              {hasOldWarnings ? 'LATEST SAVED WARNING' : 'ACTIVE WARNING'} — {warningZones.map((z) => z.name).join(' and ')}{' '}
              {warningZones.length > 1 ? 'are' : 'is'} at elevated flood risk. Follow instructions below.
            </div>
          )}
        </div>
      </section>

      {/* Zone grid */}
      <section id="warnings" className="py-10 px-6 scroll-mt-20">
        <div className="max-w-content mx-auto space-y-6">
          <h2 className="text-2xl font-semibold tracking-tight text-ink">Current Risk by Zone</h2>
          <PredictionStatus predictions={predictions} />
          {zones.length > 0 && (
            <div className="max-w-sm">
              <label htmlFor="warning-zone" className="block text-sm font-medium text-ink mb-1.5">View a zone</label>
              <select
                id="warning-zone"
                value={filteredZone?.id ?? ''}
                onChange={(event) => setZoneFilter(event.target.value)}
                className="w-full h-10 border border-border rounded-btn px-3 text-sm bg-surface text-ink"
              >
                <option value="">All zones</option>
                {zones.map((zone) => <option key={zone.id} value={zone.id}>{zone.name}</option>)}
              </select>
            </div>
          )}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {visibleZones.map((zone, i) => (
              <ZoneCard key={zone.id} zone={zone} index={i} onReport={reportZone} />
            ))}
          </div>
        </div>
      </section>

      {/* Report section */}
      <section id="report" className="py-20 px-6 bg-bg scroll-mt-20">
        <div className="max-w-content mx-auto grid grid-cols-1 lg:grid-cols-5 gap-10">
          <div className="lg:col-span-3 space-y-6">
            <div>
              <h2 className="text-2xl font-semibold tracking-tight text-ink">Report a Flood Condition</h2>
              <p className="text-muted mt-1">
                Tell us what you see in a monitored zone. No account is required. Reports do not directly change the warnings above.
              </p>
            </div>

            {submittedReport ? (
              <div id="report-success" role="status" tabIndex={-1} className="bg-surface border border-border rounded-card p-8 text-center space-y-3">
                <CheckCircle2 size={40} className="text-risk-low mx-auto" />
                <h3 className="font-semibold text-ink">Thank you — your report has been recorded.</h3>
                <p className="text-sm text-muted">{submittedReport.zoneName} · Reference #{submittedReport.id}</p>
                <p className="text-xs text-muted">Received: {formatPredictionTime(submittedReport.timestamp)}</p>
                <div className="flex flex-wrap justify-center gap-4">
                  <button type="button" onClick={startAnotherReport} className="text-ink text-sm font-medium underline underline-offset-4">Submit another report</button>
                  <a href="#warnings" className="text-ink text-sm font-medium underline underline-offset-4">Back to warnings</a>
                </div>
              </div>
            ) : (
              <form onSubmit={handleSubmit} noValidate aria-busy={submitting} className="bg-surface border border-border rounded-card p-6 space-y-6">
                {zones.length === 0 && (
                  <p role="status" className="text-sm text-muted">
                    {predictions.isRefreshing ? 'Loading reporting zones...' : 'Reporting zones are unavailable. Refresh the warnings to try again.'}
                  </p>
                )}
                {submitError && <p id="report-error" role="alert" tabIndex={-1} className="text-sm text-risk-extreme">{submitError}</p>}
                <fieldset disabled={submitting || zones.length === 0} className="space-y-6">
                  <div>
                    <label htmlFor="report-zone_id" className="block text-sm font-medium text-ink mb-1.5">Zone</label>
                    <select
                      id="report-zone_id"
                      required
                      value={form.zone_id}
                      onChange={(e) => updateField('zone_id', e.target.value)}
                      aria-invalid={Boolean(fieldErrors.zone_id)}
                      aria-describedby={fieldErrors.zone_id ? 'report-zone-error' : undefined}
                      className="w-full h-10 border border-border rounded-btn px-3 text-sm bg-surface text-ink"
                    >
                      <option value="">Choose a zone</option>
                      {form.zone_id && !zones.some((zone) => zone.id === form.zone_id) && <option value={form.zone_id} disabled>Selected zone unavailable</option>}
                      {zones.map((zone) => <option key={zone.id} value={zone.id}>{zone.name}</option>)}
                    </select>
                    {fieldErrors.zone_id && <p id="report-zone-error" className="text-sm text-risk-extreme mt-1">{fieldErrors.zone_id}</p>}
                  </div>

                  <fieldset id="report-observed_condition" tabIndex={-1} aria-describedby={fieldErrors.observed_condition ? 'report-condition-error' : undefined}>
                    <legend className="block text-sm font-medium text-ink mb-1.5">What do you observe?</legend>
                    <div className="grid grid-cols-2 gap-2">
                      {REPORT_CONDITIONS.map((c) => (
                        <label
                          key={c}
                          className={`cursor-pointer text-center text-sm font-medium rounded-full border px-3 py-2 transition-colors focus-within:ring-2 focus-within:ring-accent ${
                            form.observed_condition === c
                              ? 'bg-brand text-white border-brand'
                              : 'border-border text-ink hover:bg-bg'
                          }`}
                        >
                          <input
                            type="radio"
                            name="condition"
                            value={c}
                            checked={form.observed_condition === c}
                            onChange={(e) => updateField('observed_condition', e.target.value)}
                            className="sr-only"
                          />
                          {c}
                        </label>
                      ))}
                    </div>
                    {fieldErrors.observed_condition && <p id="report-condition-error" className="text-sm text-risk-extreme mt-1">{fieldErrors.observed_condition}</p>}
                  </fieldset>

                  <fieldset id="report-perceived_severity" tabIndex={-1} aria-describedby={fieldErrors.perceived_severity ? 'report-severity-error' : undefined}>
                    <legend className="block text-sm font-medium text-ink mb-1.5">How severe?</legend>
                    <div className="flex flex-wrap gap-2">
                      {SEVERITY_OPTIONS.map((s) => (
                        <label
                          key={s.label}
                          className="flex-1 cursor-pointer text-center text-sm font-medium rounded-full border px-3 py-2 transition-colors focus-within:ring-2 focus-within:ring-accent"
                          style={
                            form.perceived_severity === s.label
                              ? { backgroundColor: s.color, borderColor: s.color, color: '#fff' }
                              : { borderColor: 'var(--border)', color: s.color }
                          }
                        >
                          <input
                            type="radio"
                            name="severity"
                            value={s.label}
                            checked={form.perceived_severity === s.label}
                            onChange={(e) => updateField('perceived_severity', e.target.value)}
                            className="sr-only"
                          />
                          {s.label}
                        </label>
                      ))}
                    </div>
                    {fieldErrors.perceived_severity && <p id="report-severity-error" className="text-sm text-risk-extreme mt-1">{fieldErrors.perceived_severity}</p>}
                  </fieldset>

                  <div>
                    <label htmlFor="report-description" className="block text-sm font-medium text-ink mb-1.5">
                      Brief description <span className="text-muted font-normal">(optional)</span>
                    </label>
                    <textarea
                      id="report-description"
                      rows={4}
                      maxLength={MAX_DESCRIPTION_LENGTH}
                      value={form.description}
                      onChange={(e) => updateField('description', e.target.value)}
                      aria-invalid={Boolean(fieldErrors.description)}
                      aria-describedby={`report-description-count${fieldErrors.description ? ' report-description-error' : ''}`}
                      className="w-full border border-border rounded-btn px-3 py-2 text-sm bg-surface text-ink"
                    />
                    <p id="report-description-count" className="text-xs text-muted text-right mt-1">
                      {form.description.length} / {MAX_DESCRIPTION_LENGTH}
                    </p>
                    {fieldErrors.description && <p id="report-description-error" className="text-sm text-risk-extreme mt-1">{fieldErrors.description}</p>}
                  </div>

                  <button
                    type="submit"
                    disabled={submitting || zones.length === 0}
                    className="w-full h-12 rounded-card bg-brand text-white font-semibold hover:bg-brand-light transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {submitting ? 'Submitting report...' : 'Submit Report'}
                  </button>
                </fieldset>
              </form>
            )}
          </div>

          <aside className="lg:col-span-2">
            <div className="bg-surface border border-border rounded-card p-6 space-y-4 lg:sticky lg:top-24">
              <h3 className="text-lg font-semibold text-ink">Emergency Contacts</h3>
              <div className="space-y-3">
                {[
                  ['Kenya Red Cross', '0800 723 253'],
                  ['Nairobi County NDMA', '020 222 2222'],
                  ['Emergency Services', '999 / 112'],
                ].map(([label, phone]) => (
                  <div key={label} className="flex items-center gap-3 text-sm">
                    <Phone size={16} className="text-brand" />
                    <span className="text-ink">{label}</span>
                    <span className="ml-auto font-semibold text-ink">{phone}</span>
                  </div>
                ))}
              </div>
              <p className="text-xs text-muted">These services operate 24/7</p>
              <div className="border-t border-border pt-4 flex gap-2 text-sm text-ink">
                <AlertTriangle size={18} className="text-risk-high shrink-0" />
                <p>Never attempt to cross flooded roads or rivers. Turn around — don&apos;t drown.</p>
              </div>
            </div>
          </aside>
        </div>
      </section>

      <Footer />
    </div>
  )
}
