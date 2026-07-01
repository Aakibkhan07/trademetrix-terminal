'use client'

import { createContext, useContext, useEffect, useRef, useState, useCallback, type ReactNode } from 'react'
import { api } from '@/lib/api'

export interface TickData {
  symbol: string
  last_price: number
  bid: number
  ask: number
  bid_qty: number
  ask_qty: number
  volume: number
  oi: number
  change: number
  change_pct: number
  timestamp: string
  exchange: string
}

export type FeedMode = 'idle' | 'simulator' | 'broker'

interface MarketDataContextType {
  ticks: Record<string, TickData>
  connected: boolean
  feedMode: FeedMode
  subscribe: (symbols: string[]) => void
  unsubscribe: (symbols: string[]) => void
  startFeed: () => Promise<void>
  stopFeed: () => Promise<void>
}

const MarketDataContext = createContext<MarketDataContextType>({
  ticks: {},
  connected: false,
  feedMode: 'idle',
  subscribe: () => {},
  unsubscribe: () => {},
  startFeed: async () => {},
  stopFeed: async () => {},
})

export function MarketDataProvider({ children }: { children: ReactNode }) {
  const [ticks, setTicks] = useState<Record<string, TickData>>({})
  const [connected, setConnected] = useState(false)
  const [feedMode, setFeedMode] = useState<FeedMode>('idle')
  const wsRef = useRef<WebSocket | null>(null)
  const subscribedRef = useRef<Set<string>>(new Set())
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const connect = useCallback(() => {
    const baseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1'
    const wsBase = baseUrl.replace(/^http/, 'ws').replace(/\/api\/v1\/?$/, '')
    const wsUrl = `${wsBase}/api/v1/marketdata/ws`

    try {
      const ws = new WebSocket(wsUrl)
      ws.onopen = () => {
        setConnected(true)
        if (subscribedRef.current.size > 0) {
          ws.send(JSON.stringify({ action: 'subscribe', symbols: Array.from(subscribedRef.current) }))
        }
      }
      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data)
          if (msg.type === 'tick') {
            setTicks((prev) => ({ ...prev, [msg.symbol]: msg }))
          }
        } catch {}
      }
      ws.onclose = () => {
        setConnected(false)
        reconnectTimerRef.current = setTimeout(connect, 3000)
      }
      ws.onerror = () => { ws.close() }
      wsRef.current = ws
    } catch {}
  }, [])

  useEffect(() => {
    connect()
    return () => {
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current)
      wsRef.current?.close()
    }
  }, [connect])

  const subscribe = useCallback((symbols: string[]) => {
    for (const s of symbols) subscribedRef.current.add(s)
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ action: 'subscribe', symbols }))
    }
  }, [])

  const unsubscribe = useCallback((symbols: string[]) => {
    for (const s of symbols) subscribedRef.current.delete(s)
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ action: 'unsubscribe', symbols }))
    }
  }, [])

  const startFeed = useCallback(async () => {
    try {
      const res = await api.post<{ broker?: string }>('/marketdata/feed/start')
      setFeedMode(res?.broker === 'simulator' ? 'simulator' : 'broker')
    } catch {
      setFeedMode('idle')
    }
  }, [])

  const stopFeed = useCallback(async () => {
    try { await api.post('/marketdata/feed/stop') } catch {}
    setFeedMode('idle')
  }, [])

  return (
    <MarketDataContext.Provider value={{ ticks, connected, feedMode, subscribe, unsubscribe, startFeed, stopFeed }}>
      {children}
    </MarketDataContext.Provider>
  )
}

export function useMarketData() {
  return useContext(MarketDataContext)
}
