export interface DSLNode {
  id: string
  block_type: string
  params: Record<string, unknown>
  position?: { x: number; y: number }
  nested_graph?: unknown
}

export interface DSLEdge {
  id: string
  source_node: string
  source_port: string
  target_node: string
  target_port: string
}

export interface DSLSettings {
  symbol?: string
  exchange?: string
  interval?: string
  max_positions?: number
  max_risk_per_trade?: number
  max_daily_trades?: number
  trigger?: string
  require_confirmation?: boolean
}

export interface DSL {
  id?: string
  version?: string
  name: string
  description: string
  author?: string
  status?: string
  tags?: string[]
  settings?: DSLSettings
  nodes: DSLNode[]
  edges: DSLEdge[]
  created_at?: string
  updated_at?: string
  parent_id?: string
  version_number?: number
}

export interface ParamDef {
  name: string
  type: string
  label?: string
  default?: unknown
  options?: string[] | null
  min?: number | null
  max?: number | null
  step?: number | null
  description?: string
  required?: boolean
}

export interface PortDef {
  name: string
  type: string
  label?: string
  required?: boolean
}

export interface BlockMeta {
  type: string
  name: string
  category: string
  display_name?: string
  icon?: string
  description?: string
  inputs?: PortDef[]
  outputs?: PortDef[]
  params?: ParamDef[]
}

export const CATEGORY_META: Record<string, { label: string; color: string }> = {
  input: { label: 'Inputs', color: '#22d3ee' },
  indicator: { label: 'Indicators', color: '#38bdf8' },
  pattern: { label: 'Patterns', color: '#818cf8' },
  math: { label: 'Math', color: '#2dd4bf' },
  logic: { label: 'Logic', color: '#fb923c' },
  smc: { label: 'SMC', color: '#a78bfa' },
  ict: { label: 'ICT', color: '#c084fc' },
  greek: { label: 'Greeks', color: '#f472b6' },
  oi: { label: 'OI', color: '#fbbf24' },
  signal: { label: 'Signals', color: '#34d399' },
  order: { label: 'Orders', color: '#4ade80' },
  portfolio: { label: 'Portfolio', color: '#f87171' },
  risk: { label: 'Risk', color: 'var(--red)' },
  time: { label: 'Time', color: '#f59e0b' },
  variable: { label: 'Variables', color: '#94a3b8' },
  function: { label: 'Functions', color: '#60a5fa' },
  group: { label: 'Groups', color: '#a3e635' },
}


export interface TemplateInfo {
  key: string
  name: string
  description: string
  node_count: number
  tags: string[]
}

export interface ValidationIssue {
  severity: string
  node_id?: string
  message: string
}

export const INTERVALS = ['1m', '5m', '15m', '30m', '1h', '1d']

export const INDEX_SYMBOLS = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'SENSEX', 'NIFTYIT', 'MIDCPNIFTY']

export const TRIGGERS = ['CANDLE_CLOSE', 'EVERY_TICK', 'MARKET_OPEN']
