import { Droplets } from 'lucide-react'

// Simple footer for the public citizens page
export default function Footer() {
  return (
    <footer className="bg-white border-t mt-8">
      <div className="max-w-6xl mx-auto px-4 py-6 text-center space-y-2">
        <p className="text-gray-600 text-sm flex items-center justify-center gap-1">
          <Droplets size={16} className="text-brand" />
          NairobiFloodWatch — Powered by XGBoost ML · Strathmore University Capstone Project 2026
        </p>
        <p className="text-green-700 font-medium text-sm">
          ⚠ Never attempt to cross flooded roads. Turn around — don&apos;t drown.
        </p>
      </div>
    </footer>
  )
}
