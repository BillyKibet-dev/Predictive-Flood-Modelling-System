import { CheckCircle2, Info, XCircle } from 'lucide-react'

const ICONS = { success: CheckCircle2, error: XCircle, info: Info }
const BORDER = { success: '#16A34A', error: '#DC2626', info: 'var(--accent)' }

// Toast stack — fixed top-right, slides in from the right, auto-dismisses after 3s
export default function Toast({ toasts }) {
  return (
    <div className="fixed z-[2000] flex flex-col gap-2" style={{ top: 80, right: 24 }}>
      {toasts.map((t) => {
        const Icon = ICONS[t.type] || ICONS.success
        return (
          <div
            key={t.id}
            role="status"
            className="toast-enter flex items-center gap-2 bg-surface text-ink border-l-4 rounded-card shadow-card-hover px-4 py-3 text-sm font-medium min-w-[260px]"
            style={{ borderLeftColor: BORDER[t.type] || BORDER.success }}
          >
            <Icon size={18} style={{ color: BORDER[t.type] || BORDER.success }} />
            {t.message}
          </div>
        )
      })}
    </div>
  )
}
