// Fixed-position toast notification stack used across all pages
export default function Toast({ toasts }) {
  return (
    <div className="fixed bottom-4 right-4 z-[2000] flex flex-col gap-2 items-end">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`animate-fade-in-up px-4 py-3 rounded-lg shadow-lg text-sm font-medium text-white ${
            t.type === 'error' ? 'bg-red-500' : t.type === 'info' ? 'bg-brand-accent' : 'bg-green-600'
          }`}
        >
          {t.message}
        </div>
      ))}
    </div>
  )
}
