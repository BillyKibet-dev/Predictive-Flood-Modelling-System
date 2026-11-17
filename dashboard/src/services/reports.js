import { API_BASE_URL } from './api.js'

export const REPORT_CONDITIONS = ['Street flooding', 'River overflow', 'Blocked drainage', 'Other']
export const REPORT_SEVERITIES = ['Mild', 'Serious', 'Dangerous']
export const MAX_DESCRIPTION_LENGTH = 200

const FIELD_MESSAGES = {
  zone_id: 'Choose one of the available zones.',
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

export function validateCitizenReport(form, availableZoneIds) {
  const errors = {}
  if (!availableZoneIds.includes(form.zone_id)) errors.zone_id = FIELD_MESSAGES.zone_id
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
      zone_id: form.zone_id.trim(),
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
      throw new ReportSubmissionError('That zone is no longer available. Refresh the warnings and choose a zone.', {
        zone_id: FIELD_MESSAGES.zone_id,
      })
    }
    if (response.status === 422) {
      const error = await response.json().catch(() => ({}))
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
    if (!Number.isInteger(report.id) || report.id < 1 || report.zone_id !== payload.zone_id || !Number.isFinite(Date.parse(report.timestamp))) {
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


export async function fetchReportingZones({ signal } = {}) {
  const response = await fetch(`${API_BASE_URL}/reporting-zones`, { signal, cache:'no-store' })
  if (!response.ok) throw new Error('Reporting zones could not be loaded. Please retry.')
  const zones = await response.json()
  if (!Array.isArray(zones) || zones.some(zone => typeof zone.id !== 'string' || typeof zone.name !== 'string')) throw new Error('Invalid reporting zones')
  return zones
}
