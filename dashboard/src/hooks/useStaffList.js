import { useEffect, useRef, useState } from 'react'
import { useAuth } from '../context/AuthContext'

export default function useStaffList(path) {
  const { authorizedRequest } = useAuth()
  const [data, setData] = useState(null),
    [error, setError] = useState(''),
    [loading, setLoading] = useState(false),
    [revision, setRevision] = useState(0)
  const previousPath = useRef(path)
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError('')
    if (previousPath.current !== path) setData(null)
    previousPath.current = path
    authorizedRequest(path, { signal: controller.signal })
      .then((result) => {
        if (!controller.signal.aborted) setData(result)
      })
      .catch((failure) => {
        if (!controller.signal.aborted)
          setError(
            failure.name === 'AbortError'
              ? 'Request timed out. Retry to check the latest records.'
              : failure.message
          )
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
  }, [path, authorizedRequest, revision])
  // Polling applies only to reads, never mutations.
  useEffect(() => {
    const timer = setInterval(() => setRevision((value) => value + 1), 30000)
    return () => clearInterval(timer)
  }, [])
  return { data, error, loading, refresh: () => setRevision((value) => value + 1) }
}
