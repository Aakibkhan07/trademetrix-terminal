'use client'

import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * Self-refreshing data hook for Live Dashboard panels: fetches `loader()`,
 * refreshes every `intervalMs` while online, skips refresh when the market is
 * closed (last-good-data stays visible), and never throws — errors surface as
 * the `error` state for WidgetFrame to render.
 */
export function useLiveData<T>(
  loader: () => Promise<T>,
  { intervalMs = 5000, enabled = true }: { intervalMs?: number, enabled?: boolean } = {},
) {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const loaderRef = useRef(loader)
  loaderRef.current = loader

  const run = useCallback(async () => {
    try {
      const res = await loaderRef.current()
      setData(res)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!enabled) {
      setLoading(false)
      return
    }
    run()
    const id = setInterval(run, intervalMs)
    return () => clearInterval(id)
  }, [enabled, intervalMs, run])

  return { data, loading, error }
}