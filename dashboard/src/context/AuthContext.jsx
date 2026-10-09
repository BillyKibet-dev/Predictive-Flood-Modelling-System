import { createContext, useContext, useState } from 'react'
import { MOCK_CREDENTIALS } from '../data/mockData'

const AuthContext = createContext(null)

// Provides mock authentication state (user, login, logout) to the whole app via Context API
export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)

  function login(email, password) {
    const account = MOCK_CREDENTIALS[email]
    if (account && account.password === password) {
      setUser({ name: account.name, email, role: account.role })
      return account.role
    }
    return null
  }

  function logout() {
    setUser(null)
  }

  return <AuthContext.Provider value={{ user, login, logout }}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider')
  return ctx
}
