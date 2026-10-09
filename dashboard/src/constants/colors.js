// Shared colour system & lookup helpers for flood risk levels

export const RISK_COLORS = {
  Low: '#16A34A',
  Moderate: '#CA8A04',
  High: '#EA580C',
  Extreme: '#DC2626',
}

export const RISK_RADIUS = {
  Low: 20,
  Moderate: 22,
  High: 25,
  Extreme: 28,
}

export const RISK_OPACITY = {
  Low: 0.5,
  Moderate: 0.5,
  High: 0.6,
  Extreme: 0.7,
}

export const RISK_ORDER = ['Low', 'Moderate', 'High', 'Extreme']

export const RISK_ACTION_MESSAGES = {
  Extreme: 'Evacuate low-lying areas immediately.',
  High: 'Avoid flood-prone roads and drainage areas.',
  Moderate: 'Monitor conditions. Stay alert.',
  Low: 'Conditions normal.',
}

// Risk colour tokens — bg/text/border read from CSS variables so dark mode applies automatically
export const getRisk = (level) =>
  ({
    Low: { bg: 'var(--risk-low-bg)', text: 'var(--risk-low)', border: '#86EFAC' },
    Moderate: { bg: 'var(--risk-mod-bg)', text: 'var(--risk-mod)', border: '#FDE047' },
    High: { bg: 'var(--risk-high-bg)', text: 'var(--risk-high)', border: '#FDBA74' },
    Extreme: { bg: 'var(--risk-extreme-bg)', text: 'var(--risk-extreme)', border: '#FCA5A5' },
  }[level] || {})

export function riskColor(risk) {
  return RISK_COLORS[risk] || '#6b7280'
}
