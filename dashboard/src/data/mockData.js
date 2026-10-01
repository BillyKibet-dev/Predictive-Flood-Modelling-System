// Central mock data store — simulates the backend API responses for NairobiFloodWatch

export const ZONES = [
  {
    id: 'mathare',
    name: 'Mathare River',
    risk: 'Extreme',
    riskClass: 3,
    waterLevel: 3.2,
    rainfall6h: 68,
    confidence: 0.94,
    lat: -1.260,
    lon: 36.860,
    lastUpdated: '14:00 EAT',
  },
  {
    id: 'ngong',
    name: 'Ngong River',
    risk: 'High',
    riskClass: 2,
    waterLevel: 2.1,
    rainfall6h: 44,
    confidence: 0.81,
    lat: -1.317,
    lon: 36.783,
    lastUpdated: '14:00 EAT',
  },
  {
    id: 'nairobi_river',
    name: 'Nairobi River',
    risk: 'Moderate',
    riskClass: 1,
    waterLevel: 1.2,
    rainfall6h: 22,
    confidence: 0.72,
    lat: -1.283,
    lon: 36.822,
    lastUpdated: '14:00 EAT',
  },
]

export const ALERTS = [
  {
    id: 1,
    zone: 'Mathare River',
    risk: 'Extreme',
    timestamp: '14:00 EAT — 08 Jul 2026',
    acknowledged: false,
    acknowledgedBy: null,
  },
  {
    id: 2,
    zone: 'Ngong River',
    risk: 'High',
    timestamp: '13:00 EAT — 08 Jul 2026',
    acknowledged: false,
    acknowledgedBy: null,
  },
  {
    id: 3,
    zone: 'Mathare River',
    risk: 'High',
    timestamp: '08:00 EAT — 07 Jul 2026',
    acknowledged: true,
    acknowledgedBy: 'Billy Kibet',
  },
  {
    id: 4,
    zone: 'Nairobi River',
    risk: 'Moderate',
    timestamp: '06:00 EAT — 07 Jul 2026',
    acknowledged: true,
    acknowledgedBy: 'Billy Kibet',
  },
]

export const USERS = [
  {
    id: 1,
    name: 'Billy Kibet',
    email: 'billy.kibet@strathmore.edu',
    role: 'admin',
    status: 'Active',
  },
  {
    id: 2,
    name: 'Jane Mwangi',
    email: 'j.mwangi@nairobicouncil.go.ke',
    role: 'officer',
    status: 'Active',
  },
  {
    id: 3,
    name: 'David Otieno',
    email: 'd.otieno@redcross.or.ke',
    role: 'officer',
    status: 'Inactive',
  },
]

export const CITIZEN_REPORTS = [
  {
    id: 1,
    zone: 'Mathare River',
    condition: 'Street flooding',
    severity: 'Dangerous',
    timestamp: '13:45 EAT — 08 Jul 2026',
    description: 'Water is knee-deep on Juja Road near the bridge',
  },
  {
    id: 2,
    zone: 'Ngong River',
    condition: 'River overflow',
    severity: 'Serious',
    timestamp: '12:30 EAT — 08 Jul 2026',
    description: 'Langata Road completely submerged near junction',
  },
]

// Mock credential map used by the login page
export const MOCK_CREDENTIALS = {
  'admin@flood.ke': { password: 'admin123', role: 'admin', name: 'Billy Kibet' },
  'officer@flood.ke': { password: 'officer123', role: 'officer', name: 'Jane Mwangi' },
}

export const PIPELINE_LOG = [
  { id: 1, timestamp: '14:00 EAT — 08 Jul 2026', stage: 'Ingest', status: 'Success', duration: '4.2s' },
  { id: 2, timestamp: '14:00 EAT — 08 Jul 2026', stage: 'Preprocess', status: 'Success', duration: '2.8s' },
  { id: 3, timestamp: '14:00 EAT — 08 Jul 2026', stage: 'Inference', status: 'Success', duration: '1.1s' },
  { id: 4, timestamp: '14:00 EAT — 08 Jul 2026', stage: 'Alerts', status: 'Success', duration: '0.6s' },
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
