import { AlertTriangle, CheckCircle2, Phone } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import Footer from '../components/Footer'
import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import TopNav from '../components/TopNav'
import ZoneCard from '../components/ZoneCard'
import { formatPredictionTime } from '../services/predictions'
import { isZonePredictionStale } from '../services/proxyPredictions'
import { MAX_DESCRIPTION_LENGTH, REPORT_CONDITIONS, fetchReportingZones, submitCitizenReport, validateCitizenReport } from '../services/reports'

const SEVERITY_OPTIONS = [
  { label: 'Mild', color: '#16A34A' },
  { label: 'Serious', color: '#EA580C' },
  { label: 'Dangerous', color: '#DC2626' },
]
const EMPTY_FORM = { zone_id: '', observed_condition: 'Street flooding', perceived_severity: 'Mild', description: '', location_description:'', latitude:'', longitude:'', location_accuracy_m:null }

// Citizens page — public flood warnings by zone + anonymous flood condition reporting
export default function CitizenPage({ predictions, showToast }) {
  const { user } = useAuth()
  const [reportZones,setReportZones] = useState([]), [zoneError,setZoneError] = useState(''), [zoneReload,setZoneReload] = useState(0)
  const [locating,setLocating] = useState(false), [locationMessage,setLocationMessage] = useState('')
  useEffect(() => {
    const controller = new AbortController()
    setZoneError('')
    fetchReportingZones({ signal:controller.signal }).then(items => { if(!controller.signal.aborted)setReportZones(items) }).catch(error => { if(!controller.signal.aborted)setZoneError(error.message) })
    return () => controller.abort()
  }, [zoneReload])
  function locate() {
    if (!navigator.geolocation) { setLocationMessage('Location is not supported. Enter the landmark or coordinates manually.'); return }
    setLocating(true); setLocationMessage('')
    navigator.geolocation.getCurrentPosition(position => {
      setForm(previous => ({...previous,latitude:String(position.coords.latitude),longitude:String(position.coords.longitude),location_accuracy_m:position.coords.accuracy}))
      setLocationMessage('Device location added. Check that it is where you observed the flooding.'); setLocating(false)
    }, () => {setLocationMessage('Location could not be obtained. Describe the location or enter coordinates manually.');setLocating(false)}, {enableHighAccuracy:true,timeout:10000,maximumAge:60000})
  }
  const zones = predictions.data?.zones ?? []
  const isProxy = predictions.selection?.view !== undefined && predictions.selection.view !== 'legacy'
  const isReplay = predictions.selection?.view === 'v1_replay'
  const warningZones = zones.filter((z) => z.risk === 'High' || z.risk === 'Extreme')
  const hasOldWarnings = warningZones.some((zone) => isZonePredictionStale(zone))
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
    if (submissionRef.current || locating) return
    const errors = validateCitizenReport(form, reportZones.map((zone) => zone.id))
    setFieldErrors(errors)
    setSubmitError('')
    if (Object.keys(errors).length) {
      document.getElementById(`report-${Object.keys(errors)[0]}`)?.focus()
      return
    }

    const controller = new AbortController()
    submissionRef.current = controller
    setSubmitting(true)
    const zoneName = reportZones.find((zone) => zone.id === form.zone_id)?.name
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
          <h1 className="text-4xl font-bold tracking-tight">{isProxy ? 'Nairobi Environmental Risk Research' : 'Nairobi County Weather Indications'}</h1>
          <p className="text-white/80">{isProxy
            ? 'Explore next-day environmental proxy classes and report conditions you observe now. Historical replays are not current flood warnings.'
            : 'View saved weather-based risk indications and report conditions in your area. Check update times and official warnings.'}</p>
          {user ? <Link to="/officer/reports" className="inline-flex rounded-btn border border-white/50 px-4 py-2 text-sm font-semibold hover:bg-white/10">Review citizen reports</Link> : <a href="#report" className="inline-flex rounded-btn border border-white/50 px-4 py-2 text-sm font-semibold hover:bg-white/10">Report a flood condition</a>}

          {warningZones.length > 0 && (
            <div className="bg-red-600 rounded-card px-4 py-3 text-sm font-medium inline-block">
              {isReplay ? 'HISTORICAL RESEARCH CLASSES' : hasOldWarnings ? 'LATEST SAVED INDICATION' : 'ELEVATED WEATHER INDICATION'} — displayed for {warningZones.map((z) => z.name).join(', ')}.
            </div>
          )}
        </div>
      </section>

      {/* Zone grid */}
      <section id="warnings" className="py-10 px-6 scroll-mt-20">
        <div className="max-w-content mx-auto space-y-6">
          <h2 className="text-2xl font-semibold tracking-tight text-ink">{isReplay ? 'Historical Proxy Classes by Monitoring Zone' : 'Saved Indications by Monitoring Zone'}</h2>
          <p className="text-sm text-muted">Latest saved weather advisories. Local drainage is not assessed. <Link to="/" className="text-brand underline">Explore the map</Link>.</p>
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
              <ZoneCard key={zone.id} zone={zone} index={i} onReport={user ? undefined : reportZone} />
            ))}
          </div>
        </div>
      </section>

      {/* Report section */}
      {!user && <section id="report" className="py-20 px-6 bg-bg scroll-mt-20">
        <div className="max-w-content mx-auto grid grid-cols-1 lg:grid-cols-5 gap-10">
          <div className="lg:col-span-3 space-y-6">
            <div>
              <h2 className="text-2xl font-semibold tracking-tight text-ink">Report a Flood Condition</h2>
              <p className="text-muted mt-1">
                Tell us what you see in a monitored zone. No account is required. Reports do not directly change the warnings above.
              </p>
              {isReplay && <p className="text-sm text-muted">This form records conditions reported now. Selecting a historical replay does not backdate a citizen report.</p>}
            </div>

            {submittedReport ? (
              <div id="report-success" role="status" tabIndex={-1} className="bg-surface border border-border rounded-card p-8 text-center space-y-3">
                <CheckCircle2 size={40} className="text-risk-low mx-auto" />
                <h3 className="font-semibold text-ink">Thank you — your report has been recorded.</h3>
                <p className="text-sm text-muted">{submittedReport.zoneName} · Reference #{submittedReport.id}</p>
                <p className="text-sm text-muted">Your report is available in the staff inbox for review.</p>
                <p className="text-xs text-muted">Received: {formatPredictionTime(submittedReport.timestamp)}</p>
                <div className="flex flex-wrap justify-center gap-4">
                  <button type="button" onClick={startAnotherReport} className="text-ink text-sm font-medium underline underline-offset-4">Submit another report</button>
                  <a href="#warnings" className="text-ink text-sm font-medium underline underline-offset-4">Back to warnings</a>
                </div>
              </div>
            ) : (
              <form onSubmit={handleSubmit} noValidate aria-busy={submitting} className="bg-surface border border-border rounded-card p-6 space-y-6">
                {reportZones.length === 0 && (
                  <p role="status" className="text-sm text-muted">
                    {zoneError || 'Loading reporting zones...'} <button type="button" className="underline" onClick={() => setZoneReload(value => value+1)}>Retry zones</button>
                  </p>
                )}
                {submitError && <p id="report-error" role="alert" tabIndex={-1} className="text-sm text-risk-extreme">{submitError}</p>}
                <fieldset disabled={submitting || locating || reportZones.length === 0} className="space-y-6">
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
                      {form.zone_id && !reportZones.some((zone) => zone.id === form.zone_id) && <option value={form.zone_id} disabled>Selected zone unavailable</option>}
                      {reportZones.map((zone) => <option key={zone.id} value={zone.id}>{zone.name}</option>)}
                    </select>
                    {fieldErrors.zone_id && <p id="report-zone-error" className="text-sm text-risk-extreme mt-1">{fieldErrors.zone_id}</p>}
                  </div>

                  <div className="space-y-2">
                    <label htmlFor="report-location_description" className="block text-sm font-medium text-ink">Specific location / landmark</label>
                    <input id="report-location_description" required maxLength={250} value={form.location_description} onChange={event => updateField('location_description',event.target.value)} aria-invalid={Boolean(fieldErrors.location_description)} placeholder="e.g. outside Tmall, on the road towards Strathmore" className="w-full border border-border rounded-btn p-2 text-sm bg-surface text-ink" />
                    {fieldErrors.location_description && <p role="alert" className="text-sm text-risk-extreme">{fieldErrors.location_description}</p>}
                    <p className="text-xs text-muted">Visible to reviewing officers and admins. Avoid personal contact details. A report pin does not generate a location-specific forecast.</p>
                    <button type="button" disabled={locating} onClick={locate} className="border border-border rounded-btn px-3 py-2 text-sm text-ink">{locating ? 'Getting location...' : 'Use my device location (optional)'}</button>
                    {locationMessage && <p role="status" className="text-xs text-muted">{locationMessage}</p>}
                    <details><summary className="text-sm text-brand cursor-pointer">Check or enter coordinates (optional)</summary><div className="grid grid-cols-2 gap-3 mt-2">{['latitude','longitude'].map(field => <label className="text-xs text-ink capitalize" key={field}>{field}<input id={`report-${field}`} type="number" step="any" min={field==='latitude'?-90:-180} max={field==='latitude'?90:180} value={form[field]} onChange={event => {updateField(field,event.target.value);setForm(previous=>({...previous,location_accuracy_m:null}))}} aria-invalid={Boolean(fieldErrors[field])} className="block w-full border border-border rounded-btn p-2 bg-surface" /></label>)}</div></details>
                    {fieldErrors.latitude && <p role="alert" className="text-sm text-risk-extreme">{fieldErrors.latitude}</p>}
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
                    disabled={submitting || locating || reportZones.length === 0}
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
      </section>}

      <Footer />
    </div>
  )
}
