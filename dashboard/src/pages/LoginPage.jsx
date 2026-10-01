import { Droplets, Eye, EyeOff } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

// Login page — mock authentication against hard-coded admin/officer credentials
export default function LoginPage({ onLogin }) {
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')

  function handleSubmit(e) {
    e.preventDefault()
    const role = onLogin(email, password)
    if (role === 'admin') {
      navigate('/admin')
    } else if (role === 'officer') {
      navigate('/dashboard')
    } else {
      setError('Invalid credentials')
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-100 px-4">
      <div className="bg-white rounded-xl shadow-lg w-full max-w-sm p-8">
        <div className="flex flex-col items-center mb-6">
          <div className="bg-brand text-white p-3 rounded-full mb-2">
            <Droplets size={28} />
          </div>
          <h1 className="text-xl font-bold text-brand">NairobiFloodWatch</h1>
          <p className="text-sm text-gray-500">Authority &amp; Admin Sign In</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full border rounded-lg px-3 py-2 text-sm"
              placeholder="you@flood.ke"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Password</label>
            <div className="relative">
              <input
                type={showPassword ? 'text' : 'password'}
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full border rounded-lg px-3 py-2 text-sm pr-10"
                placeholder="••••••••"
              />
              <button
                type="button"
                onClick={() => setShowPassword((v) => !v)}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400"
              >
                {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>

          {error && <p className="text-sm text-red-600 font-medium">{error}</p>}

          <button
            type="submit"
            className="w-full bg-brand hover:bg-brand-accent text-white font-semibold py-2.5 rounded-lg"
          >
            Sign In
          </button>
        </form>

        <div className="text-center mt-6">
          <Link to="/public" className="text-sm text-brand-accent hover:underline">
            Back to Public View →
          </Link>
        </div>
      </div>
    </div>
  )
}
