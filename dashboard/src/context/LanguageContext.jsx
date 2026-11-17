import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { LANGUAGES, translate } from '../i18n/strings'

const LanguageContext = createContext(null)
const KEY = 'nfw-language'

function initial() {
  try {
    const saved = localStorage.getItem(KEY)
    if (LANGUAGES.some(l => l.code === saved)) return saved
  } catch { /* storage blocked: fall back to the browser language */ }
  return navigator.language?.toLowerCase().startsWith('sw') ? 'sw' : 'en'
}

// English or Kiswahili for the public pages, remembered on this device.
export function LanguageProvider({ children }) {
  const [lang, setLangState] = useState(initial)
  useEffect(() => { document.documentElement.lang = lang }, [lang])
  const setLang = useCallback(code => {
    setLangState(code)
    try { localStorage.setItem(KEY, code) } catch { /* not remembered; still switches */ }
  }, [])
  const t = useCallback((key, values) => translate(lang, key, values), [lang])
  const value = useMemo(() => ({ lang, setLang, t }), [lang, setLang, t])
  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>
}

export function useLanguage() {
  const ctx = useContext(LanguageContext)
  // Components rendered outside the provider (tests) fall back to English.
  return ctx ?? { lang: 'en', setLang: () => {}, t: (key, values) => translate('en', key, values) }
}

// Dates and times in the reader's language, always Nairobi time.
export function formatNairobi(lang, value, options) {
  return new Intl.DateTimeFormat(lang === 'sw' ? 'sw-KE' : 'en-KE', { timeZone: 'Africa/Nairobi', ...options }).format(new Date(value))
}
