import { createContext, useContext, useEffect, useState } from 'react'

const ThemeContext = createContext(null)

// Light/dark theme toggle — state only (no persistence), applies data-theme to <html>
export function ThemeProvider({ children }) {
  const [dark, setDark] = useState(false)

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light')
  }, [dark])

  function toggleTheme() {
    setDark((d) => !d)
  }

  return <ThemeContext.Provider value={{ dark, toggleTheme }}>{children}</ThemeContext.Provider>
}

export function useTheme() {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error('useTheme must be used within a ThemeProvider')
  return ctx
}
