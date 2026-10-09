import { getRisk } from '../constants/colors'

// Coloured pill badge representing a flood risk level — colour paired with text, never colour alone
export default function RiskBadge({ risk, size = 'md' }) {
  const { bg, text, border } = getRisk(risk)
  const sizeClasses = size === 'sm' ? 'text-xs px-2 py-0.5' : 'text-sm px-2.5 py-1'
  return (
    <span
      className={`inline-block rounded-badge font-semibold border whitespace-nowrap ${sizeClasses}`}
      style={{ backgroundColor: bg, color: text, borderColor: border }}
    >
      {risk}
    </span>
  )
}
