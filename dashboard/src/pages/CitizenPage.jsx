import { AlertTriangle, Camera, CheckCircle2, Copy, LocateFixed, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import Footer from '../components/Footer'
import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { formatNairobi, useLanguage } from '../context/LanguageContext'
import TopNav from '../components/TopNav'
import {
  MAX_DESCRIPTION_LENGTH, MAX_PHOTO_BYTES, PHOTO_TYPES, REPORT_CONDITIONS, checkReportStatus, fetchReportingAreas,
  locateReportingArea, submitCitizenReport, uploadReportPhoto, validateCitizenReport,
} from '../services/reports'
import { forgetReport, rememberReport, savedReports } from '../services/myReports'

const SEVERITY_OPTIONS = [
  { label: 'Mild', color: '#16A34A' },
  { label: 'Serious', color: '#EA580C' },
  { label: 'Dangerous', color: '#DC2626' },
]
const EMPTY_FORM = { area_id: '', observed_condition: 'Street flooding', perceived_severity: 'Mild', description: '', location_description:'', latitude:'', longitude:'', location_accuracy_m:null }
// Default client-side messages map to translated text; server explanations are shown as sent.
const DEFAULT_ERRORS = {
  'Choose your sub-county.': 'error.areaRequired',
  'Describe a landmark, road or address (up to 250 characters).': 'error.landmark',
  'Supply both coordinates within valid latitude/longitude ranges.': 'error.coordinates',
  [`Use ${MAX_DESCRIPTION_LENGTH} characters or fewer.`]: 'error.description',
}
const inputCls = 'w-full h-10 border border-border rounded-btn px-3 text-sm bg-surface text-ink'

// One numbered step of the report form. Defined outside the page so inputs keep focus.
function Step({ n, title, children }) {
  return <div className="space-y-4">
    <h3 className="flex items-center gap-2.5 font-semibold text-ink"><span className="w-6 h-6 rounded-full bg-brand text-white text-xs grid place-items-center tabular">{n}</span>{title}</h3>
    <div className="space-y-4 sm:pl-8">{children}</div>
  </div>
}

const STATUS_TONE = { New: 'var(--text-muted)', Reviewed: 'var(--accent)', ActionNeeded: 'var(--risk-high)', Resolved: 'var(--risk-low)' }

// One report's live status: a coloured dot and the decision in plain words.
function StatusLine({ result }) {
  const { lang, t } = useLanguage()
  return <div className="space-y-1">
    <p className="flex items-center gap-2 text-sm font-medium"><span className="w-2 h-2 rounded-full shrink-0" style={{ background: STATUS_TONE[result.review_status] ?? 'var(--text-muted)' }} aria-hidden="true" />
      {t(`status.${result.review_status}`)}</p>
    <p className="text-xs text-muted">{t(`condition.${result.observed_condition}`)} · {t('citizen.statusReported', { date: formatNairobi(lang, result.reported_at, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }), area: result.sub_county })}</p>
    {result.on_public_map && <p className="text-xs" style={{ color: '#7c3aed' }}>{t('citizen.statusOnMap')}</p>}
  </div>
}

