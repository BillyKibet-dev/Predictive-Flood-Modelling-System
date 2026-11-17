import StaffLayout from '../components/StaffLayout'
import SystemHealth from './admin/SystemHealth'
import UserAccounts from './admin/UserAccounts'

// Administrator tools; each has its own address (/admin, /admin/users, /admin/models).
export default function AdminPage({ section = 'health' }) {
  return <StaffLayout width="max-w-5xl">
    {section === 'users' ? <UserAccounts /> : <SystemHealth />}
  </StaffLayout>
}
