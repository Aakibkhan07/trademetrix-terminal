'use client'

import { useEffect, useState, useCallback, useRef } from 'react'
import { api } from '@/lib/api'
import { useMarketData } from '@/lib/use-market-data'
import { usePolling } from '@/lib/use-polling'
import { useAuth } from '@/lib/auth-context'
import { useToast } from '@/lib/use-toast'
import { PositionActions } from '@/components/positions/position-actions'
import type { ActionKind, TrailState } from '@/components/positions/position-actions'
import type { OrderRow, PositionRow } from '@/components/trade/types'

function downloadCSV(rows: string[][], filename: string) {
  const csv = rows.map(r => r.map(c => `"${String(c).replace(/"/g, '""')}"`).join(',')).join('\n')
  const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = filename; a.click()
  URL.revokeObjectURL(url)
}

function symbolOf(sym: string) { return sym.split(':').pop() || sym }

export default function PositionsPage() {
  const { token } = useAuth()
  const { ticks, connected, subscribe } = useMarketData()
  const { toast } = useToast()
  const [positions, setPositions] = useState<PositionRow[]>([])
  const [orders, setOrders] = useState<OrderRow[]>([])
  const [funds, setFunds] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [lastRefresh, setLastRefresh] = useState('')
  const [expanded, setExpanded] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [trails, setTrails] = useState<Record<string, TrailState>>({})
  const trailsRef = useRef<Record<string, TrailState>>({})

  useEffect(() => {
    subscribe(['NSE:NIFTY50-INDEX', 'NSE:NIFTYBANK-INDEX', 'NSE:FINNIFTY-INDEX', 'BSE:SENSEX-INDEX', 'NSE:INDIAVIX-INDEX'])
  }, [subscribe])

  const loadData = useCallback(async () => {
    try {
      const [p, o, f] = await Promise.all([
        api.engine.positions().catch(() => ({ positions: [] })),
        api.engine.orders().catch(() => ({ orders: [] })),
        api.engine.funds().catch(() => ({ funds: null })),
      ])
      const pos = (p as any).positions || []
      setPositions(pos)
      setOrders((o as any).orders || [])
      setFunds((f as any).funds || null)
      setLastRefresh(new Date().toLocaleTimeString())
      subscribe(pos.map((x: PositionRow) => x.symbol))
    } catch (e) { console.error('Failed to load positions', e) } finally { setLoading(false) }
  }, [subscribe])

  usePolling(loadData, 10000, !!token)

  const ltpFor = (p: PositionRow) => {
    const live = ticks[p.symbol]
    if (live?.last_price && live.last_price > 0) return live.last_price
    if (p.last_price && p.last_price > 0) return p.last_price
    return null
  }

  const pnlFor = (p: PositionRow) => {
    const live = ticks[p.symbol]
    const ltp = ltpFor(p)
    if (ltp && ltp > 0) return p.quantity * (ltp - (p.average_buy_price || 0))
    return p.unrealised_pnl || 0
  }

  const totalPnl = positions.reduce((sum, p) => sum + pnlFor(p), 0)

  const refreshSoon = () => setTimeout(loadData, 600)

  const cancelOrder = async (orderId: string) => {
    try {
      await api.engine.cancelOrder(orderId)
      toast('success', 'Order cancelled')
      refreshSoon()
    } catch {
      toast('error', 'Failed to cancel order')
    }
  }

  // ---- trail SL: client-side; re-issues the trigger via modifyOrder on ticks ----
  const startTrail = async (pos: PositionRow, distance: number) => {
    const ltp = ltpFor(pos)
    if (!ltp || ltp <= 0) { toast('error', 'No live price for this symbol'); return }
    if (!distance || distance <= 0) { toast('error', 'Enter a trail distance'); return }
    const long = pos.quantity > 0
    const side: 'BUY' | 'SELL' = long ? 'SELL' : 'BUY'
    const trigger = long ? ltp - distance : ltp + distance
    setBusy(pos.symbol)
    try {
      const res = await api.engine.trade({
        symbol: pos.symbol,
        side,
        quantity: Math.abs(pos.quantity),
        price: 0,
        trigger_price: trigger,
        exchange: 'NFO',
        order_type: 'SL-M',
        product: 'INTRADAY',
        instrument_type: pos.instrument_type || 'OPT',
        strike_price: pos.strike_price,
        expiry_date: pos.expiry_date,
        option_type: pos.option_type,
        is_paper: !!pos.is_paper,
        source: 'manual',
      }) as { result?: { broker_order_id?: string; success?: boolean; message?: string } }
      const orderId = res.result?.broker_order_id
      if (!orderId) { toast('error', res.result?.message || 'Trail SL not placed'); return }
      const state: TrailState = { symbol: pos.symbol, orderId, side, trigger, distance, lastBest: ltp }
      trailsRef.current[pos.symbol] = state
      setTrails({ ...trailsRef.current })
      toast('success', `Trail SL @ ${trigger.toFixed(1)} (${side})`)
      refreshSoon()
    } catch (e) {
      toast('error', String(e))
    } finally {
      setBusy(null)
    }
  }

  const stopTrail = async (pos: PositionRow) => {
    const t = trailsRef.current[pos.symbol]
    if (!t) return
    setBusy(pos.symbol)
    try {
      await api.engine.cancelOrder(t.orderId)
      toast('success', 'Trail SL stopped')
    } catch {
      toast('error', 'Failed to cancel trail SL')
    } finally {
      delete trailsRef.current[pos.symbol]
      setTrails({ ...trailsRef.current })
      setBusy(null)
    }
  }

  // re-issue trail triggers when price improves
  useEffect(() => {
    for (const t of Object.values(trailsRef.current)) {
      const tick = ticks[t.symbol]
      if (!tick?.last_price || tick.last_price <= 0) continue
      const improved = t.side === 'SELL'
        ? tick.last_price > t.lastBest + t.distance
        : tick.last_price < t.lastBest - t.distance
      if (!improved) continue
      const newTrigger = t.side === 'SELL' ? tick.last_price - t.distance : tick.last_price + t.distance
      const updated: TrailState = { ...t, lastBest: tick.last_price, trigger: newTrigger }
      trailsRef.current[t.symbol] = updated
      setTrails({ ...trailsRef.current })
      api.engine.modifyOrder(t.orderId, { trigger_price: newTrigger })
        .then(() => toast('success', `Trail SL moved to ${newTrigger.toFixed(1)}`))
        .catch(() => { /* keep old trigger; retried next improvement */ })
    }
  }, [ticks, toast])

  // ---- position actions ----
  const act = async (pos: PositionRow, kind: ActionKind, qty: number, extra?: { price?: number; triggerPrice?: number }) => {
    if (kind === 'exit') {
      if (!qty) { toast('error', 'Nothing to exit'); return }
      setBusy(pos.symbol)
      try {
        const side: 'BUY' | 'SELL' = pos.quantity > 0 ? 'SELL' : 'BUY'
        await api.engine.trade({
          symbol: pos.symbol, side, quantity: Math.abs(qty), price: 0,
          exchange: 'NFO', order_type: 'MARKET', product: 'INTRADAY',
          instrument_type: pos.instrument_type || 'OPT', strike_price: pos.strike_price,
          expiry_date: pos.expiry_date, option_type: pos.option_type,
          is_paper: !!pos.is_paper, source: 'manual',
        })
        toast('success', `Exit ${side} ${Math.abs(qty)}`)
        refreshSoon()
      } catch (e) { toast('error', String(e)) } finally { setBusy(null) }
      return
    }
    if (kind === 'partial' || kind === 'add') {
      if (!qty || qty <= 0) { toast('error', 'Enter a quantity'); return }
      if (kind === 'partial' && qty > Math.abs(pos.quantity)) { toast('error', 'Qty exceeds position'); return }
      const side = kind === 'partial' ? (pos.quantity > 0 ? 'SELL' : 'BUY') : (pos.quantity > 0 ? 'BUY' : 'SELL')
      setBusy(pos.symbol)
      try {
        await api.engine.trade({
          symbol: pos.symbol, side, quantity: qty, price: 0,
          exchange: 'NFO', order_type: 'MARKET', product: 'INTRADAY',
          instrument_type: pos.instrument_type || 'OPT', strike_price: pos.strike_price,
          expiry_date: pos.expiry_date, option_type: pos.option_type,
          is_paper: !!pos.is_paper, source: 'manual',
        })
        toast('success', `${kind === 'partial' ? 'Partial exit' : 'Added'} ${side} ${qty}`)
        refreshSoon()
      } catch (e) { toast('error', String(e)) } finally { setBusy(null) }
      return
    }
    if (kind === 'reverse') {
      if (!qty) { toast('error', 'Nothing to reverse'); return }
      const side: 'BUY' | 'SELL' = pos.quantity > 0 ? 'SELL' : 'BUY'
      setBusy(pos.symbol)
      try {
        await api.engine.trade({
          symbol: pos.symbol, side, quantity: Math.abs(qty), price: 0,
          exchange: 'NFO', order_type: 'MARKET', product: 'INTRADAY',
          instrument_type: pos.instrument_type || 'OPT', strike_price: pos.strike_price,
          expiry_date: pos.expiry_date, option_type: pos.option_type,
          is_paper: !!pos.is_paper, source: 'manual',
        })
        toast('success', `Reverse ${side} ${Math.abs(qty)}`)
        refreshSoon()
      } catch (e) { toast('error', String(e)) } finally { setBusy(null) }
      return
    }
    if (kind === 'modify') {
      const open = orders.find(o => o.symbol === pos.symbol && ['OPEN', 'PENDING', 'PARTIALLY_FILLED'].includes(o.status))
      if (!open) { toast('error', 'No resting order to modify'); return }
      const changes: { quantity?: number; price?: number; trigger_price?: number } = {}
      if (extra?.price) changes.price = extra.price
      if (extra?.triggerPrice) changes.trigger_price = extra.triggerPrice
      if (!Object.keys(changes).length) { toast('error', 'Enter a new price or trigger'); return }
      setBusy(pos.symbol)
      try {
        await api.engine.modifyOrder(open.id, changes)
        toast('success', 'Order modified')
        refreshSoon()
      } catch (e) { toast('error', String(e)) } finally { setBusy(null) }
    }
  }

  const toggleTrail = (pos: PositionRow) => (action: 'start' | 'stop', distance?: number) => {
    if (action === 'start') startTrail(pos, distance || 0)
    else stopTrail(pos)
  }

  return (
    <div>
      <div className="t-page-header">
        <div>
          <h1 className="t-page-title">Positions</h1>
          <p className="t-page-subtitle" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span className={`t-dot ${connected ? 't-dot-green t-dot-pulse' : 't-dot-sub'}`} />
            {connected ? 'Live' : 'Connecting...'}
            {lastRefresh && <span className="t-faint" style={{ marginLeft: 8 }}>Updated <span className="t-num">{lastRefresh}</span></span>}
          </p>
        </div>
        <button className="t-btn t-btn-ghost t-btn-sm" onClick={loadData}>Refresh</button>
      </div>

      {funds && (
        <div className="t-row" style={{ gap: 12, marginBottom: 16 }}>
          <div className="t-panel" style={{ flex: 1 }}>
            <div className="t-stat">
              <div className="t-stat-label">Available</div>
              <div className="t-stat-value">{(funds.available_margin || 0).toLocaleString()}</div>
            </div>
          </div>
          <div className="t-panel" style={{ flex: 1 }}>
            <div className="t-stat">
              <div className="t-stat-label">Used</div>
              <div className="t-stat-value" style={{ color: 'var(--cyan)' }}>{(funds.used_margin || 0).toLocaleString()}</div>
            </div>
          </div>
          <div className="t-panel" style={{ flex: 1 }}>
            <div className="t-stat">
              <div className="t-stat-label">Total P&amp;L</div>
              <div className={`t-stat-value ${totalPnl >= 0 ? 't-up' : 't-down'}`}>
                {totalPnl >= 0 ? '+' : ''}{totalPnl.toFixed(0)}
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="t-panel" style={{ padding: 0 }}>
        <div className="t-panel-header">
          <h3 className="t-panel-title">Open Positions ({positions.length})</h3>
          {positions.length > 0 && (
            <button className="t-btn t-btn-xs t-btn-ghost" onClick={() => {
              const header = ['Symbol', 'Type', 'Expiry', 'Strike', 'Qty', 'Buy Avg', 'LTP', 'P&L', 'P&L%', 'Product']
              const data = positions.map(p => {
                const ltp = ltpFor(p) || 0
                const pnl = pnlFor(p)
                const pnlPct = p.average_buy_price ? (pnl / (Math.abs(p.quantity) * p.average_buy_price) * 100) : 0
                return [p.symbol, p.instrument_type || '', p.expiry_date || '', String(p.strike_price || ''), String(p.quantity), p.average_buy_price?.toFixed(1) || '', ltp.toFixed(1), pnl.toFixed(0), pnlPct.toFixed(2), p.product || '']              })
              downloadCSV([header, ...data], `positions-${new Date().toISOString().slice(0, 10)}.csv`)
            }}>
              Export CSV
            </button>
          )}
        </div>
        {positions.length > 0 ? (
          <div className="t-table-wrap">
            <table className="t-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Type</th>
                  <th>Expiry</th>
                  <th className="t-num">Strike</th>
                  <th className="t-num">Qty</th>
                  <th className="t-num">Buy Avg</th>
                  <th className="t-num">LTP</th>
                  <th className="t-num">P&amp;L</th>
                  <th className="t-num">P&amp;L%</th>
                  <th className="t-num">Product</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {positions.map(p => {
                  const ltp = ltpFor(p)
                  const pnl = pnlFor(p)
                  const pnlPct = p.average_buy_price ? (pnl / (Math.abs(p.quantity) * p.average_buy_price) * 100) : 0
                  const posKey = p.id || `${p.symbol}|${p.quantity}|${p.average_buy_price}`
                  const isOpen = expanded === posKey
                  const openOrder = orders.find(o => o.symbol === p.symbol && ['OPEN', 'PENDING', 'PARTIALLY_FILLED'].includes(o.status)) || null
                  return (
                    <FragmentRow
                      key={posKey}
                      position={p}
                      ltp={ltp}
                      pnl={pnl}
                      pnlPct={pnlPct}
                      isOpen={isOpen}
                      trail={trails[p.symbol] || null}
                      busy={busy === p.symbol}
                      onToggleRow={() => setExpanded(isOpen ? null : posKey)}
                      onAct={(kind, qty, extra) => act(p, kind, qty, extra)}
                      onToggleTrail={toggleTrail(p)}
                      openOrder={openOrder}
                    />
                  )
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="t-panel-body" style={{ textAlign: 'center', padding: 20 }}>
            <span className="t-faint">{loading ? 'Loading...' : 'No open positions'}</span>
          </div>
        )}
      </div>

      <div className="t-panel" style={{ padding: 0 }}>
        <div className="t-panel-header">
          <h3 className="t-panel-title">Orders ({orders.length})</h3>
          {orders.length > 0 && (
            <button className="t-btn t-btn-xs t-btn-ghost" onClick={() => {
              const header = ['Symbol', 'Type', 'Expiry', 'Strike', 'Side', 'Qty', 'Price', 'Filled', 'Avg', 'Status', 'Time']
              const data = orders.map(o => [o.symbol, o.instrument_type || '', o.expiry_date || '', String(o.strike_price || ''), o.side, String(o.quantity), o.price?.toFixed(1) || '', String(o.filled_quantity || 0), o.average_price?.toFixed(1) || '', o.status, o.created_at ? new Date(o.created_at).toISOString() : ''])
              downloadCSV([header, ...data], `orders-${new Date().toISOString().slice(0, 10)}.csv`)
            }}>
              Export CSV
            </button>
          )}
        </div>
        {orders.length > 0 ? (
          <div className="t-table-wrap">
            <table className="t-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Type</th>
                  <th>Expiry</th>
                  <th className="t-num">Strike</th>
                  <th>Side</th>
                  <th className="t-num">Qty</th>
                  <th className="t-num">Price</th>
                  <th className="t-num">Filled</th>
                  <th className="t-num">Avg</th>
                  <th>Status</th>
                  <th>Time</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {orders.map(o => {
                  const ordKey = o.id || `${o.symbol}|${o.created_at}|${o.side}`
                  return (
                    <tr key={ordKey}>
                      <td style={{ fontWeight: 600 }}>{symbolOf(o.symbol)}</td>
                      <td>
                        <span className={`t-badge ${o.instrument_type === 'OPT' ? 't-badge-violet' : o.instrument_type === 'FUT' ? 't-badge-cyan' : 't-badge-green'}`}>
                          {o.instrument_type || 'EQ'}
                        </span>
                      </td>
                      <td className="t-faint" style={{ fontSize: 11 }}>{o.expiry_date || '-'}</td>
                      <td className="t-num">{o.strike_price || '-'}</td>
                      <td className={o.side === 'BUY' ? 't-up' : 't-down'} style={{ fontWeight: 600 }}>{o.side}</td>
                      <td className="t-num">{o.quantity}</td>
                      <td className="t-num">{o.price?.toFixed(1) || '-'}</td>
                      <td className="t-num">{o.filled_quantity || 0}</td>
                      <td className="t-num">{o.average_price?.toFixed(1) || '-'}</td>
                      <td>
                        <span className={`t-badge ${o.status === 'FILLED' ? 't-badge-green' : o.status === 'OPEN' ? 't-badge-cyan' : o.status === 'REJECTED' ? 't-badge-red' : 't-badge-violet'}`}>
                          {o.status}
                        </span>
                      </td>
                      <td className="t-faint t-num" style={{ fontSize: 10 }}>
                        {o.created_at ? new Date(o.created_at).toLocaleTimeString() : '-'}
                      </td>
                      <td>
                        {['OPEN', 'PENDING', 'PARTIALLY_FILLED'].includes(o.status) && (
                          <button className="t-btn t-btn-sm t-btn-danger" onClick={() => cancelOrder(o.id)}>
                            Cancel
                          </button>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="t-panel-body" style={{ textAlign: 'center', padding: 20 }}>
            <span className="t-faint">{loading ? 'Loading...' : 'No orders yet'}</span>
          </div>
        )}
      </div>
    </div>
  )
}

function FragmentRow({ position, ltp, pnl, pnlPct, isOpen, trail, busy, onToggleRow, onAct, onToggleTrail, openOrder }: {
  position: PositionRow
  ltp: number | null
  pnl: number
  pnlPct: number
  isOpen: boolean
  trail: TrailState | null
  busy: boolean
  onToggleRow: () => void
  onAct: (kind: ActionKind, qty: number, extra?: { price?: number; triggerPrice?: number }) => void
  onToggleTrail: (action: 'start' | 'stop', distance?: number) => void
  openOrder: OrderRow | null
}) {
  const p = position
  return (
    <>
      <tr onClick={onToggleRow} style={{ cursor: 'pointer' }}>
        <td style={{ fontWeight: 600 }}>{symbolOf(p.symbol)}{trail && <span className="t-badge t-badge-amber" style={{ fontSize: 8, marginLeft: 6 }}>TRAILING</span>}</td>
        <td>
          <span className={`t-badge ${p.instrument_type === 'OPT' ? 't-badge-violet' : p.instrument_type === 'FUT' ? 't-badge-cyan' : 't-badge-green'}`}>
            {p.instrument_type || 'EQ'}
          </span>
        </td>
        <td className="t-faint" style={{ fontSize: 11 }}>{p.expiry_date || '-'}</td>
        <td className="t-num">{p.strike_price || '-'}</td>
        <td className="t-num">{p.quantity}</td>
        <td className="t-num">{p.average_buy_price?.toFixed(1) || '-'}</td>
        <td className="t-num">{ltp?.toFixed(1) || '-'}</td>
        <td className={`t-num ${pnl >= 0 ? 't-up' : 't-down'}`} style={{ fontWeight: 600 }}>
          {pnl >= 0 ? '+' : ''}{pnl?.toFixed(0) || '0'}
        </td>
        <td className={`t-num ${pnlPct >= 0 ? 't-up' : 't-down'}`}>
          {pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(2)}%
        </td>
        <td className="t-num">
          <span className={`t-badge ${p.product === 'INTRADAY' ? 't-badge-cyan' : 't-badge-violet'}`}>
            {p.product}
          </span>
        </td>
        <td>
          <button className="t-btn t-btn-sm t-btn-ghost" onClick={e => { e.stopPropagation(); onToggleRow() }}>
            {isOpen ? 'Hide' : 'Actions'}
          </button>
        </td>
      </tr>
      {isOpen && (
        <tr>
          <td colSpan={11} style={{ padding: 0 }}>
            <PositionActions
              position={p}
              ltp={ltp}
              openOrder={openOrder}
              trail={trail}
              onAct={onAct}
              onToggleTrail={onToggleTrail}
              busy={busy}
            />
          </td>
        </tr>
      )}
    </>
  )
}