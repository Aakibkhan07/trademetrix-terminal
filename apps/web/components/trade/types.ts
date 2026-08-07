'use client'

import type { IndexKey, Moneyness } from '@/lib/options-contracts'

export interface OptionQuote {
  ltp: number
  bid: number
  ask: number
  volume: number
  oi: number
  iv: number
  change: number
  change_pct: number
}

export interface ChainRow {
  strike: number
  call: OptionQuote
  put: OptionQuote
}

export interface ChainData {
  optionChain: ChainRow[]
  expiries: string[]
}

export interface OrderResult {
  success: boolean
  broker_order_id: string
  message: string
  status: string
}

export interface PositionRow {
  id?: string
  symbol: string
  quantity: number
  average_buy_price: number
  last_price?: number
  unrealised_pnl?: number
  instrument_type?: string
  strike_price?: number
  expiry_date?: string
  option_type?: string
  product?: string
  is_paper?: boolean
}

export interface OrderRow {
  id: string
  symbol: string
  side: string
  order_type: string
  quantity: number
  price?: number
  trigger_price?: number
  filled_quantity?: number
  average_price?: number
  status: string
  created_at?: string
  is_paper?: boolean
  instrument_type?: string
  strike_price?: number
  expiry_date?: string
  option_type?: string
  product?: string
}

/** Shared selection state for the trader workspace. */
export interface TraderSelection {
  index: IndexKey
  moneyness: Moneyness
  customStrike: number | null
  optionType: 'CE' | 'PE'
  expiry: string
  expiryGroup: 'weekly' | 'monthly'
  lots: number
  orderType: 'MARKET' | 'LIMIT'
  limitPrice: number
}