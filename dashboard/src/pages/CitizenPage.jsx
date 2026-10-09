import { AlertTriangle, CheckCircle2, Phone } from 'lucide-react'
import { useEffect, useState } from 'react'
import Footer from '../components/Footer'
import TopNav from '../components/TopNav'
import ZoneCard from '../components/ZoneCard'

const ZONE_OPTIONS = ['Mathare', 'Kibera', 'Westlands', 'CBD', 'Kasarani', 'Embakasi', 'Dagoretti', 'Ruaraka', 'Other']
const CONDITION_OPTIONS = ['Street flooding', 'River overflow', 'Blocked drainage', 'Other']
const SEVERITY_OPTIONS = [
  { label: 'Mild', color: '#16A34A' },
  { label: 'Serious', color: '#EA580C' },
  { label: 'Dangerous', color: '#DC2626' },
]
const MAX_DESCRIPTION = 200

// Citizens page — public flood warnings by zone + anonymous flood condition reporting
export default function CitizenPage({ zones, showToast }) {
  const warningZones = zones.filter((z) => z.risk === 'High' || z.risk === 'Extreme')

  const [form, setForm] = useState({
    zone: ZONE_OPTIONS[0],
    condition: CONDITION_OPTIONS[0],
    severity: 'Mild',
    description: '',
  })
  const [submitted, setSubmitted] = useState(false)

  // Smooth-scroll to a hash target (e.g. #report, #zone-mathare) once content has rendered
  useEffect(() => {
    if (window.location.hash) {
      const el = document.getElementById(window.location.hash.slice(1))
      el?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, [])

  function handleSubmit(e) {
    e.preventDefault()
    setSubmitted(true)
    showToast?.('Report submitted. Thank you.', 'success')
  }

  return (
    <div className="min-h-screen flex flex-col page-transition">
      <TopNav variant="public" active="citizen" />

      {/* Hero */}
      <section
        className="py-20 px-6 text-white"
        style={{ background: 'linear-gradient(135deg, #0F2D5C 0%, #1E4080 100%)' }}
      >
        <div className="max-w-content mx-auto space-y-4">
          <h1 className="text-4xl font-bold tracking-tight">Nairobi County Flood Warnings</h1>
          <p className="text-white/80">Stay safe. Updated every hour automatically.</p>

          {warningZones.length > 0 && (
            <div className="bg-red-600 rounded-card px-4 py-3 text-sm font-medium inline-block">
              🔴 ACTIVE WARNING — {warningZones.map((z) => z.name).join(' and ')}{' '}
              {warningZones.length > 1 ? 'are' : 'is'} at elevated flood risk. Follow instructions below.
            </div>
          )}
        </div>
      </section>

      {/* Zone grid */}
      <section className="py-10 px-6">
        <div className="max-w-content mx-auto space-y-6">
          <h2 className="text-2xl font-semibold tracking-tight text-ink">Current Risk by Zone</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {zones.map((zone, i) => (
              <ZoneCard key={zone.id} zone={zone} index={i} />
            ))}
          </div>
        </div>
      </section>

      {/* Report section */}
      <section id="report" className="py-20 px-6" style={{ backgroundColor: '#F1F5F9' }}>
        <div className="max-w-content mx-auto grid grid-cols-1 lg:grid-cols-5 gap-10">
          <div className="lg:col-span-3 space-y-6">
            <div>
              <h2 className="text-2xl font-semibold tracking-tight text-ink">Report a Flood Condition</h2>
              <p className="text-muted mt-1">
                Your reports help improve predictions for everyone in Nairobi County.
              </p>
            </div>

            {submitted ? (
              <div className="bg-surface border border-border rounded-card p-8 text-center space-y-3">
                <CheckCircle2 size={40} className="text-risk-low mx-auto" />
                <p className="font-semibold text-ink">Thank you — report submitted successfully.</p>
                <a href="#top" onClick={() => setSubmitted(false)} className="text-brand text-sm font-medium hover:underline">
                  Back to Warnings
                </a>
              </div>
            ) : (
              <form onSubmit={handleSubmit} className="bg-surface border border-border rounded-card p-6 space-y-6">
                <div>
                  <label className="block text-sm font-medium text-ink mb-1.5">Zone</label>
                  <select
                    value={form.zone}
                    onChange={(e) => setForm({ ...form, zone: e.target.value })}
                    className="w-full h-10 border border-border rounded-btn px-3 text-sm bg-surface text-ink"
                  >
                    {ZONE_OPTIONS.map((z) => (
                      <option key={z} value={z}>
                        {z}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-sm font-medium text-ink mb-1.5">What do you observe?</label>
                  <div className="grid grid-cols-2 gap-2">
                    {CONDITION_OPTIONS.map((c) => (
                      <label
                        key={c}
                        className={`cursor-pointer text-center text-sm font-medium rounded-full border px-3 py-2 transition-colors ${
                          form.condition === c
                            ? 'bg-brand text-white border-brand'
                            : 'border-border text-ink hover:bg-bg'
                        }`}
                      >
                        <input
                          type="radio"
                          name="condition"
                          value={c}
                          checked={form.condition === c}
                          onChange={(e) => setForm({ ...form, condition: e.target.value })}
                          className="sr-only"
                        />
                        {c}
                      </label>
                    ))}
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-ink mb-1.5">How severe?</label>
                  <div className="flex gap-2">
                    {SEVERITY_OPTIONS.map((s) => (
                      <label
                        key={s.label}
                        className="flex-1 cursor-pointer text-center text-sm font-medium rounded-full border px-3 py-2 transition-colors"
                        style={
                          form.severity === s.label
                            ? { backgroundColor: s.color, borderColor: s.color, color: '#fff' }
                            : { borderColor: 'var(--border)', color: s.color }
                        }
                      >
                        <input
                          type="radio"
                          name="severity"
                          value={s.label}
                          checked={form.severity === s.label}
                          onChange={(e) => setForm({ ...form, severity: e.target.value })}
                          className="sr-only"
                        />
                        {s.label}
                      </label>
                    ))}
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-ink mb-1.5">
                    Brief description <span className="text-muted font-normal">(optional)</span>
                  </label>
                  <textarea
                    rows={4}
                    maxLength={MAX_DESCRIPTION}
                    value={form.description}
                    onChange={(e) => setForm({ ...form, description: e.target.value })}
                    className="w-full border border-border rounded-btn px-3 py-2 text-sm bg-surface text-ink"
                  />
                  <p className="text-xs text-muted text-right mt-1">
                    {form.description.length} / {MAX_DESCRIPTION}
                  </p>
                </div>

                <button
                  type="submit"
                  className="w-full h-12 rounded-card bg-brand text-white font-semibold hover:bg-brand-light transition-colors"
                >
                  Submit Report
                </button>
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