// "What happened to my report?" Reports sent from this phone are listed and checked
// automatically; a reference from another phone can be typed in.
function MyReports({ saved, onForget }) {
  const { t } = useLanguage()
  const [statuses, setStatuses] = useState({}), [typed, setTyped] = useState('')
  const [busy, setBusy] = useState(false), [result, setResult] = useState(null), [error, setError] = useState('')
  useEffect(() => {
    const controller = new AbortController()
    // One at a time, newest first: a handful of quick checks, well inside the server's limit.
    ;(async () => {
      for (const item of saved) {
        if (controller.signal.aborted) return
        try { const r = await checkReportStatus(item.reference, null, { signal: controller.signal }); setStatuses(s => ({ ...s, [item.reference]: r })) }
        catch (failure) { if (!controller.signal.aborted) setStatuses(s => ({ ...s, [item.reference]: { error: failure.message } })) }
      }
    })()
    return () => controller.abort()
  }, [saved])
  async function check(event) {
    event.preventDefault()
    setBusy(true); setError(''); setResult(null)
    try { setResult(await checkReportStatus(typed)) } catch (failure) { setError(failure.message) } finally { setBusy(false) }
  }
  return <section id="check" aria-labelledby="check-heading" className="panel p-5 space-y-4 scroll-mt-20">
    <h2 id="check-heading" className="font-semibold text-ink">{t('citizen.myReports')}</h2>
    {saved.length ? <ul className="divide-y divide-border -my-1">{saved.map(item => {
      const status = statuses[item.reference]
      return <li key={item.reference} className="py-3 space-y-1.5">
        <div className="flex items-center justify-between gap-2">
          <span className="font-mono text-sm font-semibold tracking-wide">{item.reference}</span>
          <button type="button" onClick={() => onForget(item.reference)} className="text-xs text-muted hover:text-ink">{t('citizen.forget')}</button>
        </div>
        {!status ? <p className="text-xs text-muted" role="status">{t('citizen.checking')}</p>
          : status.error ? <p className="text-xs text-muted">{status.error}</p> : <StatusLine result={status} />}
      </li>
    })}</ul> : <p className="text-sm text-muted">{t('citizen.noReports')}</p>}
    <form onSubmit={check} className="space-y-2 pt-1 border-t border-border">
      <label htmlFor="check-reference" className="block text-xs font-medium text-muted pt-3">{t('citizen.checkOther')}</label>
      <div className="flex gap-2">
        <input id="check-reference" autoCapitalize="characters" autoComplete="off" spellCheck={false} value={typed} onChange={e => setTyped(e.target.value)}
          placeholder={t('citizen.referencePlaceholder')} className={inputCls + ' font-mono uppercase placeholder:normal-case placeholder:font-sans'} />
        <button disabled={busy || !typed.trim()} className="press shrink-0 h-10 px-4 rounded-btn border border-border bg-surface text-sm font-medium hover:bg-surface-2 disabled:opacity-50">{busy ? t('citizen.checking') : t('citizen.checkButton')}</button>
      </div>
    </form>
    {error && <p role="alert" className="text-sm text-risk-extreme">{error}</p>}
    {result && <div role="status" className="rounded-btn bg-surface-2 p-3 space-y-1"><p className="font-mono text-sm font-semibold">{result.reference}</p><StatusLine result={result} /></div>}
  </section>
}

