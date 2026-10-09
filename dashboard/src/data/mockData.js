// Central mock data store — simulates the backend API responses for NairobiFloodWatch
// Covers the entire Nairobi County, organised into flood risk zones (not individual sensors).

export const LAST_UPDATED = '14:00 EAT — 08 Jul 2026'

export const ZONES = [
  { id: 'mathare', name: 'Mathare', subCounty: 'Starehe', risk: 'Extreme', riskClass: 3, rainfall24h: 68, confidence: 0.94, lat: -1.260, lon: 36.860 },
  { id: 'kibera', name: 'Kibera', subCounty: 'Langata', risk: 'High', riskClass: 2, rainfall24h: 44, confidence: 0.81, lat: -1.314, lon: 36.784 },
  { id: 'westlands', name: 'Westlands', subCounty: 'Westlands', risk: 'Moderate', riskClass: 1, rainfall24h: 22, confidence: 0.72, lat: -1.264, lon: 36.807 },
  { id: 'cbd', name: 'CBD', subCounty: 'Kamuthe', risk: 'Low', riskClass: 0, rainfall24h: 8, confidence: 0.88, lat: -1.286, lon: 36.817 },
  { id: 'kasarani', name: 'Kasarani', subCounty: 'Kasarani', risk: 'Moderate', riskClass: 1, rainfall24h: 18, confidence: 0.76, lat: -1.221, lon: 36.897 },
  { id: 'embakasi', name: 'Embakasi', subCounty: 'Embakasi East', risk: 'High', riskClass: 2, rainfall24h: 38, confidence: 0.79, lat: -1.320, lon: 36.895 },
  { id: 'dagoretti', name: 'Dagoretti', subCounty: 'Dagoretti North', risk: 'Low', riskClass: 0, rainfall24h: 5, confidence: 0.91, lat: -1.295, lon: 36.754 },
  { id: 'ruaraka', name: 'Ruaraka', subCounty: 'Ruaraka', risk: 'Moderate', riskClass: 1, rainfall24h: 20, confidence: 0.74, lat: -1.241, lon: 36.876 },
]

export const ALERTS = [
  { id: 1, zone: 'Mathare', subCounty: 'Starehe', risk: 'Extreme', timestamp: '14:00 EAT — 08 Jul 2026', acknowledged: false, acknowledgedBy: null },
  { id: 2, zone: 'Kibera', subCounty: 'Langata', risk: 'High', timestamp: '13:00 EAT — 08 Jul 2026', acknowledged: false, acknowledgedBy: null },
  { id: 3, zone: 'Embakasi', subCounty: 'Embakasi East', risk: 'High', timestamp: '08:00 EAT — 07 Jul 2026', acknowledged: true, acknowledgedBy: 'Jane Mwangi' },
  { id: 4, zone: 'Westlands', subCounty: 'Westlands', risk: 'Moderate', timestamp: '06:00 EAT — 07 Jul 2026', acknowledged: true, acknowledgedBy: 'Jane Mwangi' },
]

export const USERS = [
  { id: 1, name: 'Billy Kibet', email: 'billy.kibet@strathmore.edu', role: 'admin', status: 'Active' },
  { id: 2, name: 'Jane Mwangi', email: 'j.mwangi@nairobicouncil.go.ke', role: 'officer', status: 'Active' },
  { id: 3, name: 'David Otieno', email: 'd.otieno@redcross.or.ke', role: 'officer', status: 'Inactive' },
]

export const CITIZEN_REPORTS = [
  { id: 1, zone: 'Mathare', condition: 'Street flooding', severity: 'Dangerous', timestamp: '13:45 EAT — 08 Jul 2026', description: 'Water is knee-deep on Juja Road near the bridge' },
  { id: 2, zone: 'Kibera', condition: 'River overflow', severity: 'Serious', timestamp: '12:30 EAT — 08 Jul 2026', description: 'Langata Road completely submerged near junction' },
]

// Mock credential map used by the login page
export const MOCK_CREDENTIALS = {
  'admin@flood.ke': { password: 'admin123', role: 'admin', name: 'Billy Kibet' },
  'officer@flood.ke': { password: 'officer123', role: 'officer', name: 'Jane Mwangi' },
}

export const PIPELINE_LOG = [
  { id: 1, timestamp: '14:00 EAT — 08 Jul 2026', stage: 'Fetch data', status: 'Success', duration: '4.2s' },
  { id: 2, timestamp: '14:00 EAT — 08 Jul 2026', stage: 'Preprocess', status: 'Success', duration: '2.8s' },
  { id: 3, timestamp: '14:00 EAT — 08 Jul 2026', stage: 'Inference', status: 'Success', duration: '1.1s' },
  { id: 4, timestamp: '14:00 EAT — 08 Jul 2026', stage: 'Alert check', status: 'Success', duration: '0.6s' },
]

export const MODEL_METRICS = [
  { label: 'Weighted Recall', value: 0.7880, ok: false },
  { label: 'Weighted F1', value: 0.7790, ok: false },
  { label: 'AUC-ROC', value: 0.8732, ok: true },
  { label: 'Extreme Precision', value: 1.0000, ok: true },
  { label: 'Low Recall', value: 0.9375, ok: true },
  { label: 'Moderate Recall', value: 0.3889, ok: false },
  { label: 'High Recall', value: 0.5000, ok: false },
  { label: 'Extreme Recall', value: 0.4516, ok: false },
]

export const PER_CLASS_RECALL = [
  { name: 'Low', recall: 0.9375 },
  { name: 'Moderate', recall: 0.3889 },
  { name: 'High', recall: 0.5000 },
  { name: 'Extreme', recall: 0.4516 },
]
