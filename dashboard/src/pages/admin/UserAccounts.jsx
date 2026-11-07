import { useState } from 'react'
import { useAuth } from '../../context/AuthContext'
import useStaffList from '../../hooks/useStaffList'

const initial = { name: '', email: '', role: 'officer', status: 'Active', password: '' }
const input = 'w-full border border-border rounded-btn bg-surface text-ink p-2'
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
  return (
    <section className="space-y-5 text-ink">
      <div className="flex flex-wrap justify-between gap-3">
        <h1 className="text-2xl font-semibold">User accounts</h1>
        <div className="flex gap-2">
          <button className="border border-border rounded-btn p-2" onClick={list.refresh}>
            Refresh accounts
          </button>
          <button className="bg-brand text-white rounded-btn p-2" onClick={() => open()}>
            Add user
          </button>
        </div>
      </div>
      <p className="text-sm text-muted">
        Accounts are saved in the database. Deactivate an account to revoke access while retaining
        its review history. Changes are checked by the server.
      </p>
      <input
        className={input}
        aria-label="Search accounts"
        placeholder="Search name or email"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
      />
      {list.loading && <p role="status">Loading accounts...</p>}
      {(list.error || error) && (
        <p role="alert" className="text-risk-extreme">
          {error || list.error}
        </p>
      )}
      {notice && <p role="status">{notice}</p>}
      {list.data && !rows.length && <p>No accounts match your search.</p>}
      {rows.map((account) => (
        <article
          key={account.id}
          aria-label={`Account ${account.id}`}
          className="border border-border bg-surface rounded-card p-4 flex flex-wrap items-center gap-3"
        >
          <div className="min-w-0 flex-1">
            <p className="font-semibold">
              {account.name}
              {actor.id === account.id ? ' (you)' : ''}
            </p>
            <p className="text-sm text-muted break-all">{account.email}</p>
            <p className="text-xs text-muted">
              {account.role} / {account.status}
            </p>
          </div>
          <button
            className="border border-border rounded-btn p-2"
            disabled={busy}
            onClick={() => open(account)}
          >
            Edit
          </button>
          <button
            className="border border-border rounded-btn p-2 text-risk-extreme"
            disabled={busy || actor.id === account.id}
            onClick={() => remove(account)}
          >
            Remove
          </button>
        </article>
      ))}
      {editing !== undefined && (
        <div
          className="fixed inset-0 z-[1500] bg-black/40 flex justify-end"
          role="dialog"
          aria-modal="true"
          aria-label={editing ? 'Edit account' : 'Add account'}
        >
          <form
            onSubmit={save}
            className="bg-surface w-full max-w-md p-6 overflow-y-auto space-y-4"
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
              <button disabled={busy} className="bg-brand text-white px-4 py-2 rounded-btn">
                {busy ? 'Saving...' : 'Save account'}
              </button>
              <button
                type="button"
                disabled={busy}
                className="border border-border p-2 rounded-btn"
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
