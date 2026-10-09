import { useState } from 'react'

const ROLE_BADGE = { admin: 'bg-slate-700', officer: 'bg-accent' }
const STATUS_BADGE = { Active: 'bg-risk-low', Inactive: 'bg-risk-extreme' }

function initials(name) {
  return name.split(' ').map((p) => p[0]).join('').slice(0, 2).toUpperCase()
}

// Admin section — manage system user accounts via a card list + slide-over add/edit panel
export default function UserAccounts({ users, setUsers, showToast }) {
  const [search, setSearch] = useState('')
  const [roleFilter, setRoleFilter] = useState('All')
  const [showPanel, setShowPanel] = useState(false)
  const [editingUser, setEditingUser] = useState(null)
  const [form, setForm] = useState({ name: '', email: '', role: 'officer', password: '' })

  const filtered = users.filter((u) => {
    const matchesSearch =
      u.name.toLowerCase().includes(search.toLowerCase()) || u.email.toLowerCase().includes(search.toLowerCase())
    const matchesRole = roleFilter === 'All' || u.role === roleFilter
    return matchesSearch && matchesRole
  })

  function openAddPanel() {
    setEditingUser(null)
    setForm({ name: '', email: '', role: 'officer', password: '' })
    setShowPanel(true)
  }

  function openEditPanel(u) {
    setEditingUser(u)
    setForm({ name: u.name, email: u.email, role: u.role, password: '' })
    setShowPanel(true)
  }

  function handleSave(e) {
    e.preventDefault()
    if (editingUser) {
      setUsers((prev) =>
        prev.map((u) => (u.id === editingUser.id ? { ...u, name: form.name, email: form.email, role: form.role } : u))
      )
      showToast('User updated successfully', 'success')
    } else {
      const newUser = {
        id: Math.max(0, ...users.map((u) => u.id)) + 1,
        name: form.name,
        email: form.email,
        role: form.role,
        status: 'Active',
      }
      setUsers((prev) => [...prev, newUser])
      showToast('User added successfully', 'success')
    }
    setShowPanel(false)
  }

  function handleDelete(id) {
    if (window.confirm('Remove this user account?')) {
      setUsers((prev) => prev.filter((u) => u.id !== id))
      showToast('User removed', 'success')
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <h2 className="text-2xl font-semibold tracking-tight text-ink">User Accounts</h2>
        <button
          onClick={openAddPanel}
          className="h-11 px-5 rounded-btn bg-brand text-white text-sm font-semibold hover:bg-brand-light transition-colors"
        >
          + Add User
        </button>
      </div>

      <div className="flex flex-wrap gap-3">
        <input
          type="text"
          placeholder="Search by name or email..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="h-10 w-[280px] border border-border rounded-btn px-3 text-sm bg-surface text-ink"
        />
        <select
          value={roleFilter}
          onChange={(e) => setRoleFilter(e.target.value)}
          className="h-10 w-40 border border-border rounded-btn px-3 text-sm bg-surface text-ink"
        >
          <option value="All">All Roles</option>
          <option value="admin">Admin</option>
          <option value="officer">Officer</option>
        </select>
      </div>

      <div className="space-y-2">
        {filtered.map((u) => (
          <div
            key={u.id}
            className="bg-surface border border-border rounded-card p-4 flex items-center gap-4 card-hover shadow-card-rest"
          >
            <span className="w-10 h-10 rounded-full bg-brand text-white flex items-center justify-center text-sm font-semibold shrink-0">
              {initials(u.name)}
            </span>
            <div className="flex-1 min-w-0">
              <p className="font-semibold text-ink">{u.name}</p>
              <p className="text-sm text-muted truncate">{u.email}</p>
              <div className="flex gap-2 mt-1.5">
                <span className={`text-white text-xs font-semibold px-2 py-0.5 rounded-full ${ROLE_BADGE[u.role]}`}>
                  {u.role}
                </span>
                <span className={`text-white text-xs font-semibold px-2 py-0.5 rounded-full ${STATUS_BADGE[u.status]}`}>
                  {u.status}
                </span>
              </div>
            </div>
            <div className="flex gap-2 shrink-0">
              <button
                onClick={() => openEditPanel(u)}
                className="text-xs font-medium border border-border rounded-btn px-3 py-1.5 hover:bg-bg transition-colors"
              >
                Edit
              </button>
              <button
                onClick={() => handleDelete(u.id)}
                className="text-xs font-medium text-risk-extreme border border-border rounded-btn px-3 py-1.5 hover:bg-bg transition-colors"
              >
                Remove
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* Slide-over add/edit panel */}
      {showPanel && (
        <div className="fixed inset-0 z-[1500]">
          <div className="absolute inset-0 bg-black/40" onClick={() => setShowPanel(false)} />
          <div className="absolute right-0 top-0 bottom-0 w-full max-w-md bg-surface shadow-modal p-6 overflow-y-auto modal-scale-in">
            <h3 className="text-xl font-semibold text-ink mb-6">{editingUser ? 'Edit User' : 'Add New User'}</h3>
            <form onSubmit={handleSave} className="space-y-5">
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5">Name</label>
                <input
                  required
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  className="w-full h-10 border border-border rounded-btn px-3 text-sm bg-surface text-ink"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5">Email</label>
                <input
                  type="email"
                  required
                  value={form.email}
                  onChange={(e) => setForm({ ...form, email: e.target.value })}
                  className="w-full h-10 border border-border rounded-btn px-3 text-sm bg-surface text-ink"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5">Role</label>
                <select
                  value={form.role}
                  onChange={(e) => setForm({ ...form, role: e.target.value })}
                  className="w-full h-10 border border-border rounded-btn px-3 text-sm bg-surface text-ink"
                >
                  <option value="admin">Admin</option>
                  <option value="officer">Officer</option>
                </select>
              </div>
              {!editingUser && (
                <div>
                  <label className="block text-sm font-medium text-ink mb-1.5">Temporary Password</label>
                  <input
                    type="text"
                    required
                    value={form.password}
                    onChange={(e) => setForm({ ...form, password: e.target.value })}
                    className="w-full h-10 border border-border rounded-btn px-3 text-sm bg-surface text-ink"
                  />
                </div>
              )}
              <div className="flex justify-end gap-3 pt-4">
                <button
                  type="button"
                  onClick={() => setShowPanel(false)}
                  className="h-11 px-5 rounded-btn border border-border text-sm font-medium text-ink hover:bg-bg transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="h-11 px-5 rounded-btn bg-brand text-white text-sm font-semibold hover:bg-brand-light transition-colors"
                >
                  Save
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
