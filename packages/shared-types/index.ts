// Trade Metrix Shared Types — mirrored from Pydantic models
// Keep in sync with core/models.py

export type OrderSide = 'BUY' | 'SELL'
export type OrderType = 'MARKET' | 'LIMIT' | 'SL' | 'SLM'
export type ProductType = 'DELIVERY' | 'INTRADAY' | 'MIS' | 'NRML'
export type OrderStatus = 'PENDING' | 'OPEN' | 'PARTIALLY_FILLED' | 'FILLED' | 'CANCELLED' | 'REJECTED' | 'EXPIRED'
export type Exchange = 'NSE' | 'BSE' | 'NFO' | 'CDS' | 'MCX'

export interface NormalizedOrder {
  id: string
  broker_order_id: string
  symbol: string
  exchange: Exchange
  side: OrderSide
  order_type: OrderType
  product: ProductType
  quantity: number
  price: number
  trigger_price?: number
  status: OrderStatus
  filled_quantity: number
  average_price: number
  signal_at?: string
  risk_checked_at?: string
  sent_at?: string
  filled_at?: string
  latency_ms?: number
  slippage?: number
  strategy_id?: string
  broker: string
}

export interface Position {
  symbol: string
  exchange: Exchange
  quantity: number
  buy_quantity: number
  sell_quantity: number
  average_buy_price: number
  average_sell_price: number
  unrealised_pnl: number
  realised_pnl: number
  m2m: number
  product: ProductType
  broker: string
}

export interface Funds {
  total_margin: number
  used_margin: number
  available_margin: number
  broker: string
}

export interface Quote {
  symbol: string
  exchange: Exchange
  last_price: number
  open: number
  high: number
  low: number
  close: number
  volume: number
  bid: number
  ask: number
  timestamp: string
  broker: string
}

export interface Candle {
  symbol: string
  exchange: Exchange
  interval: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  timestamp: string
}

export interface Tick {
  symbol: string
  exchange: Exchange
  last_price: number
  bid: number
  ask: number
  volume: number
  oi: number
  timestamp: string
  broker: string
}

export interface RiskSettings {
  max_capital: number
  max_position_size: number
  max_open_positions: number
  max_daily_loss: number
  max_drawdown_pct: number
  kill_switch_enabled: boolean
  is_live: boolean
}

export interface UserProfile {
  id: string
  email: string
  full_name: string
  is_admin: boolean
  subscription_tier: string
}
