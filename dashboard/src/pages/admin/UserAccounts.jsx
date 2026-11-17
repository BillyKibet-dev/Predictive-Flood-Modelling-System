import { useState } from 'react'
import { useAuth } from '../../context/AuthContext'
import useStaffList from '../../hooks/useStaffList'
import { Search, UserPlus } from 'lucide-react'
import { PageHeader, buttonClass, primaryButtonClass } from '../../components/StaffLayout'

const initial = { name: '', email: '', role: 'officer', status: 'Active', password: '' }
const input = 'mt-1 w-full h-9 border border-border rounded-btn bg-surface text-ink px-2.5 text-sm'
export default function UserAccounts() {
  const { user: actor, authorizedRequest } = useAuth()
  const list = useStaffList('/admin/users')
  const [search, setSearch] = useState(''),
    [editing, setEditing] = useState(undefined),
    [form, setForm] = useState(initial),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [notice, setNotice] = useState('')
  function open(user = null) {
    setEditing(user)
    setForm(
      user
        ? { name: user.name, email: user.email, role: user.role, status: user.status, password: '' }
        : initial
    )
    setError('')
  }
  async function save(event) {
    event.preventDefault()
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const payload = {
        name: form.name.trim(),
        email: form.email.trim(),
        role: form.role,
        ...(editing ? { status: form.status } : {}),
      }
      if (form.password) payload.password = form.password
      if (!editing && !form.password) throw new Error('A password is required for a new account.')
      const saved = await authorizedRequest(
        editing ? `/admin/users/${editing.id}` : '/admin/users',
        { method: editing ? 'PUT' : 'POST', body: JSON.stringify(payload) }
      )
      if (!Number.isInteger(saved.id) || saved.email.toLowerCase() !== payload.email.toLowerCase())
        throw new Error('Save not confirmed. Refresh the accounts before retrying.')
      setForm(initial)
      setEditing(undefined)
      setNotice('Account saved.')
      list.refresh()
    } catch (failure) {
      setError(
        failure.name === 'AbortError'
          ? 'Save not confirmed. Refresh accounts before retrying.'
          : failure.message
      )
    } finally {
      setBusy(false)
    }
  }
  async function remove(account) {
    if (
      !window.confirm(
        `Permanently remove ${account.name}? Accounts with review/alert history must be deactivated instead.`
      )
    )
      return
    setBusy(true)
    setError('')
    setNotice('')
    try {
      await authorizedRequest(`/admin/users/${account.id}`, { method: 'DELETE' })
      setNotice('Account removed.')
      list.refresh()
    } catch (failure) {
      setError(failure.message)
    } finally {
      setBusy(false)
    }
  }
  const rows = (list.data ?? []).filter((account) =>
    `${account.name} ${account.email}`.toLowerCase().includes(search.toLowerCase())
  )
  const initials = name => name.split(/\s+/).map(w => w[0]).join('').slice(0, 2).toUpperCase()
  return (
    <section className="text-ink">
      <PageHeader title="Users" description="Who can sign in. Deactivate an account to remove access but keep its review history.">
        <button className={buttonClass} onClick={list.refresh}>Refresh accounts</button>
        <button className={primaryButtonClass} onClick={() => open()}><UserPlus size={15} />Add user</button>
      </PageHeader>
      <div className="relative mb-4 max-w-sm">
        <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" aria-hidden="true" />
        <input className="w-full h-9 border border-border rounded-btn bg-surface text-sm pl-9 pr-3" aria-label="Search accounts"
          placeholder="Search name or email" value={search} onChange={(event) => setSearch(event.target.value)} />
      </div>
      {list.loading && !list.data && <p role="status" className="text-sm text-muted">Loading accounts…</p>}
      {(list.error || error) && <p role="alert" className="text-sm text-risk-extreme mb-3">{error || list.error}</p>}
      {notice && <p role="status" className="text-sm mb-3">{notice}</p>}
      {list.data && !rows.length && <p className="text-sm text-muted">No accounts match your search.</p>}
      {rows.length > 0 && <div className="panel divide-y divide-border">
        {rows.map((account) => (
          <article key={account.id} aria-label={`Account ${account.id}`} className="p-4 flex flex-wrap items-center gap-3">
            <span aria-hidden="true" className={`w-9 h-9 rounded-full grid place-items-center text-xs font-semibold ${account.status === 'Active' ? 'bg-brand text-white' : 'bg-surface-2 text-muted'}`}>{initials(account.name)}</span>
            <div className="min-w-0 flex-1">
              <p className="font-medium">{account.name}{actor.id === account.id ? <span className="text-muted font-normal"> (you)</span> : ''}</p>
              <p className="text-sm text-muted break-all">{account.email}</p>
            </div>
            <span className="text-xs font-semibold px-2 py-1 rounded-full bg-surface-2 text-muted">{account.role === 'admin' ? 'Administrator' : 'Officer'} / {account.status}</span>
            <div className="flex gap-2">
              <button className={buttonClass} disabled={busy} onClick={() => open(account)}>Edit</button>
              <button className={buttonClass + ' text-risk-extreme'} disabled={busy || actor.id === account.id} onClick={() => remove(account)}>Remove</button>
            </div>
          </article>
        ))}
      </div>}
      {editing !== undefined && (
        <div
          className="fixed inset-0 z-[1500] bg-black/30 flex justify-end"
          role="dialog"
          aria-modal="true"
          aria-label={editing ? 'Edit account' : 'Add account'}
        >
          <form
            onSubmit={save}
            className="bg-surface w-full max-w-md p-6 overflow-y-auto space-y-4 border-l border-border modal-scale-in"
          >
            <h2 className="text-xl font-semibold">{editing ? 'Edit account' : 'Add account'}</h2>
            {['name', 'email'].map((field) => (
              <label className="block text-sm capitalize" key={field}>
                {field}
                <input
                  required
                  maxLength={field === 'name' ? 100 : 150}
                  type={field === 'email' ? 'email' : 'text'}
                  aria-label={`Account ${field}`}
                  className={input}
                  value={form[field]}
                  disabled={busy}
                  onChange={(event) =>
                    setForm((value) => ({ ...value, [field]: event.target.value }))
                  }
                />
              </label>
            ))}
            <label className="block text-sm">
              Role
              <select
                aria-label="Account role"
                className={input}
                value={form.role}
                disabled={busy || editing?.id === actor.id}
                onChange={(event) => setForm((value) => ({ ...value, role: event.target.value }))}
              >
                <option value="officer">Officer</option>
                <option value="admin">Administrator</option>
              </select>
            </label>
            {editing && (
              <label className="block text-sm">
                Status
                <select
                  aria-label="Account status"
                  className={input}
                  value={form.status}
                  disabled={busy || editing.id === actor.id}
                  onChange={(event) =>
                    setForm((value) => ({ ...value, status: event.target.value }))
                  }
                >
                  <option>Active</option>
                  <option>Inactive</option>
                </select>
              </label>
            )}
            <label className="block text-sm">
              {editing ? 'New password (optional)' : 'Password'}
              <input
                type="password"
                autoComplete="new-password"
                aria-label="Account password"
                required={!editing}
                minLength={8}
                className={input}
                value={form.password}
                disabled={busy}
                onChange={(event) =>
                  setForm((value) => ({ ...value, password: event.target.value }))
                }
              />
            </label>
            {error && (
              <p role="alert" className="text-risk-extreme">
                {error}
              </p>
            )}
            <div className="flex gap-3">
              <button disabled={busy} className={primaryButtonClass}>
                {busy ? 'Saving...' : 'Save account'}
              </button>
              <button
                type="button"
                disabled={busy}
                className={buttonClass}
                onClick={() => {
                  setForm(initial)
                  setEditing(undefined)
                  setError('')
                }}
              >
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}
    </section>
  )
}
