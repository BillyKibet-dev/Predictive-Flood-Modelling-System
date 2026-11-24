import { useEffect } from 'react'

// "Reports · NairobiFloodWatch" in the browser tab, history and bookmarks.
export default function usePageTitle(title) {
  useEffect(() => {
    document.title = title ? `${title} · NairobiFloodWatch` : 'NairobiFloodWatch'
  }, [title])
}
