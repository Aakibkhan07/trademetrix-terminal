'use client'

import { create } from 'zustand'

export interface Toast {
  id: string
  type: 'success' | 'error' | 'info' | 'warning'
  message: string
}

export type Theme = 'dark' | 'light'

export type QuickOrderSide = 'BUY' | 'SELL'

export interface QuickOrderState {
  open: boolean
  symbol: string
  name: string
  side: QuickOrderSide
  prefillQty?: number
}

export interface DrawerPrefs {
  paper: boolean
  product: 'INTRADAY' | 'NRML'
  orderType: 'MARKET' | 'LIMIT'
}

export interface WSPrefs {
  activeSymbol: string
  activeName: string
  analyzeOpen: boolean
  bottomTab: 'position' | 'orders'
  chainOpen: boolean
  chartInterval: string
}

const PREFS_KEY = 'tm_ws_prefs'

export interface UIState {
  sidebarCollapsed: boolean
  theme: Theme
  toasts: Toast[]
  quickOrder: QuickOrderState
  drawerPrefs: DrawerPrefs
  activeSymbol: string
  activeName: string
  wsPrefs: WSPrefs
  recentSymbols: { symbol: string; name: string; at: number }[]
  toggleSidebar: () => void
  setTheme: (theme: Theme) => void
  addToast: (type: Toast['type'], message: string, duration?: number) => void
  removeToast: (id: string) => void
  openQuickOrder: (symbol: string, name: string, side?: QuickOrderSide, prefillQty?: number) => void
  closeQuickOrder: () => void
  setDrawerPrefs: (prefs: Partial<DrawerPrefs>) => void
  setActiveSymbol: (symbol: string, name?: string) => void
  setWsPrefs: (prefs: Partial<WSPrefs>) => void
  restoreWsPrefs: () => void
  pushRecent: (symbol: string, name: string) => void
  clearRecents: () => void
}

const getInitialTheme = (): Theme => {
  if (typeof window !== 'undefined') {
    return (localStorage.getItem('theme') as Theme) || 'dark'
  }
  return 'dark'
}

const DEFAULT_PREFS: WSPrefs = { activeSymbol: 'NSE:NIFTY50-INDEX', activeName: 'NIFTY 50', analyzeOpen: false, bottomTab: 'position', chainOpen: false, chartInterval: '15m' }

const loadPrefs = (): WSPrefs => {
  if (typeof window === 'undefined') return DEFAULT_PREFS
  try {
    const p = JSON.parse(localStorage.getItem(PREFS_KEY) || '{}')
    return {
      activeSymbol: p.activeSymbol || DEFAULT_PREFS.activeSymbol,
      activeName: p.activeName || DEFAULT_PREFS.activeName,
      analyzeOpen: !!p.analyzeOpen,
      bottomTab: p.bottomTab === 'orders' ? 'orders' : 'position',
      chainOpen: !!p.chainOpen,
      chartInterval: p.chartInterval || DEFAULT_PREFS.chartInterval,
    }
  } catch {
    return DEFAULT_PREFS
  }
}

const loadDrawerPrefs = (): DrawerPrefs => {
  if (typeof window === 'undefined') return { paper: true, product: 'INTRADAY', orderType: 'MARKET' }
  try {
    const p = JSON.parse(localStorage.getItem('tm_drawer_prefs') || '{}')
    return {
      paper: p.paper !== false,
      product: p.product === 'NRML' ? 'NRML' : 'INTRADAY',
      orderType: p.orderType === 'LIMIT' ? 'LIMIT' : 'MARKET',
    }
  } catch {
    return { paper: true, product: 'INTRADAY', orderType: 'MARKET' }
  }
}

const loadRecents = (): { symbol: string; name: string; at: number }[] => {
  if (typeof window === 'undefined') return []
  try { return JSON.parse(localStorage.getItem('tm_recent_symbols') || '[]') } catch { return [] }
}

export const useUIStore = create<UIState>((set, get) => ({
  sidebarCollapsed: false,
  theme: getInitialTheme(),
  toasts: [],
  quickOrder: { open: false, symbol: '', name: '', side: 'BUY' },
  drawerPrefs: { paper: true, product: 'INTRADAY', orderType: 'MARKET' },
  activeSymbol: 'NSE:NIFTY50-INDEX',
  activeName: 'NIFTY 50',
  wsPrefs: DEFAULT_PREFS,
  recentSymbols: [],

  toggleSidebar: () => set(s => ({ sidebarCollapsed: !s.sidebarCollapsed })),

  setTheme: (theme) => {
    localStorage.setItem('theme', theme)
    document.documentElement.setAttribute('data-theme', theme)
    set({ theme })
  },

  addToast: (type, message, duration = 4000) => {
    const id = Date.now().toString(36)
    set(s => ({ toasts: [...s.toasts, { id, type, message }] }))
    if (duration > 0) {
      setTimeout(() => get().removeToast(id), duration)
    }
  },

  removeToast: (id) => set(s => ({ toasts: s.toasts.filter(t => t.id !== id) })),

  openQuickOrder: (symbol, name, side, prefillQty) =>
    set(s => ({
      quickOrder: { open: true, symbol, name, side: side || s.quickOrder.side || 'BUY', prefillQty },
      activeSymbol: symbol,
      activeName: name || s.activeName,
    })),

  closeQuickOrder: () => set(s => ({ quickOrder: { ...s.quickOrder, open: false } })),

  setDrawerPrefs: (prefs) => {
    const next = { ...get().drawerPrefs, ...prefs }
    localStorage.setItem('tm_drawer_prefs', JSON.stringify(next))
    set({ drawerPrefs: next })
  },

  setActiveSymbol: (symbol, name) =>
    set(s => ({
      activeSymbol: symbol,
      activeName: name || s.activeName,
      wsPrefs: { ...s.wsPrefs, activeSymbol: symbol, activeName: name || s.activeName },
    })),

  setWsPrefs: (prefs) => {
    const next = { ...get().wsPrefs, ...prefs }
    localStorage.setItem(PREFS_KEY, JSON.stringify(next))
    set({ wsPrefs: next })
  },

  restoreWsPrefs: () => {
    const p = loadPrefs()
    set({
      wsPrefs: p,
      activeSymbol: p.activeSymbol,
      activeName: p.activeName,
      drawerPrefs: loadDrawerPrefs(),
      recentSymbols: loadRecents(),
    })
  },

  pushRecent: (symbol, name) => {
    const next = [{ symbol, name, at: Date.now() }, ...get().recentSymbols.filter(r => r.symbol !== symbol)].slice(0, 10)
    localStorage.setItem('tm_recent_symbols', JSON.stringify(next))
    set({ recentSymbols: next })
  },

  clearRecents: () => {
    localStorage.setItem('tm_recent_symbols', '[]')
    set({ recentSymbols: [] })
  },
}))
