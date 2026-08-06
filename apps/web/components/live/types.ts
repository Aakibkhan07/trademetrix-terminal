'use client'

// Shared types for the Live Operational Dashboard (`/live`).
// These mirror the canonical backend payload contracts (SignalPayload,
// runtime status, market status, engine positions/orders) with optional
// fields so the dashboard degrades gracefully on any shape drift.

export interface LiveSignal {
  signal_version?: number
  signal_id: string
  strategy_id: string
  strategy_name?: string
  user_id?: string
  symbol: string
  exchange?: string
  side: string
  quantity?: number
  price?: number
  sl_price?: number
  target_price?: number
  confidence?: number
  reason?: string
  mode?: string
  triggered_at?: string
  metadata?: Record<string, unknown>
}

export interface LiveOrder {
  id?: string
  broker_order_id?: string
  symbol: string
  exchange?: string
  side: string
  order_type?: string
  product?: string
  quantity: number
  price?: number
  trigger_price?: number
  status: string
  is_paper?: boolean
  message?: string
  filled_quantity?: number
  average_price?: number
  instrument_type?: string
  filled_at?: string
  created_at?: string
}

export interface LivePosition {
  symbol: string
  exchange?: string
  quantity: number
  average_buy_price?: number
  average_sell_price?: number
  buy_quantity?: number
  sell_quantity?: number
  unrealised_pnl?: number
  realised_pnl?: number
  m2m?: number
  product?: string
  last_price?: number
}

export interface MarketStatus {
  is_open: boolean
  market: string
  open_time: string
  close_time: string
  next_open: string
  next_holiday: string
  current_time: string
}

export interface RuntimeStrategySummary {
  strategy_id: string
  user_id?: string
  state: string
  symbol: string
  exchange?: string
  interval?: string
  timeframes?: string[]
  mode?: string
  broker?: string
  account?: string
  trigger?: string
  started_at?: string
  stopped_at?: string
  paused_reason?: string
  last_error?: string
  last_activity?: string
  worker_active?: boolean
  last_price?: number
  stats?: Record<string, unknown>
}

export interface RuntimeHealth {
  status: string
  runtime_state: string
  strategies_total: number
  strategies_by_state: Record<string, number>
  strategies_running: number
  running_list: string[]
  scheduler_active: boolean
  broker_states: Record<string, string>
  metrics?: Record<string, unknown>
}

export const fmtInr = (n: number | undefined | null) => {
  if (n === undefined || n === null || Number.isNaN(n)) return '—'
  const sign = n < 0 ? '-' : ''
  return `${sign}₹${Math.abs(n).toLocaleString('en-IN', { maximumFractionDigits: 2 })}`
}

export const fmtNum = (n: number | undefined | null, digits = 2) => {
  if (n === undefined || n === null || Number.isNaN(n)) return '—'
  return n.toLocaleString('en-IN', { maximumFractionDigits: digits })
}

export const fmtTime = (iso: string | undefined) => {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}
