import { riskColor } from '../constants/colors'

// Coloured pill badge representing a flood risk level (Low/Moderate/High/Extreme)
export default function RiskBadge({ risk, size = 'md' }) {
  const sizeClasses = size === 'sm' ? 'text-xs px-2 py-0.5' : 'text-sm px-3 py-1'
  return (
    <span
      className={`inline-block rounded-full font-semibold text-white whitespace-nowrap ${sizeClasses}`}
      style={{ backgroundColor: riskColor(risk) }}
    >
      {risk}
    </span>
  )
}
