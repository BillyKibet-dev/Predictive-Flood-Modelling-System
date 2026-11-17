import { API_BASE_URL } from './api.js'

export const REPORT_CONDITIONS = ['Street flooding', 'River overflow', 'Blocked drainage', 'Other']
export const REPORT_SEVERITIES = ['Mild', 'Serious', 'Dangerous']
export const MAX_DESCRIPTION_LENGTH = 200

const FIELD_MESSAGES = {
  area_id: 'Choose your sub-county.',
  observed_condition: 'Choose an observed condition.',
  perceived_severity: 'Choose a severity.',
  description: `Use ${MAX_DESCRIPTION_LENGTH} characters or fewer.`,
  location_description: 'Describe a landmark, road or address (up to 250 characters).',
  latitude: 'Supply both coordinates within valid latitude/longitude ranges.',
  longitude: 'Supply both coordinates within valid latitude/longitude ranges.',

}
const UNCONFIRMED_MESSAGE = 'We could not confirm whether your report was received. Your entries are still here. Check your connection before trying again.'

export class ReportSubmissionError extends Error {
  constructor(message, fieldErrors = {}) {
    super(message)
    this.name = 'ReportSubmissionError'
    this.fieldErrors = fieldErrors
  }
}

export function validateCitizenReport(form, availableAreaIds) {
  const errors = {}
  if (!availableAreaIds.includes(form.area_id)) errors.area_id = FIELD_MESSAGES.area_id
  if (!REPORT_CONDITIONS.includes(form.observed_condition)) errors.observed_condition = FIELD_MESSAGES.observed_condition
  if (!REPORT_SEVERITIES.includes(form.perceived_severity)) errors.perceived_severity = FIELD_MESSAGES.perceived_severity
  if (typeof form.description !== 'string' || form.description.length > MAX_DESCRIPTION_LENGTH) {
    errors.description = FIELD_MESSAGES.description
  }
  if ('location_description' in form && (typeof form.location_description !== 'string' || !form.location_description.trim() || form.location_description.length > 250)) errors.location_description = FIELD_MESSAGES.location_description
  const lat = form.latitude === '' || form.latitude == null ? null : Number(form.latitude)
  const lon = form.longitude === '' || form.longitude == null ? null : Number(form.longitude)
  if ((lat === null) !== (lon === null) || (lat !== null && (!Number.isFinite(lat) || Math.abs(lat) > 90)) || (lon !== null && (!Number.isFinite(lon) || Math.abs(lon) > 180))) {
    errors.latitude = FIELD_MESSAGES.latitude; errors.longitude = FIELD_MESSAGES.longitude
  }
  return errors
}

// A POST is never retried automatically: a lost response can follow a successful save.
export async function submitCitizenReport(form, { signal, timeoutMs = 15_000 } = {}) {
  const controller = new AbortController()
  const abort = () => controller.abort()
  signal?.addEventListener('abort', abort, { once: true })
  if (signal?.aborted) abort()
  const timer = setTimeout(abort, timeoutMs)

  try {
    const payload = {
      area_id: form.area_id.trim(),
      observed_condition: form.observed_condition,
      perceived_severity: form.perceived_severity,
      description: form.description.trim() || null,
      ...('location_description' in form ? { location_description:form.location_description.trim() || null } : {}),
      ...(form.latitude !== '' && form.latitude != null && form.longitude !== '' && form.longitude != null ? {
        latitude:Number(form.latitude), longitude:Number(form.longitude),
        ...(form.location_accuracy_m != null && form.location_accuracy_m !== '' ? { location_accuracy_m:Number(form.location_accuracy_m) } : {})
      } : {}),
    }
    const response = await fetch(`${API_BASE_URL}/citizen-report`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload), signal: controller.signal,
    })

    if (response.status === 404) {
      throw new ReportSubmissionError('That sub-county is not available. Refresh the page and choose again.', {
        area_id: FIELD_MESSAGES.area_id,
      })
    }
    if (response.status === 422) {
      const error = await response.json().catch(() => ({}))
      // A plain message is the server explaining a pin/sub-county mismatch in words.
      if (typeof error.detail === 'string') throw new ReportSubmissionError(error.detail, { area_id: error.detail })
      const fields = {}
      for (const issue of Array.isArray(error.detail) ? error.detail : []) {
        const field = issue.loc?.[1]
        if (FIELD_MESSAGES[field]) fields[field] = FIELD_MESSAGES[field]
      }
      throw new ReportSubmissionError('Please check the report details and try again.', fields)
    }
    if (response.status !== 201) {
      throw new ReportSubmissionError('We could not confirm your report. Your entries are still here. Please try again.')
    }

    const report = await response.json()
    if (!Number.isInteger(report.id) || report.id < 1 || report.area_id !== payload.area_id || !Number.isFinite(Date.parse(report.timestamp))) {
      throw new Error('Missing report confirmation')
    }
    if ('location_description' in payload && report.location_description !== payload.location_description) throw new Error('Location save not confirmed')
    if ('latitude' in payload && (report.latitude !== payload.latitude || report.longitude !== payload.longitude)) throw new Error('Coordinate save not confirmed')
    return report
  } catch (error) {
    if (error instanceof ReportSubmissionError) throw error
    throw new ReportSubmissionError(UNCONFIRMED_MESSAGE)
  } finally {
    clearTimeout(timer)
    signal?.removeEventListener('abort', abort)
  }
}


