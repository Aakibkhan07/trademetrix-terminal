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

    // The shared request must NOT be tied to this hook's AbortController.
    //
    // It used to be, and the result was that `useApi` never worked on any page that gates its
    // rendering on the result. React 18's App Router mounts through `createRoot`, which is
    // StrictMode by default, so every effect runs twice in development: mount, cleanup, mount.
    // The cleanup aborted the controller that had been handed to the *shared* request, and the
    // second mount then found that same promise still sitting in `inflight` and reused it — so
    // it never issued a request of its own, and inherited one already cancelled. Both runs
    // rejected, the second with `controller.signal.aborted === false` (its own, unused
    // controller), and the hook reported `Request timed out — please retry` against a request
    // the server had answered in milliseconds.
    //
    // The tell was two log lines per path with opposite `aborted` values, across 16 files:
    // `/funds` and `/analytics` showed "Failed to load ...", while `/paper` rendered fine —
    // because `/paper` calls `api.*` directly and never touches this hook.
    //
    // Dedupe stays, and is still worth having for genuinely concurrent mounts. It simply no
    // longer lets one consumer's unmount cancel a request others are waiting on: the request
    // is owned by the module and bounded by its own timeout, and the hook's controller now
    // only decides whether to apply a result to state.
    let req: Promise<unknown>
    if (inflight.has(path)) {
      req = inflight.get(path)!
    } else {
      req = api.get<T>(path).then(r => {
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