// Public observations are independent of model availability and research selection.
export default function CitizenPage({ showToast }) {
  const { user } = useAuth()
  const { lang, t } = useLanguage()
  const [reportZones,setReportZones] = useState([]), [zoneError,setZoneError] = useState(''), [zoneReload,setZoneReload] = useState(0)
  const [locating,setLocating] = useState(false), [locationMessage,setLocationMessage] = useState(''), [pinArea,setPinArea] = useState(null)
  const [photo, setPhoto] = useState(null), [photoUrl, setPhotoUrl] = useState(''), [photoError, setPhotoError] = useState('')
  const [photoResult, setPhotoResult] = useState(''), [copied, setCopied] = useState(false)
  const [saved, setSaved] = useState(() => savedReports())
  useEffect(() => {
    const controller = new AbortController()
    setZoneError('')
    fetchReportingAreas({ signal:controller.signal }).then(items => { if(!controller.signal.aborted)setReportZones(items) }).catch(error => { if(!controller.signal.aborted)setZoneError(error.message) })
    return () => controller.abort()
  }, [zoneReload])
  useEffect(() => () => { if (photoUrl) URL.revokeObjectURL(photoUrl) }, [photoUrl])
  function locate() {
    if (!navigator.geolocation) { setLocationMessage(t('citizen.locationUnsupported')); return }
    setLocating(true); setLocationMessage('')
    navigator.geolocation.getCurrentPosition(position => {
      setForm(previous => ({...previous,latitude:String(position.coords.latitude),longitude:String(position.coords.longitude),location_accuracy_m:position.coords.accuracy}))
      setLocationMessage(t('citizen.located')); setLocating(false)
    }, () => {setLocationMessage(t('citizen.locationFailed'));setLocating(false)}, {enableHighAccuracy:true,timeout:10000,maximumAge:60000})
  }
  const [form, setForm] = useState(() => ({ ...EMPTY_FORM, area_id: new URLSearchParams(window.location.search).get('area') ?? '' }))
  const [submittedReport, setSubmittedReport] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [fieldErrors, setFieldErrors] = useState({})
  const [submitError, setSubmitError] = useState('')
  const submissionRef = useRef(null)
  const fieldError = field => fieldErrors[field] && (DEFAULT_ERRORS[fieldErrors[field]] ? t(DEFAULT_ERRORS[fieldErrors[field]]) : fieldErrors[field])

  useEffect(() => () => submissionRef.current?.abort(), [])

  // A pin picks its own sub-county, so citizens never need to know where the boundary runs.
  useEffect(() => {
    const lat = Number(form.latitude), lon = Number(form.longitude)
    if (form.latitude === '' || form.longitude === '' || !Number.isFinite(lat) || !Number.isFinite(lon)) { setPinArea(null); return }
    const controller = new AbortController()
    const timer = setTimeout(() => locateReportingArea(lat, lon, { signal:controller.signal }).then(area => {
      if (controller.signal.aborted) return
      setPinArea(area ?? { outside:true })
      if (area) { setForm(previous => ({ ...previous, area_id:area.id })); setFieldErrors(previous => ({ ...previous, area_id:null })) }
    }).catch(() => { if (!controller.signal.aborted) setPinArea(null) }), 400)
    return () => { clearTimeout(timer); controller.abort() }
  }, [form.latitude, form.longitude])

  // Smooth-scroll to a hash target (e.g. #report, #check) once content has rendered
  useEffect(() => {
    if (window.location.hash) document.getElementById(window.location.hash.slice(1))?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [reportZones.length])

  function updateField(field, value) {
    setForm((previous) => ({ ...previous, [field]: value }))
    setFieldErrors((previous) => ({ ...previous, [field]: null }))
    setSubmitError('')
  }

  function choosePhoto(file) {
    setPhotoError('')
    if (!file) return
    if (!PHOTO_TYPES.includes(file.type)) { setPhotoError('JPEG, PNG, WebP'); return }
    if (file.size > MAX_PHOTO_BYTES) { setPhotoError('8 MB'); return }
    if (photoUrl) URL.revokeObjectURL(photoUrl)
    setPhoto(file); setPhotoUrl(URL.createObjectURL(file))
  }
  function clearPhoto() { if (photoUrl) URL.revokeObjectURL(photoUrl); setPhoto(null); setPhotoUrl(''); setPhotoError('') }

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
    setSubmitting(true); setPhotoResult('')
    const zoneName = reportZones.find((zone) => zone.id === form.area_id)?.name
    try {
      const report = await submitCitizenReport(form, { signal: controller.signal })
      if (controller.signal.aborted) return
      // The report is saved; a photo problem never undoes it.
      if (photo && report.tracking_code) {
        try { await uploadReportPhoto(report.id, report.tracking_code, photo, { signal: controller.signal }); setPhotoResult(t('citizen.photoAdded')) }
        catch (failure) { setPhotoResult(t('citizen.photoFailed', { reason: failure.message })) }
      }
      setSubmittedReport({ ...report, zoneName })
      // Remember it on this phone so the resident never has to type the reference.
      if (report.tracking_code) setSaved(rememberReport({ reference: report.tracking_code, sentAt: report.timestamp, condition: report.observed_condition, area: zoneName }))
      clearPhoto()
      showToast?.(t('citizen.thanks'), 'success')
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
    setForm({ ...EMPTY_FORM, area_id: submittedReport.area_id })
    setSubmittedReport(null); setFieldErrors({}); setSubmitError(''); setPhotoResult(''); setCopied(false)
    requestAnimationFrame(() => document.getElementById('report-area_id')?.focus())
  }

  async function copyCode() {
    try { await navigator.clipboard.writeText(submittedReport.tracking_code); setCopied(true) } catch { /* the reference stays on screen */ }
  }

  const chip = active => `cursor-pointer text-center text-sm font-medium rounded-btn border px-3 h-10 grid place-items-center transition-colors focus-within:ring-2 focus-within:ring-accent ${active ? 'bg-brand text-white border-brand' : 'border-border text-ink hover:bg-surface-2'}`
  return (
    <div id="top" className="min-h-screen flex flex-col page-transition bg-bg">
      <TopNav active="citizen" />

      <section className="px-4 sm:px-6 pt-10 sm:pt-14 pb-6">
        <div className="max-w-5xl mx-auto">
          <Link to="/" className="text-sm text-muted hover:text-ink">{t('citizen.back')}</Link>
          <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight text-ink mt-3">{t('citizen.title')}</h1>
          <p className="text-muted mt-2 max-w-xl">{t('citizen.intro')}</p>
          {user && <Link to="/officer/reports" className="inline-block mt-3 text-sm text-accent font-medium">{t('citizen.staffInbox')}</Link>}
        </div>
      </section>

      {!user && <section id="report" className="px-4 sm:px-6 pb-16 scroll-mt-20 flex-1">
        <div className="max-w-5xl mx-auto grid grid-cols-1 lg:grid-cols-[1fr_300px] gap-6 lg:gap-8 items-start">
          {submittedReport ? (
            <div id="report-success" role="status" tabIndex={-1} className="panel p-8 sm:p-10 text-center space-y-4">
              <CheckCircle2 size={44} className="text-risk-low mx-auto" />
              <h2 className="text-xl font-semibold text-ink">{t('citizen.thanks')}</h2>
              <p className="text-sm text-muted">{submittedReport.zoneName} · {formatNairobi(lang, submittedReport.timestamp, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}</p>
              {submittedReport.tracking_code && <div className="mx-auto max-w-sm rounded-card border border-border bg-surface-2 p-4 space-y-2">
                <p className="eyebrow">{t('citizen.yourReference')}</p>
                <p className="text-3xl font-semibold font-mono tracking-wider" data-testid="tracking-code">{submittedReport.tracking_code}</p>
                <p className="text-xs text-muted">{t('citizen.savedHere')}</p>
                <button type="button" onClick={copyCode} className="press inline-flex items-center gap-1.5 text-sm font-medium text-accent"><Copy size={14} aria-hidden="true" />{copied ? t('citizen.copied') : t('citizen.copy')}</button>
              </div>}
              {photoResult && <p className="text-sm">{photoResult}</p>}
              <p className="text-sm text-muted">{t('citizen.next')}</p>
              <div className="flex flex-wrap justify-center gap-3 pt-1">
                <button type="button" onClick={startAnotherReport} className="press h-10 px-4 rounded-btn border border-border bg-surface text-sm font-medium hover:bg-surface-2">{t('citizen.another')}</button>
                <Link to="/" className="press h-10 px-4 rounded-btn bg-brand text-white text-sm font-medium grid place-items-center">{t('citizen.backMap')}</Link>
              </div>
            </div>
          ) : (
            <form onSubmit={handleSubmit} noValidate aria-busy={submitting} className="panel p-5 sm:p-7 space-y-8">
              {reportZones.length === 0 && (
                <p role="status" className="text-sm text-muted">
                  {zoneError || t('citizen.loadingAreas')} <button type="button" className="underline" onClick={() => setZoneReload(value => value+1)}>{t('citizen.retry')}</button>
                </p>
              )}
              {submitError && <p id="report-error" role="alert" tabIndex={-1} className="text-sm text-risk-extreme">{submitError}</p>}
              <fieldset disabled={submitting || locating || reportZones.length === 0} className="space-y-8">
                <Step n={1} title={t('citizen.step1')}>
                  <div className="flex flex-wrap items-center gap-3">
                    <button type="button" disabled={locating} onClick={locate} className="press inline-flex items-center gap-2 h-10 px-4 rounded-btn bg-surface-2 text-sm font-medium text-ink hover:bg-border">
                      <LocateFixed size={16} aria-hidden="true" />{locating ? t('citizen.finding') : form.latitude ? t('citizen.updateLocation') : t('citizen.useLocation')}</button>
                    <span className="text-xs text-muted">{t('citizen.locationHint')}</span>
                  </div>
                  {locationMessage && <p role="status" className="text-xs text-muted -mt-2">{locationMessage}</p>}
                  <div className="grid sm:grid-cols-2 gap-4">
                    <div>
                      <label htmlFor="report-area_id" className="block text-sm font-medium text-ink mb-1.5">{t('citizen.subCounty')}</label>
                      <select id="report-area_id" required value={form.area_id} onChange={(e) => updateField('area_id', e.target.value)}
                        aria-invalid={Boolean(fieldErrors.area_id)} aria-describedby={fieldErrors.area_id ? 'report-zone-error' : 'report-area-hint'} className={inputCls}>
                        <option value="">{t('citizen.chooseSubCounty')}</option>
                        {form.area_id && reportZones.length > 0 && !reportZones.some((zone) => zone.id === form.area_id) && <option value={form.area_id} disabled>{t('citizen.subCountyUnavailable')}</option>}
                        {reportZones.map((zone) => <option key={zone.id} value={zone.id}>{zone.name}</option>)}
                      </select>
                      {fieldErrors.area_id ? <p id="report-zone-error" className="text-sm text-risk-extreme mt-1">{fieldError('area_id')}</p>
                        : <p id="report-area-hint" className="text-xs text-muted mt-1">{pinArea?.outside ? t('citizen.pinOutside') : pinArea ? t('citizen.pinFilled', { name: pinArea.name }) : t('citizen.pinHint')}</p>}
                    </div>
                    <div>
                      <label htmlFor="report-location_description" className="block text-sm font-medium text-ink mb-1.5">{t('citizen.landmark')}</label>
                      <input id="report-location_description" required maxLength={250} value={form.location_description} onChange={event => updateField('location_description',event.target.value)} aria-invalid={Boolean(fieldErrors.location_description)} placeholder={t('citizen.landmarkPlaceholder')} className={inputCls} />
                      {fieldErrors.location_description && <p role="alert" className="text-sm text-risk-extreme mt-1">{fieldError('location_description')}</p>}
                    </div>
                  </div>
                  <details className="text-sm"><summary className="text-accent cursor-pointer">{form.latitude ? t('citizen.coordsCheck') : t('citizen.coordsEnter')}</summary><div className="grid grid-cols-2 gap-3 mt-2">{['latitude','longitude'].map(field => <label className="text-xs text-muted" key={field}>{t(`citizen.${field}`)}<input id={`report-${field}`} type="number" step="any" min={field==='latitude'?-90:-180} max={field==='latitude'?90:180} value={form[field]} onChange={event => {updateField(field,event.target.value);setForm(previous=>({...previous,location_accuracy_m:null}))}} aria-invalid={Boolean(fieldErrors[field])} className={inputCls + ' mt-1 tabular'} /></label>)}</div></details>
                  {fieldErrors.latitude && <p role="alert" className="text-sm text-risk-extreme">{fieldError('latitude')}</p>}
                </Step>

                <Step n={2} title={t('citizen.step2')}>
                  <fieldset id="report-observed_condition" tabIndex={-1}>
                    <legend className="sr-only">{t('citizen.condition')}</legend>
                    <div className="grid grid-cols-2 gap-2">
                      {REPORT_CONDITIONS.map((c) => <label key={c} className={chip(form.observed_condition === c)}>
                        <input type="radio" name="condition" value={c} checked={form.observed_condition === c} onChange={(e) => updateField('observed_condition', e.target.value)} className="sr-only" />{t(`condition.${c}`)}
                      </label>)}
                    </div>
                  </fieldset>
                  <fieldset id="report-perceived_severity" tabIndex={-1}>
                    <legend className="block text-sm font-medium text-ink mb-1.5">{t('citizen.severity')}</legend>
                    <div className="grid grid-cols-3 gap-2">
                      {SEVERITY_OPTIONS.map((s) => {
                        const active = form.perceived_severity === s.label
                        return <label key={s.label} className="cursor-pointer text-sm font-medium rounded-btn border h-10 flex items-center justify-center gap-2 transition-colors focus-within:ring-2 focus-within:ring-accent"
                          style={active ? { backgroundColor: s.color, borderColor: s.color, color: '#fff' } : { borderColor: 'var(--border)', color: 'var(--text)' }}>
                          <input type="radio" name="severity" value={s.label} checked={active} onChange={(e) => updateField('perceived_severity', e.target.value)} className="sr-only" />
                          {!active && <span className="w-2 h-2 rounded-full" style={{ background: s.color }} aria-hidden="true" />}{t(`severity.${s.label}`)}
                        </label>
                      })}
                    </div>
                  </fieldset>
                </Step>

                <Step n={3} title={t('citizen.step3')}>
                  <div>
                    <label htmlFor="report-description" className="sr-only">{t('citizen.step3')}</label>
                    <textarea id="report-description" rows={3} maxLength={MAX_DESCRIPTION_LENGTH} value={form.description} onChange={(e) => updateField('description', e.target.value)}
                      aria-invalid={Boolean(fieldErrors.description)} aria-describedby="report-description-count"
                      placeholder={t('citizen.descriptionPlaceholder')} className="w-full border border-border rounded-btn px-3 py-2 text-sm bg-surface text-ink" />
                    <p id="report-description-count" className="text-xs text-muted flex justify-between mt-1"><span>{t('citizen.descriptionHint')}</span><span className="tabular">{form.description.length}/{MAX_DESCRIPTION_LENGTH}</span></p>
                    {fieldErrors.description && <p className="text-sm text-risk-extreme mt-1">{fieldError('description')}</p>}
                  </div>
                  <div className="space-y-2">
                    {photoUrl ? <div className="flex items-center gap-3">
                      <img src={photoUrl} alt="" className="w-20 h-20 object-cover rounded-btn border border-border" />
                      <button type="button" onClick={clearPhoto} className="press inline-flex items-center gap-1.5 text-sm text-muted hover:text-ink"><X size={14} aria-hidden="true" />{t('citizen.photoRemove')}</button>
                    </div> : <label className="press inline-flex items-center gap-2 h-10 px-4 rounded-btn border border-dashed border-border text-sm font-medium text-ink cursor-pointer hover:bg-surface-2 focus-within:ring-2 focus-within:ring-accent">
                      <Camera size={16} aria-hidden="true" />{t('citizen.photo')}
                      <input id="report-photo" type="file" accept={PHOTO_TYPES.join(',')} capture="environment" className="sr-only" onChange={e => { choosePhoto(e.target.files?.[0]); e.target.value = '' }} />
                    </label>}
                    <p className={`text-xs ${photoError ? 'text-risk-extreme' : 'text-muted'}`}>{t('citizen.photoHint')}</p>
                  </div>
                </Step>

                <div className="space-y-3">
                  <button type="submit" disabled={submitting || locating || reportZones.length === 0}
                    className="press w-full h-12 rounded-card bg-brand text-white font-semibold hover:bg-brand-light disabled:opacity-50 disabled:cursor-not-allowed">
                    {submitting ? t('citizen.sending') : t('citizen.send')}
                  </button>
                  <p className="text-xs text-muted text-center">{t('citizen.publicNote')}</p>
                </div>
              </fieldset>
            </form>
          )}

          <aside className="space-y-4 lg:sticky lg:top-24">
            <div className="panel p-5 space-y-3" style={{ borderColor: 'color-mix(in srgb, var(--risk-extreme) 35%, var(--border))' }}>
              <h2 className="font-semibold text-ink flex items-center gap-2"><AlertTriangle size={18} className="text-risk-extreme" aria-hidden="true" />{t('citizen.safeTitle')}</h2>
              <ul className="text-sm text-ink space-y-2 list-disc pl-5"><li>{t('citizen.safe1')}</li><li>{t('citizen.safe2')}</li></ul>
              <p className="text-sm border-t border-border pt-3"><span className="font-semibold">{t('citizen.danger')}</span>{' '}
                {t('citizen.call', { a: '999', b: '112', c: '1199' }).split(/(999|112|1199)/).map((part, i) => /^(999|112|1199)$/.test(part)
                  ? <a key={i} className="font-semibold text-risk-extreme tabular" href={`tel:${part}`}>{part}</a> : part)}</p>
            </div>
            <MyReports saved={saved} onForget={reference => setSaved(forgetReport(reference))} />
            <p className="text-xs text-muted px-1">{t('citizen.notEmergency')}</p>
          </aside>
        </div>
      </section>}

      <Footer />
    </div>
  )
}
