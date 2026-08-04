'use client'

import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { useMarketData, type TickData } from '@/lib/use-market-data'
import { usePolling } from '@/lib/use-polling'
import { useOrders, usePositions } from '@/lib/queries/orders'
import { useBrokerCredentials } from '@/lib/queries/misc'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'
import { useUIStore } from '@/lib/stores/ui-store'
import Logo from '@/components/logo'

interface WatchItem { symbol: string; name: string; type: string }
interface Order {
  id: string; symbol: string; side: string; quantity: number; price: number
  status: string; filled_quantity: number; average_price: number
  created_at: string; is_paper: boolean
}
interface Position {
  symbol: string; exchange: string; quantity: number
  buy_quantity: number; sell_quantity: number
  average_buy_price: number; average_sell_price: number
  unrealised_pnl: number; realised_pnl: number; m2m: number
  product: string; instrument_type: string
}

interface QuoteData { last_price: number; close: number; change_pct: number | null }
interface Credential {
  id: string; broker: string; is_active: boolean
  token_status?: string; token_expires_at?: string; created_at: string
}

const STORAGE_KEY = 'tm_watchlist_custom'

function fmt(n: number) {
  return n.toLocaleString('en-IN', { maximumFractionDigits: 2 })
}
function fmtMoney(n: number) {
  return n.toLocaleString('en-IN', { maximumFractionDigits: 2, minimumFractionDigits: 2 })
}
function shortSymbol(s: string) { return s.split(':').pop() || s }
function timeAgo(iso?: string) {
  if (!iso) return '-'
  const d = new Date(iso)
  const now = Date.now()
  const mins = Math.max(0, Math.floor((now - d.getTime()) / 60000))
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })
}

