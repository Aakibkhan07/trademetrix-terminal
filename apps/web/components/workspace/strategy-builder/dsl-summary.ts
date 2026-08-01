import { DSL, BlockMeta } from './types'

const ORDER_CATEGORIES = new Set(['order', 'signal'])
const RISK_CATEGORIES = new Set(['risk', 'portfolio'])
const TIME_CATEGORIES = new Set(['time'])

function fmtParam(key: string, value: unknown): string | null {
  if (value === undefined || value === null || value === '') return null
  if (typeof value === 'number') return String(value)
  if (typeof value === 'boolean') return value ? 'yes' : 'no'
  return String(value)
}

export function summarizeDsl(
  dsl: DSL | null,
  blocks: Record<string, BlockMeta>,
): { lines: string[]; valid: boolean; issues: string[] } {
  if (!dsl) {
    return { lines: ['No strategy yet — start from a template, or describe one in Beginner mode.'], valid: false, issues: ['Nothing to validate.'] }
  }

  const s = dsl.settings || {}
  const issues: string[] = []
  const lines: string[] = []

  const symbol = s.symbol || 'NIFTY'
  const interval = s.interval || '15m'
  const trigger = (s.trigger || 'CANDLE_CLOSE').toLowerCase().replace('_', ' ')
  lines.push(`Runs on ${symbol} ${interval} charts, triggered ${trigger}.`)

  if (s.max_positions && s.max_positions > 1) lines.push(`Up to ${s.max_positions} open positions at once.`)
  if (s.max_risk_per_trade) lines.push(`Risk capped at ${s.max_risk_per_trade}% per trade.`)
  if (s.max_daily_trades) lines.push(`Max ${s.max_daily_trades} trades per day.`)

  const byId = new Map(dsl.nodes.map(n => [n.id, n]))

  let orderBlocks = 0
  const described = new Set<string>()
  for (const node of dsl.nodes) {
    const meta = blocks[node.block_type]
    const label = meta?.display_name || meta?.name || node.block_type.replace(/\./g, ' ')
    if (meta && ORDER_CATEGORIES.has(meta.category)) orderBlocks++
    const key = `${node.block_type}|${JSON.stringify(node.params || {})}`
    if (described.has(key)) continue
    described.add(key)
    const parts = node.params ? Object.entries(node.params).slice(0, 2).map(([k, v]) => {
      const f = fmtParam(k, v)
      return f ? `${k.replace(/_/g, ' ')} ${f}` : null
    }).filter(Boolean) : []
    const suffix = parts.length ? ` (${parts.join(', ')})` : ''
    lines.push(`• ${label}${suffix}`)
  }

  if (dsl.edges.length) {
    let dangling = 0
    for (const e of dsl.edges) {
      if (!byId.has(e.source_node) || !byId.has(e.target_node)) dangling++
    }
    if (dangling) issues.push(`${dangling} connection(s) point at a missing block.`)
  }

  if (!dsl.nodes.length) issues.push('No blocks on the canvas yet.')
  if (!orderBlocks) issues.push('No buy/sell block found — the strategy cannot place orders.')
  if (!s.symbol) issues.push('Choose an underlying symbol.')

  lines.push(`${dsl.nodes.length} block(s) · ${dsl.edges.length} connection(s).`)
  return { lines, valid: issues.length === 0, issues }
}