// The 17 Nairobi sub-counties (the outlines on the map).
export async function fetchReportingAreas({ signal } = {}) {
  const response = await fetch(`${API_BASE_URL}/reporting-areas`, { signal })
  if (!response.ok) throw new Error('Sub-counties could not be loaded. Please retry.')
  const areas = await response.json()
  if (!Array.isArray(areas) || !areas.length || areas.some(area => typeof area.id !== 'string' || typeof area.name !== 'string')) throw new Error('Invalid sub-county list')
  return areas
}

// Sub-county containing a pin (null outside Nairobi). Sent in the body so it is never logged.
export async function locateReportingArea(latitude, longitude, { signal } = {}) {
  const response = await fetch(`${API_BASE_URL}/reporting-areas/locate`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, signal,
    body: JSON.stringify({ latitude: Number(latitude), longitude: Number(longitude) }),
  })
  if (!response.ok) throw new Error('Sub-county could not be checked')
  const area = await response.json()
  if (area !== null && (typeof area?.id !== 'string' || typeof area?.name !== 'string')) throw new Error('Invalid sub-county')
  return area
}

export const MAX_PHOTO_BYTES = 8 * 1024 * 1024
export const PHOTO_TYPES = ['image/jpeg', 'image/png', 'image/webp']

// One photo for a report just sent. The server strips location and camera data.
export async function uploadReportPhoto(reference, code, file, { signal } = {}) {
  if (!PHOTO_TYPES.includes(file?.type)) throw new Error('Use a JPEG, PNG or WebP photo.')
  if (file.size > MAX_PHOTO_BYTES) throw new Error('The photo is larger than 8 MB.')
  const body = new FormData()
  body.append('code', code)
  body.append('photo', file)
  const response = await fetch(`${API_BASE_URL}/citizen-report/${encodeURIComponent(reference)}/photo`, { method: 'POST', body, signal })
  const result = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'The photo could not be added.')
  if (result.reference !== reference || result.photo_attached !== true) throw new Error('The photo could not be confirmed.')
  return result
}

// What happened to my report? The code goes in the body, never the address bar.
export async function checkReportStatus(reference, code, { signal } = {}) {
  const number = Number(String(reference).replace(/^#/, '').trim())
  if (!Number.isInteger(number) || number < 1) throw new Error('Enter the reference number, for example 42.')
  const clean = String(code).trim()
  if (clean.replace(/[\s-]/g, '').length !== 8) throw new Error('Enter the 8-character code, for example K7Q2-M9XD.')
  const response = await fetch(`${API_BASE_URL}/citizen-report/status`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, signal, body: JSON.stringify({ reference: number, code: clean }),
  })
  const result = await response.json().catch(() => ({}))
  if (response.status === 404) throw new Error(result.detail || 'That reference and code do not match a report.')
  if (!response.ok || result.reference !== number || typeof result.status_text !== 'string') throw new Error('Status could not be checked. Please try again.')
  return result
}
