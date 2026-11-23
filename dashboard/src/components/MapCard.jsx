import { X } from 'lucide-react'
import { useEffect, useRef } from 'react'

// A frosted card that floats above every map layer: a bottom sheet on phones, a side card
// from tablet width. Closes with the X, the Escape key, or (handled by the map) a tap elsewhere.
export default function MapCard({ label, closeLabel, onClose, children, footer }) {
  const card = useRef(null)
  useEffect(() => {
    const onKey = event => { if (event.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  // Move focus into the card when it opens so keyboard and screen-reader users land on it.
  useEffect(() => { card.current?.focus({ preventScroll: true }) }, [label])
  // Swipe the handle down on phones to close.
  const drag = useRef(null)
  function onPointerDown(event) { drag.current = event.clientY }
  function onPointerUp(event) { if (drag.current !== null && event.clientY - drag.current > 60) onClose(); drag.current = null }

  return <aside ref={card} tabIndex={-1} aria-label={label} onPointerDown={event => event.stopPropagation()} onClick={event => event.stopPropagation()}
    className="map-card glass absolute z-[1050] text-ink outline-none flex flex-col
      inset-x-0 bottom-0 max-h-[58dvh] rounded-t-[20px] safe-bottom
      md:inset-x-auto md:bottom-auto md:top-3 md:right-3 md:w-[24rem] md:max-h-[calc(100%-1.5rem)] md:rounded-[18px]">
    <div className="md:hidden pt-2 pb-1 grid place-items-center touch-none cursor-grab" onPointerDown={onPointerDown} onPointerUp={onPointerUp} aria-hidden="true">
      <span className="w-10 h-1.5 rounded-full" style={{ background: 'color-mix(in srgb, var(--text-muted) 45%, transparent)' }} />
    </div>
    <button type="button" onClick={onClose} aria-label={closeLabel} title={closeLabel}
      className="press absolute top-3 right-3 z-10 w-10 h-10 grid place-items-center rounded-full glass-inset text-ink hover:bg-surface-2">
      <X size={19} />
    </button>
    <div className="overflow-y-auto overscroll-contain px-4 pb-4 pt-1 md:pt-4">{children}</div>
    {footer && <div className="border-t px-4 py-3" style={{ borderColor: 'color-mix(in srgb, var(--border) 70%, transparent)' }}>{footer}</div>}
  </aside>
}
