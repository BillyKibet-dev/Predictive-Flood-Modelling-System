import { Droplets, Phone } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import Footer from '../components/Footer'
import ZoneCard from '../components/ZoneCard'

const ZONE_OPTIONS = ['Mathare River', 'Ngong River', 'Nairobi River', 'Other']
const CONDITION_OPTIONS = ['Street flooding', 'River overflow', 'Blocked drainage', 'Other']
const SEVERITY_OPTIONS = ['Mild', 'Serious', 'Dangerous']
const MAX_DESCRIPTION = 200

// Public citizens page — flood warnings + anonymous flood condition reporting (no login required)
export default function PublicPage({ zones, showToast }) {
  const activeWarningZones = zones.filter((z) => z.risk === 'High' || z.risk === 'Extreme')

  const [form, setForm] = useState({
    zone: ZONE_OPTIONS[0],
    condition: CONDITION_OPTIONS[0],
    severity: SEVERITY_OPTIONS[0],
    description: '',
  })
  const [submitted, setSubmitted] = useState(false)

  function handleSubmit(e) {
    e.preventDefault()
    setSubmitted(true)
    showToast?.('Report submitted. Thank you.', 'success')
    setTimeout(() => {
      setSubmitted(false)
      setForm({ zone: ZONE_OPTIONS[0], condition: CONDITION_OPTIONS[0], severity: SEVERITY_OPTIONS[0], description: '' })
    }, 2500)
  }

  return (
    <div className="min-h-screen flex flex-col">
      {/* Top navigation */}
      <nav className="bg-white shadow px-4 sm:px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-2 font-bold text-brand text-lg">
          <Droplets size={22} />
          NairobiFloodWatch
        </div>
        <div className="flex items-center gap-3">
          <span className="hidden sm:inline text-xs text-gray-400">Public access — no login required</span>
          <Link
            to="/login"
            className="bg-brand-accent hover:bg-brand text-white text-sm font-medium px-4 py-2 rounded-lg"
          >
            Login →
          </Link>
        </div>
      </nav>

      {/* Active warning banner */}
      {activeWarningZones.length > 0 && (
        <div className="bg-red-500 text-white text-center py-3 px-4 font-semibold">
          🔴 ACTIVE FLOOD WARNING — NAIROBI COUNTY —{' '}
          {activeWarningZones.map((z) => z.name).join(', ')}
        </div>
      )}

      <main className="flex-1 max-w-6xl w-full mx-auto px-4 py-6 grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* LEFT COLUMN — Current Warnings (60%) */}
        <section className="lg:col-span-3 space-y-4">
          <div>
            <h2 className="text-xl font-bold text-gray-800">Current Flood Warnings</h2>
            <p className="text-sm text-gray-500">Updated every hour automatically.</p>
          </div>

          <div className="space-y-4">
            {zones.map((zone) => (
              <ZoneCard key={zone.id} zone={zone} variant="public" />
            ))}
          </div>

          {/* Emergency contacts */}
          <div className="bg-white rounded-lg shadow p-4">
            <h3 className="font-bold text-gray-800 mb-2 flex items-center gap-2">
              <Phone size={16} className="text-brand" /> Emergency Contacts
            </h3>
            <ul className="text-sm text-gray-700 space-y-1">
              <li>Kenya Red Cross: <span className="font-semibold">0800 723 253</span> (toll free)</li>
              <li>Nairobi County NDMA: <span className="font-semibold">020 222 2222</span></li>
              <li>Emergency Services: <span className="font-semibold">999 / 112</span></li>
            </ul>
          </div>
        </section>

        {/* RIGHT COLUMN — Report a Flood Condition (40%) */}
        <section className="lg:col-span-2">
          <div className="bg-white rounded-lg shadow p-5">
            <h2 className="text-xl font-bold text-gray-800">Report a Flood Condition</h2>
            <p className="text-sm text-gray-500 mb-4">Help improve predictions. No account required.</p>

            {submitted ? (
              <div className="bg-green-100 text-green-800 rounded-lg p-4 font-medium">
                ✅ Report submitted. Thank you.
              </div>
            ) : (
              <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Zone</label>
                  <select
                    value={form.zone}
                    onChange={(e) => setForm({ ...form, zone: e.target.value })}
                    className="w-full border rounded-lg px-3 py-2 text-sm"
                  >
                    {ZONE_OPTIONS.map((z) => (
                      <option key={z} value={z}>
                        {z}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">What do you observe?</label>
                  <div className="space-y-1">
                    {CONDITION_OPTIONS.map((c) => (
                      <label key={c} className="flex items-center gap-2 text-sm text-gray-700">
                        <input
                          type="radio"
                          name="condition"
                          value={c}
                          checked={form.condition === c}
                          onChange={(e) => setForm({ ...form, condition: e.target.value })}
                        />
                        {c}
                      </label>
                    ))}
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">How severe?</label>
                  <div className="space-y-1">
                    {SEVERITY_OPTIONS.map((s) => (
                      <label
                        key={s}
                        className={`flex items-center gap-2 text-sm ${s === 'Dangerous' ? 'text-red-600 font-semibold' : 'text-gray-700'}`}
                      >
                        <input
                          type="radio"
                          name="severity"
                          value={s}
                          checked={form.severity === s}
                          onChange={(e) => setForm({ ...form, severity: e.target.value })}
                        />
                        {s}
                      </label>
                    ))}
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Brief description <span className="text-gray-400 font-normal">(optional)</span>
                  </label>
                  <textarea
                    maxLength={MAX_DESCRIPTION}
                    value={form.description}
                    onChange={(e) => setForm({ ...form, description: e.target.value })}
                    rows={3}
                    className="w-full border rounded-lg px-3 py-2 text-sm"
                    placeholder="e.g. Water is knee-deep near the bridge"
                  />
                  <p className="text-xs text-gray-400 text-right">
                    {form.description.length}/{MAX_DESCRIPTION}
                  </p>
                </div>

                <button
                  type="submit"
                  className="w-full bg-brand hover:bg-brand-accent text-white font-semibold py-3 rounded-lg"
                >
                  Submit Report
                </button>

                <p className="text-xs text-gray-400 text-center">
                  Reports are anonymous. No personal data is collected.
                </p>
              </form>
            )}
          </div>
        </section>
      </main>

      <Footer />
    </div>
  )
}
