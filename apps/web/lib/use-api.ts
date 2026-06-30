'use client'

import { useEffect, useState, useRef } from 'react'
import { api, ApiError } from './api'

export interface UseApiResult<T> {
  data: T | null
  loading: boolean
  error: ApiError | null
}

export function useApi<T = unknown>(path: string | null): UseApiResult<T> {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<ApiError | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    if (abortRef.current) abortRef.current.abort()

    if (!path) {
      setData(null)
      setLoading(false)
      setError(null)
      return
    }

    const controller = new AbortController()
    abortRef.current = controller
    setLoading(true)
    setError(null)

    api.get<T>(path, controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) {
          setData(result)
          setLoading(false)
        }
      })
      .catch((err) => {
        if (!controller.signal.aborted) {
          setData(null)
          setError(err instanceof ApiError ? err : new ApiError(0, String(err)))
          setLoading(false)
        }
      })

    return () => controller.abort()
  }, [path])

  return { data, loading, error }
}