export default function PortfolioPage() {
  const { user, loading: authLoading } = useAuth()
  const { ticks, subscribe } = useMarketData()
  const openQuickOrder = useUIStore(s => s.openQuickOrder)
  const { data: ordersData } = useOrders()
  const { data: positionsData } = usePositions()
  const { data: credsData } = useBrokerCredentials()
  const [watchItems, setWatchItems] = useState<WatchItem[]>([])
  const [customItems, setCustomItems] = useState<WatchItem[]>([])
  const [now, setNow] = useState<Date | null>(null)
  const [quotes, setQuotes] = useState<Record<string, QuoteData>>({})

  useEffect(() => { setNow(new Date()) }, [])

  const orders = (ordersData as { orders?: Order[] } | undefined)?.orders || []
  const positions = (positionsData as { positions?: Position[] } | undefined)?.positions || []
  const credentials = (credsData as { credentials?: Credential[] } | undefined)?.credentials || []

  const tickChangePct = (t: TickData) => (typeof t.change_pct === 'number' ? t.change_pct : null)

  const refreshQuotes = async () => {
    const syms = Array.from(new Set(positions.map(p => p.symbol).filter(Boolean)))
    if (!syms.length) return
    try {
      const res: any = await api.marketdata.quote(syms)
      const arr = Array.isArray(res) ? res : [res]
      const next: Record<string, QuoteData> = {}
      for (const r of arr) {
        if (!r?.symbol) continue
        const lp = Number(r.last_price || 0)
        const pc = Number(r.close || 0)
        next[r.symbol] = {
          last_price: lp,
          close: pc,
          change_pct: pc > 0 && lp > 0 ? ((lp - pc) / pc) * 100 : null,
        }
      }
      setQuotes(prev => ({ ...prev, ...next }))
    } catch { /* quote poll failures are non-fatal */ }
  }

  const positionQuote = (p: Position) => {
    const t = ticks[p.symbol]
    const q = quotes[p.symbol]
    if (t && t.last_price > 0) {
      const pct = tickChangePct(t)
      if (pct !== null) return { last_price: t.last_price, change_pct: pct }
      if (q && q.last_price > 0) return { last_price: t.last_price, change_pct: q.change_pct }
      return { last_price: t.last_price, change_pct: null }
    }
    return q && q.last_price > 0 ? { last_price: q.last_price, change_pct: q.change_pct } : undefined
  }

  useEffect(() => {
    const syms = positions.map(p => p.symbol).filter(Boolean)
    if (syms.length) subscribe(syms)
  }, [positions, subscribe])

  usePolling(refreshQuotes, 5000)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const data = await api.marketdata.watchlist() as { indices: WatchItem[]; stocks: WatchItem[] }
        if (cancelled) return
        const custom: WatchItem[] = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]')
        const all = [...(data.indices || []), ...(data.stocks || []), ...custom]
        setWatchItems(all)
        setCustomItems(custom)
        subscribe(all.map(i => i.symbol))
      } catch { /* auth or api unavailable */ }
    })()
    return () => { cancelled = true }
  }, [subscribe])

  const unrealisedPnl = useMemo(() => positions.reduce((s, p) => {
    const q = positionQuote(p)
    return s + (q ? p.quantity * (q.last_price - p.average_buy_price) : p.unrealised_pnl || 0)
  }, 0), [positions, ticks, quotes])

  const realisedToday = useMemo(() => {
    const today = new Date().toDateString()
    const fills = orders
      .filter(o => o.status === 'FILLED' && o.filled_quantity > 0 && new Date(o.created_at).toDateString() === today)
      .sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime())
    const book = new Map<string, { qty: number; cost: number }>()
    let total = 0
    for (const o of fills) {
      const b = book.get(o.symbol) || { qty: 0, cost: 0 }
      const px = o.average_price || o.price || 0
      if (o.side === 'BUY') { b.cost += px * o.filled_quantity; b.qty += o.filled_quantity }
      else if (b.qty > 0) { total += (px - b.cost / b.qty) * o.filled_quantity }
      book.set(o.symbol, b)
    }
    return total
  }, [orders])

  const todayPnl = unrealisedPnl + realisedToday
  const todayFills = orders.filter(o => new Date(o.created_at).toDateString() === new Date().toDateString()).length

  const openPositions = positions.filter(p => p.quantity !== 0)
  const closedPositions = positions.filter(p => p.quantity === 0)
  const totalUnrealised = openPositions.reduce((s, p) => s + (p.unrealised_pnl || 0), 0)
  const totalRealised = positions.reduce((s, p) => s + (p.realised_pnl || 0), 0)

  const trades = orders
    .filter(o => o.status === 'FILLED' && o.filled_quantity > 0)
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
    .slice(0, 20)

  const watchRows = useMemo(() => {
    const customSymbols = new Set(customItems.map(i => i.symbol))
    const ranked = [...watchItems].sort((a, b) => {
      const at = ticks[a.symbol]?.last_price || 0
      const bt = ticks[b.symbol]?.last_price || 0
      return bt - at
    })
    return [...ranked.filter(i => customSymbols.has(i.symbol)), ...ranked.filter(i => !customSymbols.has(i.symbol))].slice(0, 12)
  }, [watchItems, customItems, ticks])

  const indices = useMemo(() => watchItems.filter(i => i.type === 'index').slice(0, 8), [watchItems])

  const greeting = now ? (
    now.getHours() < 12 ? 'Good morning' : now.getHours() < 17 ? 'Good afternoon' : 'Good evening'
  ) : ''

  if (!authLoading && !user) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div className="t-panel" style={{ maxWidth: 360, textAlign: 'center' }}>
          <h3 className="t-panel-title" style={{ marginBottom: 8 }}>Sign in required</h3>
          <p className="t-faint" style={{ fontSize: 12, marginBottom: 16 }}>Your portfolio is waiting — sign in to view positions, P&L and quick trade.</p>
          <Link href="/auth" className="t-btn t-btn-primary" style={{ textDecoration: 'none' }}>Sign In</Link>
        </div>
      </div>
    )
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <header style={{
        height: 56, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '0 24px', borderBottom: '1px solid var(--border)', flexShrink: 0,
      }}>
        <Link href="/portfolio" style={{ display: 'flex', alignItems: 'center', gap: 8, textDecoration: 'none', fontFamily: 'var(--font-display)', fontSize: 16, fontWeight: 700 }}>
          <Logo size={22} />
          <span style={{ background: 'var(--gradient-primary)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>TradeMetrix</span>
        </Link>
        <nav style={{ display: 'flex', gap: 14, alignItems: 'center', fontSize: 12, fontWeight: 600 }}>
          <Link href="/marketdata" style={{ color: 'var(--text-sub)', textDecoration: 'none' }}>Market Data</Link>
          <Link href="/trade" style={{ color: 'var(--text-sub)', textDecoration: 'none' }}>Trade</Link>
          <Link href="/portal" style={{ color: 'var(--text-sub)', textDecoration: 'none' }}>Client Portal</Link>
          <span className="t-faint" style={{ fontSize: 11 }}>{user?.full_name || user?.email || ''}</span>
        </nav>
      </header>

      <div style={{ flex: 1, maxWidth: 1080, width: '100%', margin: '0 auto', padding: '20px 24px 40px', display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div>
          <h1 style={{ fontSize: 20, fontWeight: 700, margin: 0, letterSpacing: '-0.02em' }}>Portfolio</h1>
          <div className="t-faint" style={{ fontSize: 12, marginTop: 2 }}>
            {greeting}{user?.full_name ? `, ${user.full_name.split(' ')[0]}` : ''}{greeting ? ' · ' : ''}{now ? now.toLocaleDateString('en-IN', { weekday: 'long', day: '2-digit', month: 'long' }) : ''}
          </div>
        </div>

        <div className="t-grid-2" style={{ gap: 12 }}>
          <div className="t-panel">
            <div className="t-panel-body">
              <div className="t-faint" style={{ fontSize: 10, fontWeight: 700, letterSpacing: '.1em' }}>TODAY'S P&L</div>
              <div className={`t-num ${todayPnl >= 0 ? 't-up' : 't-down'}`} style={{ fontSize: 34, fontWeight: 800, margin: '6px 0' }}>
                {todayPnl >= 0 ? '+' : '−'}₹{fmtMoney(Math.abs(todayPnl))}
              </div>
              <div style={{ display: 'flex', gap: 14, fontSize: 11, flexWrap: 'wrap' }}>
                <span className="t-faint">Unrealised <b className={unrealisedPnl >= 0 ? 't-up' : 't-down'}>{unrealisedPnl >= 0 ? '+' : '−'}₹{fmtMoney(Math.abs(unrealisedPnl))}</b></span>
                <span className="t-faint">Realised today <b className={realisedToday >= 0 ? 't-up' : 't-down'}>{realisedToday >= 0 ? '+' : '−'}₹{fmtMoney(Math.abs(realisedToday))}</b></span>
                <span className="t-faint">{positions.length} open · {todayFills} fills today</span>
              </div>
            </div>
          </div>

          <div className="t-panel">
            <div className="t-panel-body">
              <div className="t-faint" style={{ fontSize: 10, fontWeight: 700, letterSpacing: '.1em', marginBottom: 8 }}>BROKER STATUS</div>
              {credentials.length === 0 ? (
                <div className="t-faint" style={{ fontSize: 12 }}>
                  No broker connected.{' '}
                  <Link href="/brokers" style={{ color: 'var(--cyan)' }}>Connect one</Link>
                </div>
              ) : credentials.map(c => {
                const exp = c.token_expires_at ? new Date(c.token_expires_at) : null
                const daysLeft = exp ? Math.ceil((exp.getTime() - Date.now()) / 86400000) : null
                const tokenOk = c.token_status === 'valid'
                return (
                  <div key={c.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '5px 0', borderBottom: '1px solid rgba(255,255,255,.03)' }}>
                    <div>
                      <span style={{ fontWeight: 700, fontSize: 13, textTransform: 'capitalize' }}>{c.broker}</span>
                      {c.is_active && <span className="t-badge t-badge-green" style={{ marginLeft: 8 }}>ACTIVE</span>}
                    </div>
                    <div style={{ textAlign: 'right' }}>
                      {exp ? (
                        <span className={`t-chip ${tokenOk && daysLeft !== null && daysLeft <= 2 ? 't-chip-warn' : ''}`} style={{ fontSize: 10 }}>
                          {tokenOk ? 'TOKEN VALID' : 'TOKEN EXPIRED'}
                        </span>
                      ) : (
                        <span className="t-chip" style={{ fontSize: 10 }}>NOT SET</span>
                      )}
                      <div className="t-faint" style={{ fontSize: 10, marginTop: 2 }}>
                        {exp ? `expires ${exp.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })}${daysLeft !== null ? ` · ${daysLeft}d` : ''}` : 'no session'}
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </div>

        <div className="t-panel" style={{ padding: 0 }}>
          <div className="t-panel-header">
            <h3 className="t-panel-title">⭐ WATCHLIST</h3>
            <Link href="/marketdata" style={{ fontSize: 11, color: 'var(--cyan)', textDecoration: 'none' }}>View all →</Link>
          </div>
          <div className="t-table-wrap">
            <table className="t-table">
              <thead>
                <tr><th>Symbol</th><th>Name</th><th>LTP</th><th>Change%</th><th></th></tr>
              </thead>
              <tbody>
                {watchRows.map(item => {
                  const t = ticks[item.symbol]
                  const pct = t?.change_pct ?? 0
                  return (
                    <tr key={item.symbol}>
                      <td style={{ fontWeight: 600, fontSize: 10 }}>{shortSymbol(item.symbol)}</td>
                      <td style={{ fontSize: 12 }}>{item.name}</td>
                      <td><span className="t-num">{t?.last_price ? fmt(t.last_price) : '-'}</span></td>
                      <td><span className={`t-num ${pct >= 0 ? 't-up' : 't-down'}`}>{t ? `${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%` : '-'}</span></td>
                      <td>
                        <div style={{ display: 'flex', gap: 4, justifyContent: 'flex-end' }}>
                          <button className="t-btn t-btn-xs" style={{ color: 'var(--green)' }} onClick={() => openQuickOrder(item.symbol, item.name, 'BUY')}>Buy</button>
                          <button className="t-btn t-btn-xs" style={{ color: 'var(--red)' }} onClick={() => openQuickOrder(item.symbol, item.name, 'SELL')}>Sell</button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
                {watchRows.length === 0 && (
                  <tr><td colSpan={5} style={{ textAlign: 'center' }}><span className="t-faint">Loading watchlist…</span></td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className="t-panel" style={{ padding: 0 }}>
          <div className="t-panel-header">
            <h3 className="t-panel-title">Positions ({positions.length})</h3>
            <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
              <span className="t-faint" style={{ fontSize: 10 }}>
                Unrealised <b style={{ color: totalUnrealised >= 0 ? 'var(--text-green)' : 'var(--text-red)' }}>{totalUnrealised >= 0 ? '+' : ''}{totalUnrealised.toFixed(0)}</b>
                {' · '}Realised <b style={{ color: totalRealised >= 0 ? 'var(--text-green)' : 'var(--text-red)' }}>{totalRealised >= 0 ? '+' : ''}{totalRealised.toFixed(0)}</b>
              </span>
            </div>
          </div>
          {positions.length > 0 ? (
            <div className="t-table-wrap" style={{ maxHeight: 320, overflowY: 'auto' }}>
              {openPositions.length > 0 && (
                <>
                  <div style={{ padding: '6px 12px', borderBottom: '1px solid var(--border)', background: 'var(--bg-tertiary)' }}>
                    <span style={{ fontSize: 9, fontWeight: 700, color: 'var(--text-sub)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                      Open Positions ({openPositions.length})
                    </span>
                  </div>
                  <table className="t-table">
                    <thead>
                      <tr>
                        <th>Symbol</th><th className="num">Qty</th><th className="num">Buy</th>
                        <th className="num">LTP</th><th className="num">Chg%</th><th className="num">Unrealised P&L</th>
                      </tr>
                    </thead>
                    <tbody>
                      {openPositions.map(p => {
                        const q = positionQuote(p)
                        const ltp = q?.last_price || p.average_buy_price || 0
                        const pnl = q ? (p.quantity * (ltp - p.average_buy_price)) : (p.unrealised_pnl || 0)
                        const chg = q?.change_pct ?? null
                        const base = p.quantity * p.average_buy_price
                        const pnlPct = base !== 0 ? (pnl / base) * 100 : 0
                        return (
                          <tr key={p.symbol}>
                            <td style={{ fontWeight: 600, fontSize: 12 }}>{shortSymbol(p.symbol)}</td>
                            <td className="t-num">{p.quantity}</td>
                            <td className="t-num">{(p.average_buy_price || 0).toFixed(1)}</td>
                            <td className="t-num">{ltp > 0 ? ltp.toFixed(1) : '—'}</td>
                            <td className={`t-num ${chg !== null && chg !== undefined ? (chg >= 0 ? 't-up' : 't-down') : ''}`}>
                              {chg !== null && chg !== undefined ? `${chg >= 0 ? '+' : ''}${chg.toFixed(2)}%` : '—'}
                            </td>
                            <td className={`t-num ${(pnl || 0) >= 0 ? 't-up' : 't-down'}`} style={{ fontWeight: 700 }}>
                              {(pnl || 0) >= 0 ? '+' : ''}{(pnl || 0).toFixed(0)}
                              <span className="t-faint" style={{ fontSize: 9, marginLeft: 4 }}>({(pnlPct >= 0 ? '+' : '')}{pnlPct.toFixed(1)}%)</span>
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </>
              )}
              {closedPositions.length > 0 && (
                <>
                  <div style={{ padding: '6px 12px', borderBottom: '1px solid var(--border)', background: 'var(--bg-tertiary)' }}>
                    <span style={{ fontSize: 9, fontWeight: 700, color: 'var(--text-sub)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                      Closed Today ({closedPositions.length})
                    </span>
                  </div>
                  <table className="t-table">
                    <thead>
                      <tr>
                        <th>Symbol</th><th className="num">Buy Qty</th><th className="num">Avg Buy</th>
                        <th className="num">Avg Sell</th><th className="num">Realised P&L</th>
                      </tr>
                    </thead>
                    <tbody>
                      {closedPositions.map(p => (
                        <tr key={p.symbol}>
                          <td style={{ fontWeight: 600, fontSize: 12 }}>{shortSymbol(p.symbol)}</td>
                          <td className="t-num">{p.buy_quantity || p.sell_quantity || 0}</td>
                          <td className="t-num">{(p.average_buy_price || 0).toFixed(1)}</td>
                          <td className="t-num">{(p.average_sell_price || 0).toFixed(1)}</td>
                          <td className={`t-num ${(p.realised_pnl || 0) >= 0 ? 't-up' : 't-down'}`} style={{ fontWeight: 700 }}>
                            {(p.realised_pnl || 0) >= 0 ? '+' : ''}{(p.realised_pnl || 0).toFixed(0)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </>
              )}
            </div>
          ) : (
            <div className="t-panel-body">
              <p className="t-faint" style={{ fontSize: 12, margin: 0 }}>No positions yet — your open and closed positions will appear here.</p>
            </div>
          )}
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, alignItems: 'start' }}>
          <div className="t-panel" style={{ padding: 0 }}>
            <div className="t-panel-header">
              <h3 className="t-panel-title">Trade History</h3>
              <span className="t-faint" style={{ fontSize: 10 }}>{trades.length} executed</span>
            </div>
            <div className="t-table-wrap" style={{ maxHeight: 300, overflowY: 'auto' }}>
              <table className="t-table">
                <thead>
                  <tr><th>Symbol</th><th>Side</th><th>Qty</th><th>Price</th><th>Time</th></tr>
                </thead>
                <tbody>
                  {trades.map(o => (
                    <tr key={o.id}>
                      <td style={{ fontSize: 11, fontWeight: 600 }}>{shortSymbol(o.symbol)}</td>
                      <td><span className={o.side === 'BUY' ? 't-up' : 't-down'} style={{ fontWeight: 700, fontSize: 10 }}>{o.side}</span></td>
                      <td><span className="t-num">{o.filled_quantity}</span></td>
                      <td><span className="t-num">{o.average_price ? fmt(o.average_price) : o.price ? fmt(o.price) : '-'}</span></td>
                      <td><span className="t-faint" style={{ fontSize: 10 }}>{timeAgo(o.created_at)}</span></td>
                    </tr>
                  ))}
                  {trades.length === 0 && (
                    <tr><td colSpan={5} style={{ textAlign: 'center' }}><span className="t-faint">No trades yet</span></td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div className="t-panel" style={{ padding: 0 }}>
            <div className="t-panel-header"><h3 className="t-panel-title">Recent Orders</h3></div>
            <div className="t-table-wrap" style={{ maxHeight: 300, overflowY: 'auto' }}>
              <table className="t-table">
                <thead>
                  <tr><th>Symbol</th><th>Side</th><th>Qty</th><th>Price</th><th>Status</th><th>Time</th></tr>
                </thead>
                <tbody>
                  {orders.slice(0, 12).map(o => (
                    <tr key={o.id}>
                      <td style={{ fontSize: 11, fontWeight: 600 }}>{shortSymbol(o.symbol)}</td>
                      <td><span className={o.side === 'BUY' ? 't-up' : 't-down'} style={{ fontWeight: 700, fontSize: 10 }}>{o.side}</span></td>
                      <td><span className="t-num">{o.filled_quantity || o.quantity}</span></td>
                      <td><span className="t-num">{o.average_price ? fmt(o.average_price) : o.price ? fmt(o.price) : '-'}</span></td>
                      <td>
                        <span className={`t-chip ${o.status === 'FILLED' ? '' : 't-chip-warn'}`} style={{ fontSize: 9 }}>
                          {o.status === 'FILLED' ? 'FILLED' : o.status === 'REJECTED' ? 'REJECTED' : o.status}
                        </span>
                        {o.is_paper && <span className="t-badge t-badge-amber" style={{ marginLeft: 4 }}>PAPER</span>}
                      </td>
                      <td><span className="t-faint" style={{ fontSize: 10 }}>{timeAgo(o.created_at)}</span></td>
                    </tr>
                  ))}
                  {orders.length === 0 && (
                    <tr><td colSpan={6} style={{ textAlign: 'center' }}><span className="t-faint">No orders yet</span></td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <div>
          <div className="t-faint" style={{ fontSize: 10, fontWeight: 700, letterSpacing: '.1em', marginBottom: 8 }}>MARKET SUMMARY</div>
          <div className="t-grid-3" style={{ gap: 8 }}>
            {indices.map(item => {
              const t = ticks[item.symbol]
              const pct = t?.change_pct ?? 0
              return (
                <div key={item.symbol} className="t-panel" style={{ padding: '10px 14px' }}>
                  <div className="t-faint" style={{ fontSize: 10, marginBottom: 2 }}>{item.name}</div>
                  <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                    <span className="t-num" style={{ fontSize: 15, fontWeight: 700 }}>{t?.last_price ? fmt(t.last_price) : '—'}</span>
                    <span className={`t-num ${pct >= 0 ? 't-up' : 't-down'}`} style={{ fontSize: 10 }}>{t ? `${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%` : ''}</span>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </div>
  )
}
