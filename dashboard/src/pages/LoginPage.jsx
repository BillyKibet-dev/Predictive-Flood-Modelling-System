import { Check, Droplets, Eye, EyeOff, Loader2 } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

const FEATURES = [
  'XGBoost ML model with AUC-ROC 0.8732',
  'Eight monitored zones across Nairobi County',
  'Automated alerts for High and Extreme risk',
]

// Login page — split layout; mock authentication against hard-coded admin/officer credentials
export default function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setLoading(true)
    setTimeout(() => {
      const role = login(email, password)
      setLoading(false)
      if (role === 'admin') navigate('/admin')
      else if (role === 'officer') navigate('/officer')
      else setError('Invalid credentials. Please try again.')
    }, 500)
  }

  return (
    <div className="min-h-screen grid grid-cols-1 md:grid-cols-2 page-transition">
      {/* Left — brand panel */}
      <div
        className="hidden md:flex flex-col justify-center px-16 text-white"
        style={{ background: 'linear-gradient(135deg, #0F2D5C 0%, #1E4080 100%)' }}
      >
        <div className="max-w-sm space-y-8">
          <div className="flex items-center gap-2 font-semibold text-lg">
            <Droplets size={24} />
            NairobiFloodWatch
          </div>
          <h2 className="text-3xl font-bold tracking-tight">
            Real-time flood prediction for Nairobi County
          </h2>
          <ul className="space-y-6">
            {FEATURES.map((f) => (
              <li key={f} className="flex items-center gap-3">
                <span className="w-6 h-6 rounded-full bg-white/15 flex items-center justify-center shrink-0">
                  <Check size={14} />
                </span>
                <span className="text-sm text-white/90">{f}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* Right — form */}
      <div className="flex items-center justify-center px-6 bg-surface">
        <div className="w-full max-w-[400px] space-y-8">
          <div>
            <h2 className="text-2xl font-semibold tracking-tight text-ink">Sign in to your account</h2>
            <p className="text-muted mt-1">Access the officer dashboard and alerts</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-8">
            <div className="space-y-2">
              <label className="block text-sm font-medium text-ink">Email</label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                aria-label="Email"
                className={`w-full h-10 px-3 rounded-btn border text-sm bg-surface text-ink ${
                  error ? 'border-risk-extreme' : 'border-border'
                }`}
                placeholder="you@flood.ke"
              />
            </div>

            <div className="space-y-2">
              <label className="block text-sm font-medium text-ink">Password</label>
              <div className="relative">
                <input
                  type={showPassword ? 'text' : 'password'}
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  aria-label="Password"
                  className={`w-full h-10 px-3 pr-10 rounded-btn border text-sm bg-surface text-ink ${
                    error ? 'border-risk-extreme' : 'border-border'
                  }`}
                  placeholder="••••••••"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted"
                >
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
              {error && <p className="text-sm text-risk-extreme">{error}</p>}
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full h-12 rounded-card bg-brand text-white font-semibold flex items-center justify-center gap-2 hover:bg-brand-light transition-colors disabled:opacity-70"
            >
              {loading ? (
                <>
                  <Loader2 size={18} className="animate-spin" /> Signing in...
                </>
              ) : (
                'Sign In'
              )}
            </button>
          </form>

          <Link to="/" className="block text-center text-sm text-brand hover:underline">
            ← Back to Map
          </Link>
        </div>
      </div>
    </div>
  )
}
