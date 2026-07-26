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
  const reconnectAttemptRef = useRef(0)
  const tickBufferRef = useRef<Record<string, TickData>>({})
  const flushTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const startFeed = useCallback(async () => {
    try {
      const res = await api.post<{ broker?: string }>('/marketdata/feed/start')
      setFeedMode(res?.broker === 'simulator' ? 'simulator' : 'broker')
    } catch (e) {
      console.error('startFeed', e)
      setFeedMode('idle')
    }
  }, [])

  const stopFeed = useCallback(async () => {
    try { await api.post('/marketdata/feed/stop') } catch (e) { console.error('stopFeed', e) }
    setFeedMode('idle')
  }, [])

  const subscribe = useCallback(async (symbols: string[]) => {
    for (const s of symbols) subscribedRef.current.add(s)
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ action: 'subscribe', symbols }))
      return
    }
    if (!wsRef.current) {
      connectRef.current?.()
      try { await startFeed() } catch (e) { console.error('subscribe startFeed', e) }
    }
  }, [startFeed])

  const unsubscribe = useCallback((symbols: string[]) => {
    for (const s of symbols) subscribedRef.current.delete(s)
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ action: 'unsubscribe', symbols }))
    }
  }, [])

  const connectRef = useRef<() => void>()

  connectRef.current = () => {
    const baseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1'
    const wsBase = baseUrl.replace(/^http/, 'ws').replace(/\/api\/v1\/?$/, '')
    const wsUrl = `${wsBase}/api/v1/marketdata/ws`

    try {
      const ws = new WebSocket(wsUrl)
      ws.onopen = () => {
        setConnected(true)
        reconnectAttemptRef.current = 0
        if (subscribedRef.current.size > 0) {
          ws.send(JSON.stringify({ action: 'subscribe', symbols: Array.from(subscribedRef.current) }))
        }
      }
      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data)
          if (msg.type === 'tick') {
            tickBufferRef.current[msg.symbol] = msg
          }
        } catch (e) { console.error('ws parse', e) }
      }
      ws.onclose = () => {
        setConnected(false)
        const delay = Math.min(1000 * Math.pow(2, reconnectAttemptRef.current), 30000)
        reconnectAttemptRef.current++
        reconnectTimerRef.current = setTimeout(() => connectRef.current?.(), delay)
      }
      ws.onerror = () => { ws.close() }
      wsRef.current = ws
    } catch (e) { console.error('ws connect', e) }
  }

  useEffect(() => {
    flushTimerRef.current = setInterval(() => {
      const buf = tickBufferRef.current
      if (Object.keys(buf).length === 0) return
      tickBufferRef.current = {}
      setTicks((prev) => {
        let changed = false
        for (const k in buf) {
          if (prev[k]?.last_price !== buf[k].last_price || prev[k]?.bid !== buf[k].bid) {
            changed = true
            break
          }
        }
        return changed ? { ...prev, ...buf } : prev
      })
    }, 250)
    return () => {
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current)
      if (flushTimerRef.current) clearInterval(flushTimerRef.current)
      wsRef.current?.close()
    }
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
