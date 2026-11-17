import { Navigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

// Staff routes require their declared role; administrators may also use officer tools.
export default function ProtectedRoute({ role, children }) {
  const { user } = useAuth()

  if (!user) {
    return <Navigate to="/login" replace />
  }
  if (role && user.role !== role && user.role !== 'admin') {
    return <Navigate to="/officer" replace />
  }
  return children
}
