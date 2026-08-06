'use client'

import { useCallback, useMemo, useState, useEffect } from 'react'
import { api } from '@/lib/api'
import { useLiveData } from './use-live-data'
import type { LiveSignal, RuntimeStrategySummary } from './types'
import type { LiveEventCallback } from './use-live-connection'

const MAX_SIGNALS = 100

export interface LiveFeedFilters {
  mode: 'all' | 'paper' | 'live'
  side: 'all' | 'BUY' | 'SELL' | 'EXIT' | 'REVERSE' | 'HOLD'
  strategyId: string
  search: string
}

const DEFAULT_FILTERS: LiveFeedFilters = { mode: 'all', side: 'all', strategyId: '', search: '' }

/**
 * The Live Signals feed: subscribes to the canonical `SignalGenerated`
 * execution-bus event (single SSE connection owned by `use-live-connection`),
 * dedupes by `signal_id`, keeps the newest 100, and seeds the widget with the
 * currently running runtime strategies so the panel is never dead-empty.
 * Filters (mode / side / strategy / search) are applied client-side.
 */
export function useLiveFeed(subscribe: (type: string, cb: LiveEventCallback) => () => void) {
  const [signals, setSignals] = useState<LiveSignal[]>([])
  const [filters, setFilters] = useState<LiveFeedFilters>(DEFAULT_FILTERS)

  useEffect(() => {
    return subscribe('SignalGenerated', (event) => {
      const raw = event.payload || {}
      if (!raw.signal_id) return
      setSignals(prev => {
        const next = [raw as unknown as LiveSignal, ...prev.filter(s => s.signal_id !== raw.signal_id)]
        return next.slice(0, MAX_SIGNALS)
      })
    })
  }, [subscribe])

  const { data: seeds } = useLiveData<{ strategies: RuntimeStrategySummary[] }>(
    useCallback(async () => (await api.runtime.strategies()) as { strategies: RuntimeStrategySummary[] }, []),
    { intervalMs: 10_000 },
  )

  const strategyIds = useMemo(() => {
    const ids = new Set(signals.map(s => s.strategy_id).filter(Boolean))
    for (const s of seeds?.strategies || []) ids.add(s.strategy_id)
    return [...ids]
  }, [signals, seeds])

  const filtered = useMemo(() => {
    const q = filters.search.trim().toLowerCase()
    return signals.filter(s => {
      if (filters.mode !== 'all' && (s.mode || 'paper') !== filters.mode) return false
      if (filters.side !== 'all' && s.side !== filters.side) return false
      if (filters.strategyId && s.strategy_id !== filters.strategyId) return false
      if (q && !`${s.symbol} ${s.strategy_name || ''} ${s.reason || ''}`.toLowerCase().includes(q)) return false
      return true
    })
  }, [signals, filters])

  return { signals, filtered, filters, setFilters, strategyIds, seeds: seeds?.strategies || [] }
}