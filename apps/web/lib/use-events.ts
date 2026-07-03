'use client'

import { useEffect, useRef, useCallback, useState } from 'react'
import { api } from './api'

export interface ExecutionEventData {
  type: string
  execution_request_id: string
  user_id: string
  broker: string
  symbol: string
  side: string
  state: string
  message: string
  payload: Record<string, unknown>
  timestamp: string
}

type EventCallback = (event: ExecutionEventData) => void

export function useEvents() {
  const [connected, setConnected] = useState(false)
  const eventSourceRef = useRef<EventSource | null>(null)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const listenersRef = useRef<Map<string, Set<EventCallback>>>(new Map())

  const connect = useCallback(() => {
    if (eventSourceRef.current?.readyState === EventSource.OPEN) return

    try {
      const es = new EventSource(api.events.stream(), { withCredentials: true })
      es.onopen = () => setConnected(true)
      es.onerror = () => {
        setConnected(false)
        es.close()
        reconnectTimerRef.current = setTimeout(connect, 3000)
      }
      es.onmessage = (event) => {
        try {
          const data: ExecutionEventData = JSON.parse(event.data)
          const typeListeners = listenersRef.current.get(data.type)
          if (typeListeners) {
            typeListeners.forEach(cb => cb(data))
          }
          const wildcardListeners = listenersRef.current.get('*')
          if (wildcardListeners) {
            wildcardListeners.forEach(cb => cb(data))
          }
        } catch {}
      }
      eventSourceRef.current = es
    } catch {}
  }, [])

  useEffect(() => {
    connect()
    return () => {
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current)
      eventSourceRef.current?.close()
    }
  }, [connect])

  const subscribe = useCallback((eventType: string, callback: EventCallback) => {
    if (!listenersRef.current.has(eventType)) {
      listenersRef.current.set(eventType, new Set())
    }
    listenersRef.current.get(eventType)!.add(callback)
    return () => { listenersRef.current.get(eventType)?.delete(callback) }
  }, [])

  return { connected, subscribe }
}
