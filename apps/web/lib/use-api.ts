'use client'

import { useEffect, useState, useRef } from 'react'
import { api, ApiError } from './api'

export interface UseApiResult<T> {
  data: T | null
  loading: boolean
  error: ApiError | null
}

const cache = new Map<string, { data: unknown; ts: number }>()
const CACHE_TTL = 10_000
const inflight = new Map<string, Promise<unknown>>()

export function useApi<T = unknown>(path: string | null): UseApiResult<T> {
  const [data, setData] = useState<T | null>(() => {
    if (path && cache.has(path)) return cache.get(path)!.data as T
    return null
  })
  const [loading, setLoading] = useState(!(path && cache.has(path)))
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

    const cached = cache.get(path)
    if (cached && Date.now() - cached.ts < CACHE_TTL) {
      setData(cached.data as T)
      setLoading(false)
      setError(null)
      return
    }

    const controller = new AbortController()
    abortRef.current = controller
    setLoading(true)
    setError(null)

    let req: Promise<unknown>
    if (inflight.has(path)) {
      req = inflight.get(path)!
    } else {
      req = api.get<T>(path, controller.signal).then(r => {
        cache.set(path, { data: r, ts: Date.now() })
        inflight.delete(path)
        return r
      }).catch(e => {
        inflight.delete(path)
        throw e
      })
      inflight.set(path, req)
    }

    req
      .then((result) => {
        if (!controller.signal.aborted) {
          setData(result as T)
          setLoading(false)
        }
      })
      .catch((err) => {
        if (!controller.signal.aborted) {
          if (!cached) {
            setData(null)
            setError(err instanceof ApiError ? err : new ApiError(0, String(err)))
          }
          setLoading(false)
        }
      })

    return () => controller.abort()
  }, [path])

  return { data, loading, error }
}
