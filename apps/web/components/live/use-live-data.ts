'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { friendlyApiError, ApiError } from '@/lib/api'

export function useLiveData<T>(
  loader: () => Promise<T>,
  { intervalMs = 15000, enabled = true }: { intervalMs?: number, enabled?: boolean } = {},
) {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [halted, setHalted] = useState(false)
  const loaderRef = useRef(loader)
  loaderRef.current = loader

  const run = useCallback(async () => {
    if (typeof document !== 'undefined' && document.hidden) return
    if (!navigator.onLine) return
    try {
      const res = await loaderRef.current()
      setData(res)
      setError(null)
    } catch (e) {
      if (e instanceof ApiError && (e.status === 401 || e.status === 429)) {
        setHalted(true)
      }
      setError(friendlyApiError(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!enabled || halted) {
      if (!enabled) setLoading(false)
      return
    }
    run()
    const id = setInterval(run, intervalMs)
    return () => clearInterval(id)
  }, [enabled, halted, intervalMs, run])

  return { data, loading, error }
}