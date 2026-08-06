'use client'

import { useCallback, useEffect, useState } from 'react'
import { api } from '@/lib/api'
import { useEvents, type ExecutionEventData } from '@/lib/use-events'
import { usePolling } from '@/lib/use-polling'
import type { MarketStatus } from './types'

export type LiveEventCallback = (event: ExecutionEventData) => void

/**
 * Single owner of the execution-event SSE feed for the Live Dashboard.
 * Exposes connectivity (browser online + SSE), the market session clock
 * (`/market/status`, polled) and a `subscribe(eventType, cb)` helper.
 * Every Live widget must derive its online/market-closed states from here
 * instead of opening its own EventSource.
 */
export function useLiveConnection(refreshMs = 60_000) {
  const { connected: sseConnected, subscribe } = useEvents()
  const [online, setOnline] = useState(true)
  const [market, setMarket] = useState<MarketStatus | null>(null)
  const [marketLoading, setMarketLoading] = useState(true)

  useEffect(() => {
    setOnline(typeof navigator !== 'undefined' ? navigator.onLine : true)
    const on = () => setOnline(true)
    const off = () => setOnline(false)
    window.addEventListener('online', on)
    window.addEventListener('offline', off)
    return () => {
      window.removeEventListener('online', on)
      window.removeEventListener('offline', off)
    }
  }, [])

  usePolling(
    useCallback(async () => {
      try {
        const s = await api.market.status()
        setMarket(s as MarketStatus)
      } catch {
        // keep the last known session state — never flip to a wrong open/closed
      } finally {
        setMarketLoading(false)
      }
    }, []),
    refreshMs,
    true,
  )

  return {
    online,
    isOffline: !online,
    sseConnected,
    subscribe,
    market,
    marketLoading,
    isMarketOpen: !!market?.is_open,
  }
}
