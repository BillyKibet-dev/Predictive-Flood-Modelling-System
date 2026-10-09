import { Navigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

// Route guard — admin can access all protected routes; officer limited to /officer and /officer/alerts
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
