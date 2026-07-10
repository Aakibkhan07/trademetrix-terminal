'use client'

import { create } from 'zustand'

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

export interface MarketState {
  ticks: Record<string, TickData>
  connected: boolean
  feedMode: FeedMode
  subscribedSymbols: Set<string>
  setTicks: (ticks: Record<string, TickData>) => void
  setConnected: (connected: boolean) => void
  setFeedMode: (mode: FeedMode) => void
  subscribe: (symbols: string[]) => void
  unsubscribe: (symbols: string[]) => void
}

export const useMarketStore = create<MarketState>((set, get) => ({
  ticks: {},
  connected: false,
  feedMode: 'idle',
  subscribedSymbols: new Set(),

  setTicks: (ticks) => set({ ticks }),
  setConnected: (connected) => set({ connected }),
  setFeedMode: (feedMode) => set({ feedMode }),

  subscribe: (symbols) => {
    const current = get().subscribedSymbols
    symbols.forEach(s => current.add(s))
    set({ subscribedSymbols: new Set(current) })
  },

  unsubscribe: (symbols) => {
    const current = get().subscribedSymbols
    symbols.forEach(s => current.delete(s))
    set({ subscribedSymbols: new Set(current) })
  },
}))
