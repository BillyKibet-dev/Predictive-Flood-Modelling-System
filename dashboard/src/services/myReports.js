// References of reports sent from this device, so residents never have to type them.
// Stored only in this browser (never sent anywhere except to check status). Storage can be
// unavailable (private windows, blocked site data): every call then quietly does nothing.

const KEY = 'nfw.myReports.v1'
export const MAX_SAVED = 10

function read(storage) {
  try {
    const items = JSON.parse(storage?.getItem(KEY) ?? '[]')
    return Array.isArray(items) ? items.filter(i => typeof i?.reference === 'string' && typeof i.sentAt === 'string') : []
  } catch { return [] }
}

function write(storage, items) {
  try { storage?.setItem(KEY, JSON.stringify(items)) } catch { /* storage unavailable or full */ }
}

const local = () => { try { return globalThis.localStorage } catch { return null } }

export function savedReports(storage = local()) { return read(storage) }

// Newest first; one entry per reference; at most MAX_SAVED.
export function rememberReport({ reference, sentAt, condition = null, area = null }, storage = local()) {
  const items = [{ reference, sentAt, condition, area }, ...read(storage).filter(i => i.reference !== reference)].slice(0, MAX_SAVED)
  write(storage, items)
  return items
}

export function forgetReport(reference, storage = local()) {
  const items = read(storage).filter(i => i.reference !== reference)
  write(storage, items)
  return items
}
