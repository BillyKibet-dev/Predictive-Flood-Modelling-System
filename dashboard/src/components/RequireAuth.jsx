import { Navigate } from 'react-router-dom'

// Route guard: blocks access unless a user is logged in (and optionally has the required role)
export default function RequireAuth({ user, role, children }) {
  if (!user) {
    return <Navigate to="/login" replace />
  }
  if (role && user.role !== role) {
    return <Navigate to={user.role === 'admin' ? '/admin' : '/dashboard'} replace />
  }
  return children
}
