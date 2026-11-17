import { Droplets } from 'lucide-react'
import { useLanguage } from '../context/LanguageContext'

// Dark brand footer shown at the bottom of the citizen page
export default function Footer() {
  const { t } = useLanguage()
  return (
    <footer className="border-t border-border bg-surface py-8">
      <div className="max-w-content mx-auto px-6 text-center space-y-1">
        <p className="text-sm flex items-center justify-center gap-2 font-medium text-ink">
          <Droplets size={16} />
          NairobiFloodWatch
        </p>
        <p className="text-xs text-muted">{t('footer.tagline')}</p>
      </div>
    </footer>
  )
}
