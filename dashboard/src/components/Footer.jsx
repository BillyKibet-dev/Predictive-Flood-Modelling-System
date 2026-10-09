import { Droplets } from 'lucide-react'

// Dark brand footer shown at the bottom of the citizen page
export default function Footer() {
  return (
    <footer className="bg-brand text-white py-10">
      <div className="max-w-content mx-auto px-6 text-center space-y-1">
        <p className="text-sm flex items-center justify-center gap-2 font-medium">
          <Droplets size={16} />
          NairobiFloodWatch — XGBoost ML · Strathmore University 2026
        </p>
        <p className="text-xs text-white/60">Data: CHIRPS · Open-Meteo · TAHMO</p>
      </div>
    </footer>
  )
}
