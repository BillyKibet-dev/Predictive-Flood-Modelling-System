import { API_BASE_URL } from './api.js'

export const REPORT_CONDITIONS = ['Street flooding', 'River overflow', 'Blocked drainage', 'Other']
export const REPORT_SEVERITIES = ['Mild', 'Serious', 'Dangerous']
export const MAX_DESCRIPTION_LENGTH = 200

const FIELD_MESSAGES = {
  zone_id: 'Choose one of the available zones.',
  observed_condition: 'Choose an observed condition.',
  perceived_severity: 'Choose a severity.',
  description: `Use ${MAX_DESCRIPTION_LENGTH} characters or fewer.`,
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
    return report
  } catch (error) {
    if (error instanceof ReportSubmissionError) throw error
    throw new ReportSubmissionError(UNCONFIRMED_MESSAGE)
  } finally {
    clearTimeout(timer)
    signal?.removeEventListener('abort', abort)
  }
}
