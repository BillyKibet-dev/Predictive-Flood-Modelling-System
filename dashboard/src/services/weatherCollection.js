const VERSION = 'manual-point-weather-1'
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/
function time(value) { return typeof value === 'string' && Number.isFinite(Date.parse(value)) }

export function collectionAttempt(value) {
  if (!value || !uuid.test(value.request_id) || !['REQUESTING','RECOVERY_REQUIRED','COMPLETE'].includes(value.status) ||
      !time(value.started_at) || !Number.isInteger(value.requested_count) || value.requested_count < 1 || value.requested_count > 40)
    throw new Error('Collection status could not be verified.')
  if (value.status === 'COMPLETE' && (!time(value.finished_at) || Date.parse(value.finished_at) < Date.parse(value.started_at) ||
      !Number.isInteger(value.complete_target_count) || value.complete_target_count < 0 || value.complete_target_count > value.requested_count ||
      !['COMPLETE_TARGETS','PARTIAL_TARGETS','SOURCE_UNAVAILABLE'].includes(value.outcome) || !/^[0-9a-f]{64}$/.test(value.receipt_sha256) ||
      (value.outcome === 'COMPLETE_TARGETS') !== (value.complete_target_count === value.requested_count) ||
      (value.outcome === 'SOURCE_UNAVAILABLE') !== (value.complete_target_count === 0)))
    throw new Error('Collection completion could not be verified.')
  return value
}

// Last automatic (scheduled) attempt reported by the API, or null if none has run yet.
export function automaticAttempt(value) {
  if (value === null || value === undefined) return null
  if (!time(value.started_at) || !time(value.finished_at) ||
      !['COMPLETE_TARGETS','PARTIAL_TARGETS','SOURCE_UNAVAILABLE','FAILED'].includes(value.outcome))
    throw new Error('Automatic collection status could not be verified.')
  return value
}

export function collectionStatus(value) {
  if (value?.contract_version !== VERSION || typeof value.automatic !== 'boolean' || value.automatic !== value.automation_configured ||
      (value.automatic ? !time(value.next_collection_at) : value.next_collection_at !== null) ||
      value.cooldown_seconds !== 900 || !time(value.checked_at) ||
      typeof value.automation_configured !== 'boolean' ||
      (value.automation_configured ? (!Number.isInteger(value.configured_interval_hours) || value.configured_interval_hours < 1 || value.configured_interval_hours > 24) : value.configured_interval_hours !== null) ||
      (value.latest !== null && (!time(value.next_manual_at) || Date.parse(value.next_manual_at) !== Date.parse(value.latest.started_at) + 900000)))
    throw new Error('Collection status could not be verified.')
  return {...value, latest:value.latest === null ? null : collectionAttempt(value.latest),
    latest_automatic:automaticAttempt(value.latest_automatic)}
}

export async function requestWeatherCollection(authorizedRequest, requestId) {
  if (!uuid.test(requestId)) throw new Error('A valid collection attempt is required.')
  const value = await authorizedRequest('/monitoring-areas/collection', {
    method:'POST', body:JSON.stringify({request_id:requestId}), timeoutMs:75000,
  })
  if (value?.contract_version !== VERSION || typeof value.reused !== 'boolean' || value.attempt?.request_id !== requestId || value.attempt?.status !== 'COMPLETE')
    throw new Error('Collection completion could not be verified. Check its status.')
  return {...value, attempt:collectionAttempt(value.attempt)}
}
