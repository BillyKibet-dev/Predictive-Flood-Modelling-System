// Shared colour system & lookup helpers for flood risk levels

export const RISK_COLORS = {
  Low: '#22c55e',
  Moderate: '#eab308',
  High: '#f59e0b',
  Extreme: '#ef4444',
}

export const RISK_BG_LIGHT = {
  Low: '#dcfce7',
  Moderate: '#fef9c3',
  High: '#ffedd5',
  Extreme: '#fee2e2',
}

export const BRAND = {
  primary: '#1F4E79',
  accent: '#2E75B6',
}

export const RISK_RADIUS = {
  Low: 16,
  Moderate: 18,
  High: 20,
  Extreme: 22,
}

export const RISK_ORDER = ['Low', 'Moderate', 'High', 'Extreme']

export const RISK_ACTION_MESSAGES = {
  Extreme: 'Water rising rapidly. Evacuate low-lying areas.',
  High: 'Water levels elevated. Monitor closely.',
  Moderate: 'Elevated but stable. Stay alert.',
  Low: 'Conditions normal. No action needed.',
}

export function riskColor(risk) {
  return RISK_COLORS[risk] || '#6b7280'
}

export function riskBgLight(risk) {
  return RISK_BG_LIGHT[risk] || '#f3f4f6'
}
