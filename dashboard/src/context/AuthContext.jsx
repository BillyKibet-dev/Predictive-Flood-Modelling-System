import { createContext, useContext, useState, useEffect } from 'react'
import { createAuthSession } from '../services/auth'

const AuthContext = createContext(null)

// Memory-only backend session; reload requires sign-in.
export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)

  const [session] = useState(() => createAuthSession())
  useEffect(() => session.subscribe(setUser), [session])

  return <AuthContext.Provider value={{ user, login: session.login, logout: session.logout, authorizedRequest: session.authorizedRequest }}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider')
  return ctx
}
