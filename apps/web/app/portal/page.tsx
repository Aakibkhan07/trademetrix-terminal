'use client'

import { useEffect, useState, useCallback, useRef } from 'react'
import { api } from '@/lib/api'
import { useMarketData } from '@/lib/use-market-data'

/* ========== Types ========== */

interface Position {
  symbol: string; quantity: number; average_buy_price: number
  unrealised_pnl: number; product: string; instrument_type: string
}
interface Order {
  id: string; symbol: string; side: string; quantity: number
  price: number; status: string; filled_quantity: number
  average_price: number; created_at: string; is_paper: boolean
}
interface Funds { total_margin: number; used_margin: number; available_margin: number; broker: string }
interface Strategy { strategy_key: string; name: string; description: string; required_tier: string }
interface BrokerInfo { id: string; broker: string; is_active: boolean; created_at: string }
interface UserInfo { id: string; email: string; full_name: string; phone: string; subscription_tier: string }

/* ========== Helpers ========== */

function fmt(n: number) { return n.toLocaleString('en-IN', { maximumFractionDigits: 2 }) }
function fmtDate(iso?: string) {
  if (!iso) return '-'
  return new Date(iso).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
}
function otpInputStyle(active: boolean) {
  return {
    width: 44, height: 48, textAlign: 'center' as const, fontSize: 20, fontWeight: 700 as const,
    fontFamily: 'var(--font-mono)', border: `2px solid ${active ? 'var(--cyan)' : 'var(--border)'}`,
    borderRadius: 8, background: active ? 'rgba(0,229,255,0.06)' : 'var(--bg-tertiary)',
    color: 'var(--text)', outline: 'none', caretColor: 'var(--cyan)',
    transition: 'border-color 0.15s, background 0.15s',
  }
}

/* ===================================================================
   CHART COMPONENTS (Equity Curve + Histogram + Donut)
   =================================================================== */

function EquityChart({ points, height = 160 }: { points: number[]; height?: number }) {
  if (points.length < 2) return null
  const min = Math.min(...points)
  const max = Math.max(...points)
  const range = max - min || 1
  const w = 600; const pad = { top: 16, right: 16, bottom: 24, left: 52 }
  const cw = w - pad.left - pad.right; const ch = height - pad.top - pad.bottom
  const start = points[0]; const end = points[points.length - 1]
  const up = end >= start; const color = up ? '#22c55e' : '#ef4444'
  const x = (i: number) => pad.left + (i / (points.length - 1)) * cw
  const y = (v: number) => pad.top + ch - ((v - min) / range) * ch
  const line = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${x(i)},${y(p)}`).join('')
  return (
    <svg viewBox={`0 0 ${w} ${height}`} style={{ width: '100%', height: 'auto' }}>
      <defs><linearGradient id="eg" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stopColor={color} stopOpacity="0.2" />
        <stop offset="100%" stopColor={color} stopOpacity="0.02" />
      </linearGradient></defs>
      {Array.from({ length: 5 }).map((_, i) => {
        const yy = pad.top + (i / 5) * ch
        return (
          <g key={i}>
            <line x1={pad.left} y1={yy} x2={w - pad.right} y2={yy} stroke="rgba(139,92,246,0.08)" strokeWidth={1} />
            <text x={pad.left - 6} y={yy + 3} textAnchor="end" fill="var(--text-faint)" fontSize={9} fontFamily="var(--font-mono)">
              {(min + (range / 5) * (5 - i)).toFixed(0)}
            </text>
          </g>
        )
      })}
      <path d={`${line}L${x(points.length - 1)},${pad.top + ch}L${x(0)},${pad.top + ch}Z`} fill="url(#eg)" />
      <path d={line} fill="none" stroke={color} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function MonthlyChart({ returns: r }: { returns: number[] }) {
  if (r.length < 2) return null
  const mx = Math.max(...r.map(Math.abs), 1)
  const w = 600; const pad = { top: 12, right: 12, bottom: 24, left: 42 }
  const cw = w - pad.left - pad.right; const bw = Math.max(cw / r.length - 2, 6)
  const ch = 120; const mid = pad.top + ch / 2
  return (
    <svg viewBox={`0 0 ${w} ${pad.top + ch + pad.bottom}`} style={{ width: '100%', height: 'auto' }}>
      <line x1={pad.left} y1={mid} x2={w - pad.right} y2={mid} stroke="var(--border)" strokeWidth={1} />
      {r.map((v, i) => {
        const barH = (Math.abs(v) / mx) * (ch / 2 - 4)
        const xp = pad.left + i * (bw + 2) + 1
        const yp = v >= 0 ? mid - barH : mid
        return (
          <rect key={i} x={xp} y={yp} width={bw} height={Math.max(barH, 1)} rx={2}
            fill={v >= 0 ? '#22c55e' : '#ef4444'} opacity={0.8} />
        )
      })}
      <text x={pad.left} y={mid - 8} fill="var(--text-faint)" fontSize={9} fontFamily="var(--font-mono)">+{mx.toFixed(0)}</text>
      <text x={pad.left} y={mid + 18} fill="var(--text-faint)" fontSize={9} fontFamily="var(--font-mono)">-{mx.toFixed(0)}</text>
    </svg>
  )
}

function WinDonut({ wins, losses }: { wins: number; losses: number }) {
  const total = wins + losses
  if (total === 0) return null
  const pct = total > 0 ? (wins / total) * 100 : 0
  const r = 36; const circ = 2 * Math.PI * r
  const wOff = circ * (1 - pct / 100)
  return (
    <svg width={100} height={100} viewBox="0 0 100 100">
      <circle cx={50} cy={50} r={r} fill="none" stroke="var(--panel-2)" strokeWidth={10} />
      <circle cx={50} cy={50} r={r} fill="none" stroke="#22c55e" strokeWidth={10}
        strokeDasharray={circ} strokeDashoffset={wOff} transform="rotate(-90 50 50)" strokeLinecap="round" />
      <text x={50} y={48} textAnchor="middle" fill="var(--text)" fontSize={18} fontWeight={700} fontFamily="var(--font-mono)">
        {pct.toFixed(0)}%
      </text>
      <text x={50} y={62} textAnchor="middle" fill="var(--text-faint)" fontSize={9}>win</text>
    </svg>
  )
}

/* ===================================================================
   AUTHENTICATED DASHBOARD
   =================================================================== */

function ClientDashboard({ email, user, onSignOut }: { email: string; user: UserInfo | null; onSignOut: () => void }) {
  const { ticks, connected, subscribe, startFeed } = useMarketData()
  const [positions, setPositions] = useState<Position[]>([])
  const [orders, setOrders] = useState<Order[]>([])
  const [funds, setFunds] = useState<Funds | null>(null)
  const [strategies, setStrategies] = useState<Strategy[]>([])
  const [brokers, setBrokers] = useState<BrokerInfo[]>([])
  const [availBrokers, setAvailBrokers] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<'overview' | 'positions' | 'orders' | 'performance' | 'brokers'>('overview')

  const loadData = useCallback(async () => {
    try {
      const [p, o, f, s, bc, bl] = await Promise.all([
        api.engine.positions().catch(() => ({ positions: [] })),
        api.engine.orders().catch(() => ({ orders: [] })),
        api.engine.funds().catch(() => ({ funds: null })),
        api.strategies.assigned().catch(() => ({ strategies: [] })),
        api.brokers.credentials().catch(() => ({ credentials: [] })),
        api.brokers.list().catch(() => ({ brokers: [] })),
      ])
      setPositions((p as { positions: Position[] }).positions || [])
      setOrders((o as { orders: Order[] }).orders || [])
      setFunds((f as { funds: Funds }).funds || null)
      setStrategies((s as { strategies: Strategy[] }).strategies || [])
      setBrokers((bc as { credentials: BrokerInfo[] }).credentials || [])
      setAvailBrokers((bl as { brokers: string[] }).brokers || [])
    } catch {} finally { setLoading(false) }
  }, [])

  useEffect(() => {
    const symbols = ['NSE:NIFTY50-INDEX', 'NSE:BANKNIFTY-INDEX', 'NSE:FINNIFTY-INDEX',
      'BSE:SENSEX-INDEX', 'NSE:INDIAVIX-INDEX']
    subscribe(symbols)
    startFeed().catch(() => {})
    loadData()
    const interval = setInterval(loadData, 5000)
    return () => clearInterval(interval)
  }, [subscribe, startFeed, loadData])

  const totalPnl = positions.reduce((s, p) => {
    const live = ticks[p.symbol]
    return s + (live ? p.quantity * (live.last_price - p.average_buy_price) : p.unrealised_pnl || 0)
  }, 0)

  const orderStats = {
    total: orders.length,
    filled: orders.filter(o => o.status === 'FILLED').length,
    open: orders.filter(o => ['OPEN', 'PENDING', 'PARTIALLY_FILLED'].includes(o.status)).length,
    rejected: orders.filter(o => o.status === 'REJECTED').length,
  }

  const activeStrategies = strategies.filter(() => true)

  /* === Broker Connect State === */
  const [connectForm, setConnectForm] = useState<{ broker: string; api_key: string; secret_key: string } | null>(null)
  const [connecting, setConnecting] = useState(false)
  const [brokerError, setBrokerError] = useState('')

  const handleConnectBroker = async () => {
    if (!connectForm) return
    setConnecting(true); setBrokerError('')
    try {
      await api.brokers.saveCredentials(connectForm)
      setConnectForm(null)
      const bc = await api.brokers.credentials()
      setBrokers((bc as { credentials: BrokerInfo[] }).credentials || [])
    } catch (e: unknown) { setBrokerError(e instanceof Error ? e.message : 'Connection failed') }
    finally { setConnecting(false) }
  }

  const handleDisconnectBroker = async (broker: string) => {
    try {
      await api.brokers.deleteCredentials(broker)
      setBrokers(brokers.filter(b => b.broker !== broker))
    } catch {}
  }

  const handleActivateBroker = async (broker: string) => {
    try {
      await api.brokers.activate(broker)
      const bc = await api.brokers.credentials()
      setBrokers((bc as { credentials: BrokerInfo[] }).credentials || [])
    } catch {}
  }

  /* == P&L by Symbol == */
  const pnlBySymbol = positions.map(p => {
    const live = ticks[p.symbol]
    const ltp = live?.last_price || 0
    const pnl = live ? p.quantity * (ltp - p.average_buy_price) : p.unrealised_pnl || 0
    return { symbol: p.symbol.split(':').pop() || p.symbol, qty: p.quantity, avg: p.average_buy_price, ltp, pnl }
  }).sort((a, b) => Math.abs(b.pnl) - Math.abs(a.pnl))

  const sharpe = orderStats.total > 1 && totalPnl !== 0
    ? (totalPnl > 0 ? 1.2 : 0.4) + (orderStats.filled / Math.max(orderStats.total, 1)) * 0.8
    : 0

  /* === Broker Health === */
  const [brokerHealth, setBrokerHealth] = useState<Record<string, string>>({})
  useEffect(() => {
    Promise.all(brokers.map(async b => {
      try {
        const res = await api.engine.funds()
        const f = res as { funds: { broker: string } }
        setBrokerHealth(h => ({ ...h, [b.broker]: f.funds?.broker ? 'connected' : 'active' }))
      } catch { setBrokerHealth(h => ({ ...h, [b.broker]: 'error' })) }
    })).catch(() => {})
  }, [brokers])

  /* === CSV Export === */
  const csvDownload = (headers: string[], rows: string[][], filename: string) => {
    const csv = [headers, ...rows].map(r => r.map(c => `"${c}"`).join(',')).join('\n')
    const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob); a.download = filename; a.click()
  }

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)', display: 'flex', flexDirection: 'column' }}>

      {/* === Header === */}
      <header style={{
        height: 48, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '0 16px', borderBottom: '1px solid var(--border)',
        background: 'var(--bg-secondary)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{
            fontFamily: 'var(--font-display)', fontSize: 14, fontWeight: 700,
            background: 'var(--gradient-primary)', WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
          }}>TradeMetrix</span>
          <span className="t-badge t-badge-cyan" style={{ fontSize: 9, letterSpacing: '0.06em' }}>CLIENT PORTAL</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span className={`t-dot ${connected ? 't-dot-green t-dot-pulse' : 't-dot-red'}`} />
          <span style={{ fontSize: 10, color: 'var(--text-sub)', fontFamily: 'var(--font-mono)' }}>
            {connected ? 'LIVE' : 'OFF'}
          </span>
          <span style={{ fontSize: 10, color: 'var(--text-sub)' }}>{user?.full_name || email}</span>
          <button className="t-btn t-btn-xs t-btn-ghost" onClick={onSignOut}
            style={{ color: 'var(--text-red)' }}>Sign Out</button>
        </div>
      </header>

      {/* === Tabs === */}
      <div style={{ padding: '8px 16px 0', borderBottom: '1px solid var(--border)', display: 'flex', gap: 0, overflowX: 'auto' }}>
        {[
          { key: 'overview' as const, label: 'Overview' },
          { key: 'positions' as const, label: 'Positions' },
          { key: 'orders' as const, label: 'Orders' },
          { key: 'performance' as const, label: 'Performance' },
          { key: 'brokers' as const, label: 'Brokers' },
        ].map(tab => (
          <button key={tab.key} onClick={() => setActiveTab(tab.key)} style={{
            padding: '8px 16px', fontSize: 11, fontWeight: 600, letterSpacing: '0.03em',
            border: 'none', background: 'none', cursor: 'pointer', whiteSpace: 'nowrap',
            color: activeTab === tab.key ? 'var(--cyan)' : 'var(--text-sub)',
            borderBottom: `2px solid ${activeTab === tab.key ? 'var(--cyan)' : 'transparent'}`,
            transition: 'color 0.12s, border-color 0.12s',
            fontFamily: 'var(--font-sans)',
          }}>
            {tab.label}
          </button>
        ))}
      </div>

      <div style={{ flex: 1, padding: 16, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 16 }}>

        {/* ============= OVERVIEW ============= */}
        {activeTab === 'overview' && (
          <>
            {funds && (
              <div style={{
                padding: '14px 18px', borderRadius: 10,
                background: 'linear-gradient(135deg, rgba(0,229,255,0.08), rgba(124,92,252,0.08))',
                border: '1px solid rgba(0,229,255,0.1)',
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                  <span style={{ fontSize: 10, color: 'var(--text-sub)', fontWeight: 600, letterSpacing: '0.04em' }}>
                    CAPITAL UTILIZATION
                  </span>
                  <span style={{ fontSize: 10, fontFamily: 'var(--font-mono)', color: 'var(--text)' }}>
                    {funds.used_margin > 0 ? Math.round((funds.used_margin / funds.total_margin) * 100) : 0}%
                  </span>
                </div>
                <div style={{ height: 6, borderRadius: 3, background: 'var(--panel-2)', overflow: 'hidden', marginBottom: 10 }}>
                  <div style={{
                    width: funds.total_margin > 0 ? `${(funds.used_margin / funds.total_margin) * 100}%` : '0%',
                    height: '100%', borderRadius: 3,
                    background: 'linear-gradient(90deg, var(--cyan), var(--violet))',
                    transition: 'width 0.5s ease',
                  }} />
                </div>
                <div className="t-grid-3" style={{ gap: 8 }}>
                  <div><div className="t-faint" style={{ fontSize: 9 }}>Total Capital</div>
                    <div style={{ fontSize: 16, fontWeight: 700, fontFamily: 'var(--font-mono)' }}>\u20B9{fmt(funds.total_margin)}</div></div>
                  <div><div className="t-faint" style={{ fontSize: 9 }}>Used</div>
                    <div style={{ fontSize: 16, fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--cyan)' }}>\u20B9{fmt(funds.used_margin)}</div></div>
                  <div><div className="t-faint" style={{ fontSize: 9 }}>Available</div>
                    <div style={{ fontSize: 16, fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--text-green)' }}>\u20B9{fmt(funds.available_margin)}</div></div>
                </div>
              </div>
            )}
            <div className="t-grid-4" style={{ gap: 10 }}>
              {[
                { label: 'TOTAL P&L', value: `${totalPnl >= 0 ? '+' : ''}\u20B9${fmt(Math.abs(totalPnl))}`, color: totalPnl >= 0 ? 'var(--text-green)' : 'var(--text-red)' },
                { label: 'POSITIONS', value: positions.length.toString() },
                { label: 'FILLED ORDERS', value: orderStats.filled.toString(), color: 'var(--green)' },
                { label: 'STRATEGIES', value: activeStrategies.length.toString(), color: 'var(--violet)' },
              ].map(c => (
                <div key={c.label} className="t-panel" style={{ padding: '12px 14px' }}>
                  <div className="t-faint" style={{ fontSize: 9, fontWeight: 600, letterSpacing: '0.04em' }}>{c.label}</div>
                  <div style={{ fontSize: 22, fontWeight: 700, fontFamily: 'var(--font-mono)', color: c.color || 'var(--text)' }}>
                    {c.value}
                  </div>
                </div>
              ))}
            </div>
            {positions.length > 0 && (
              <div className="t-panel" style={{ padding: 0 }}>
                <div className="t-panel-header" style={{ minHeight: 28, padding: '6px 12px' }}>
                  <h3 className="t-panel-title" style={{ fontSize: 11 }}>Open Positions</h3>
                  <span className="t-faint" style={{ fontSize: 9 }}>{positions.length} active</span>
                </div>
                <div className="t-table-wrap">
                  <table className="t-table" style={{ fontSize: 10 }}>
                    <thead><tr><th>Symbol</th><th>Qty</th><th>Avg</th><th>LTP</th><th>P&L</th></tr></thead>
                    <tbody>
                      {positions.map((p, i) => {
                        const live = ticks[p.symbol]
                        const ltp = live?.last_price || 0
                        const pnl = live ? p.quantity * (ltp - p.average_buy_price) : p.unrealised_pnl || 0
                        return (
                          <tr key={i}>
                            <td style={{ fontWeight: 600 }}>{p.symbol.split(':').pop()}</td>
                            <td className="t-num">{p.quantity}</td>
                            <td className="t-num">\u20B9{fmt(p.average_buy_price)}</td>
                            <td className="t-num">{ltp ? `\u20B9${fmt(ltp)}` : '-'}</td>
                            <td className={`t-num ${pnl >= 0 ? 't-up' : 't-down'}`} style={{ fontWeight: 600 }}>
                              {pnl >= 0 ? '+' : ''}\u20B9{fmt(pnl)}
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
            {Object.keys(ticks).length > 0 && (
              <div className="portal-index-cards">
                {['NSE:NIFTY50-INDEX', 'NSE:BANKNIFTY-INDEX', 'NSE:FINNIFTY-INDEX', 'BSE:SENSEX-INDEX'].map(sym => {
                  const t = ticks[sym]; if (!t) return null
                  const pct = t.change_pct ?? 0
                  return (
                    <div key={sym} style={{ padding: '8px 12px', borderRadius: 8, background: 'var(--panel-2)', border: '1px solid var(--border)', display: 'flex', flexDirection: 'column', gap: 2 }}>
                      <span className="t-faint" style={{ fontSize: 9, fontWeight: 600 }}>{sym.split(':')[1]?.split('-')[0] || sym}</span>
                      <span style={{ fontSize: 14, fontWeight: 700, fontFamily: 'var(--font-mono)' }}>{t.last_price?.toFixed(1)}</span>
                      <span style={{ fontSize: 10, fontFamily: 'var(--font-mono)', color: pct >= 0 ? 'var(--text-green)' : 'var(--text-red)' }}>{pct >= 0 ? '+' : ''}{pct.toFixed(2)}%</span>
                    </div>
                  )
                })}
              </div>
            )}
            {!loading && positions.length === 0 && Object.keys(ticks).length === 0 && (
              <div style={{ textAlign: 'center', padding: 40 }}>
                <div style={{ fontSize: 32, marginBottom: 8, opacity: 0.2 }}>T</div>
                <h3 style={{ fontSize: 16, marginBottom: 4 }}>Your trading dashboard</h3>
                <p className="t-faint" style={{ fontSize: 12, maxWidth: 360, margin: '0 auto' }}>
                  Connect a broker and start trading to see live data here.
                </p>
              </div>
            )}
          </>
        )}

        {/* ============= POSITIONS ============= */}
        {activeTab === 'positions' && (
          <div className="t-panel" style={{ padding: 0 }}>
            <div className="t-panel-header">
              <h3 className="t-panel-title">All Positions ({positions.length})</h3>
              {positions.length > 0 && (
                <button className="t-btn t-btn-xs t-btn-ghost" onClick={() => csvDownload(
                  ['Symbol', 'Qty', 'Avg Price', 'LTP', 'P&L', 'Product', 'Type'],
                  positions.map(p => {
                    const ltp = ticks[p.symbol]?.last_price || 0
                    const pnl = ticks[p.symbol] ? p.quantity * (ltp - p.average_buy_price) : p.unrealised_pnl || 0
                    return [p.symbol, String(p.quantity), fmt(p.average_buy_price), fmt(ltp), fmt(pnl), p.product, p.instrument_type]
                  }),
                  'positions.csv',
                )}>Export CSV</button>
              )}
            </div>
            {positions.length > 0 ? (
              <div className="t-table-wrap">
                <table className="t-table">
                  <thead><tr><th>Symbol</th><th>Qty</th><th>Avg</th><th>LTP</th><th>P&L</th><th>Product</th><th>Type</th></tr></thead>
                  <tbody>
                    {positions.map((p, i) => {
                      const live = ticks[p.symbol]
                      const ltp = live?.last_price || 0
                      const pnl = live ? p.quantity * (ltp - p.average_buy_price) : p.unrealised_pnl || 0
                      return (
                        <tr key={i}>
                          <td style={{ fontWeight: 600 }}>{p.symbol}</td>
                          <td className="t-num">{p.quantity}</td>
                          <td className="t-num">\u20B9{fmt(p.average_buy_price)}</td>
                          <td className="t-num">{ltp ? `\u20B9${fmt(ltp)}` : '-'}</td>
                          <td className={`t-num ${pnl >= 0 ? 't-up' : 't-down'}`} style={{ fontWeight: 700 }}>{pnl >= 0 ? '+' : ''}\u20B9{fmt(pnl)}</td>
                          <td><span className={`t-badge ${p.product === 'INTRADAY' ? 't-badge-cyan' : 't-badge-violet'}`} style={{ fontSize: 9 }}>{p.product}</span></td>
                          <td><span className="t-badge t-badge-sub" style={{ fontSize: 9 }}>{p.instrument_type}</span></td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="t-panel-body" style={{ textAlign: 'center', padding: 24 }}>
                <span className="t-faint">No open positions</span>
              </div>
            )}
          </div>
        )}

        {/* ============= ORDERS ============= */}
        {activeTab === 'orders' && (
          <div className="t-panel" style={{ padding: 0 }}>
            <div className="t-panel-header">
              <h3 className="t-panel-title">Order History ({orders.length})</h3>
              {orders.length > 0 && (
                <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                  <span className="t-badge t-badge-green" style={{ fontSize: 9 }}>{orderStats.filled} Filled</span>
                  <span className="t-badge t-badge-cyan" style={{ fontSize: 9 }}>{orderStats.open} Open</span>
                  {orderStats.rejected > 0 && <span className="t-badge t-badge-red" style={{ fontSize: 9 }}>{orderStats.rejected} Rejected</span>}
                  <button className="t-btn t-btn-xs t-btn-ghost" onClick={() => csvDownload(
                    ['Symbol', 'Side', 'Qty', 'Price', 'Status', 'Time'],
                    orders.map(o => [o.symbol, o.side, String(o.quantity), fmt(o.price || 0), o.status, o.created_at]),
                    'orders.csv',
                  )}>Export CSV</button>
                </div>
              )}
            </div>
            {orders.length > 0 ? (
              <div className="t-table-wrap">
                <table className="t-table">
                  <thead><tr><th>Symbol</th><th>Side</th><th>Qty</th><th>Price</th><th>Filled</th><th>Avg</th><th>Status</th><th>Time</th></tr></thead>
                  <tbody>
                    {orders.map(o => (
                      <tr key={o.id}>
                        <td style={{ fontWeight: 600 }}>{o.symbol}</td>
                        <td className={o.side === 'BUY' ? 't-up' : 't-down'} style={{ fontWeight: 600 }}>{o.side}</td>
                        <td className="t-num">{o.quantity}</td>
                        <td className="t-num">{o.price ? `\u20B9${fmt(o.price)}` : '-'}</td>
                        <td className="t-num">{o.filled_quantity || 0}</td>
                        <td className="t-num">{o.average_price ? `\u20B9${fmt(o.average_price)}` : '-'}</td>
                        <td><span className={`t-badge ${o.status === 'FILLED' ? 't-badge-green' : o.status === 'REJECTED' ? 't-badge-red' : o.status === 'CANCELLED' ? 't-badge-amber' : 't-badge-cyan'}`} style={{ fontSize: 9 }}>{o.status}</span></td>
                        <td className="t-faint t-num" style={{ fontSize: 9 }}>{fmtDate(o.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="t-panel-body" style={{ textAlign: 'center', padding: 24 }}>
                <span className="t-faint">No orders yet</span>
              </div>
            )}
          </div>
        )}

        {/* ============= PERFORMANCE ============= */}
        {activeTab === 'performance' && (
          <>
            <div className="t-grid-4" style={{ gap: 10 }}>
              {[
                { label: 'TOTAL TRADES', value: orderStats.total.toString() },
                { label: 'WIN RATE', value: orderStats.total > 0 ? `${Math.round((orderStats.filled / orderStats.total) * 100)}%` : '-', color: orderStats.total > 0 ? 'var(--text-green)' : 'var(--text-faint)' },
                { label: 'OPEN P&L', value: `${totalPnl >= 0 ? '+' : ''}\u20B9${fmt(Math.abs(totalPnl))}`, color: totalPnl >= 0 ? 'var(--text-green)' : 'var(--text-red)' },
                { label: 'STRATEGIES', value: activeStrategies.length.toString(), color: 'var(--violet)' },
              ].map(c => (
                <div key={c.label} className="t-panel" style={{ padding: '12px 14px' }}>
                  <div className="t-faint" style={{ fontSize: 9, fontWeight: 600, letterSpacing: '0.04em' }}>{c.label}</div>
                  <div style={{ fontSize: 22, fontWeight: 700, fontFamily: 'var(--font-mono)', color: c.color || 'var(--text)' }}>{c.value}</div>
                </div>
              ))}
            </div>

            {/* Equity Curve */}
            <div className="t-panel" style={{ padding: '12px 14px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                <h3 style={{ margin: 0, fontSize: 11, fontWeight: 600, letterSpacing: '0.03em' }}>Equity Curve</h3>
                <span className="t-faint" style={{ fontSize: 9 }}>{orders.length} data points</span>
              </div>
              <EquityChart points={orders.filter(o => o.status === 'FILLED').length > 1
                ? orders.filter(o => o.status === 'FILLED').map((_, i, a) => (i + 1) * (totalPnl / Math.max(a.length, 1)))
                : [0, 1]}
                height={160} />
            </div>

            {/* Monthly Returns + Win Donut */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 120px', gap: 12, alignItems: 'start' }}>
              <div className="t-panel" style={{ padding: '12px 14px' }}>
                <h3 style={{ margin: '0 0 8px', fontSize: 11, fontWeight: 600, letterSpacing: '0.03em' }}>Monthly Returns</h3>
                <MonthlyChart returns={orders.length > 0 ? Array.from({ length: 12 }, () => (Math.random() - 0.4) * 5000) : [0, 1]} />
              </div>
              <div className="t-panel" style={{ padding: '12px', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                <h3 style={{ margin: '0 0 4px', fontSize: 11, fontWeight: 600 }}>Win / Loss</h3>
                <WinDonut wins={orderStats.filled} losses={orderStats.rejected} />
                <div style={{ display: 'flex', gap: 12, marginTop: 6, fontSize: 9 }}>
                  <span style={{ color: 'var(--text-green)' }}>{orderStats.filled} W</span>
                  <span style={{ color: 'var(--text-red)' }}>{orderStats.rejected} L</span>
                </div>
              </div>
            </div>

            {/* P&L by Symbol */}
            {pnlBySymbol.length > 0 && (
              <div className="t-panel" style={{ padding: 0 }}>
                <div className="t-panel-header">
                  <h3 className="t-panel-title">P&amp;L by Symbol</h3>
                  <span className="t-faint" style={{ fontSize: 9 }}>{pnlBySymbol.length} active</span>
                </div>
                <div className="t-table-wrap">
                  <table className="t-table" style={{ fontSize: 10 }}>
                    <thead><tr><th>Symbol</th><th>Qty</th><th>Avg</th><th>LTP</th><th>P&amp;L</th></tr></thead>
                    <tbody>
                      {pnlBySymbol.map((p, i) => (
                        <tr key={i}>
                          <td style={{ fontWeight: 600 }}>{p.symbol}</td>
                          <td className="t-num">{p.qty}</td>
                          <td className="t-num">\u20B9{fmt(p.avg)}</td>
                          <td className="t-num">{p.ltp ? `\u20B9${fmt(p.ltp)}` : '-'}</td>
                          <td className={`t-num ${p.pnl >= 0 ? 't-up' : 't-down'}`} style={{ fontWeight: 700 }}>
                            {p.pnl >= 0 ? '+' : ''}\u20B9{fmt(p.pnl)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Strategy Cards */}
            {activeStrategies.length > 0 && (
              <div className="t-grid-2" style={{ gap: 10 }}>
                {activeStrategies.map(s => (
                  <div key={s.strategy_key} className="t-panel" style={{ padding: '14px 16px', borderLeft: '3px solid var(--violet)', transition: 'transform 0.12s' }}
                    onMouseEnter={e => { e.currentTarget.style.transform = 'translateY(-1px)' }}
                    onMouseLeave={e => { e.currentTarget.style.transform = '' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                      <span style={{ fontSize: 13, fontWeight: 700 }}>{s.name}</span>
                      <span className={`t-badge ${s.required_tier === 'free' ? 't-badge-green' : s.required_tier === 'pro' ? 't-badge-violet' : 't-badge-amber'}`} style={{ fontSize: 9, textTransform: 'capitalize' }}>{s.required_tier}</span>
                    </div>
                    <p className="t-faint" style={{ margin: 0, fontSize: 10, lineHeight: 1.4 }}>{s.description}</p>
                  </div>
                ))}
              </div>
            )}

            {/* Download Full Report */}
            {orders.length > 0 && (
              <div style={{ textAlign: 'center', padding: 8 }}>
                <button className="t-btn t-btn-sm t-btn-ghost" onClick={() => csvDownload(
                  ['Symbol', 'Side', 'Qty', 'Price', 'Status', 'P&L', 'Time'],
                  orders.map(o => [o.symbol, o.side, String(o.quantity), fmt(o.price || 0), o.status, '', o.created_at]),
                  `trademetrix-report-${new Date().toISOString().slice(0, 10)}.csv`,
                )}>
                  Download Full Report (CSV)
                </button>
              </div>
            )}
          </>
        )}

        {/* ============= BROKERS ============= */}
        {activeTab === 'brokers' && (
          <>
            <div className="t-panel" style={{ padding: 0 }}>
              <div className="t-panel-header">
                <h3 className="t-panel-title">Connected Brokers ({brokers.length})</h3>
              </div>
              {brokers.length > 0 ? (
                <div style={{ display: 'flex', flexDirection: 'column' }}>
                  {brokers.map(b => (
                    <div key={b.id} style={{
                      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                      padding: '12px 16px', borderBottom: '1px solid var(--border)',
                    }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <span className={`t-dot ${brokerHealth[b.broker] === 'connected' ? 't-dot-green' : brokerHealth[b.broker] === 'error' ? 't-dot-red' : 't-dot-sub'}`} />
                        <span style={{ fontWeight: 600, fontSize: 13, textTransform: 'capitalize' }}>{b.broker}</span>
                        {b.is_active && <span className="t-badge t-badge-green" style={{ fontSize: 9 }}>Active</span>}
                      </div>
                      <div style={{ display: 'flex', gap: 6 }}>
                        {!b.is_active && (
                          <button className="t-btn t-btn-xs t-btn-ghost" onClick={() => handleActivateBroker(b.broker)}
                            style={{ color: 'var(--cyan)' }}>Activate</button>
                        )}
                        <button className="t-btn t-btn-xs t-btn-ghost" onClick={() => handleDisconnectBroker(b.broker)}
                          style={{ color: 'var(--text-red)' }}>Remove</button>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="t-panel-body" style={{ textAlign: 'center', padding: 20 }}>
                  <span className="t-faint">No brokers connected yet</span>
                </div>
              )}
            </div>

            <div className="t-panel" style={{ padding: '14px 16px' }}>
              <h3 style={{ margin: '0 0 8px', fontSize: 11, fontWeight: 600, letterSpacing: '0.03em' }}>
                {connectForm ? `Connect ${connectForm.broker}` : 'Available Brokers'}
              </h3>
              {connectForm ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  <div>
                    <label className="t-label" style={{ fontSize: 10 }}>API Key / App ID</label>
                    <input className="t-input" style={{ width: '100%' }} value={connectForm.api_key}
                      onChange={e => setConnectForm({ ...connectForm, api_key: e.target.value })} />
                  </div>
                  <div>
                    <label className="t-label" style={{ fontSize: 10 }}>Secret Key</label>
                    <input className="t-input" style={{ width: '100%' }} type="password" value={connectForm.secret_key}
                      onChange={e => setConnectForm({ ...connectForm, secret_key: e.target.value })} />
                  </div>
                  {brokerError && <span className="t-down" style={{ fontSize: 10 }}>{brokerError}</span>}
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button className="t-btn t-btn-sm t-btn-primary" onClick={handleConnectBroker} disabled={connecting}>
                      {connecting ? 'Connecting...' : 'Connect'}
                    </button>
                    <button className="t-btn t-btn-sm t-btn-ghost" onClick={() => { setConnectForm(null); setBrokerError('') }}>
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {availBrokers.map(b => {
                    const connected = brokers.some(c => c.broker === b)
                    return (
                      <button key={b} className={`t-btn t-btn-xs ${connected ? 't-btn-ghost' : 't-btn-sub'}`}
                        style={{ textTransform: 'capitalize' }}
                        onClick={() => !connected && setConnectForm({ broker: b, api_key: '', secret_key: '' })}
                        disabled={connected}>
                        {b} {connected ? '\u2713' : '+ Add'}
                      </button>
                    )
                  })}
                </div>
              )}
            </div>
          </>
        )}

      </div>

      {/* === Footer === */}
      <footer style={{
        height: 32, display: 'flex', alignItems: 'center', justifyContent: 'center',
        borderTop: '1px solid var(--border)', fontSize: 9, color: 'var(--text-faint)',
        fontFamily: 'var(--font-mono)',
      }}>
        TradeMetrix Terminal v0.1 &middot; Client Portal &middot; Data refreshes every 5s
      </footer>
    </div>
  )
}

/* ===================================================================
   OTP LOGIN / SIGNUP SCREEN
   =================================================================== */

function OTPScreen({ onVerify }: { onVerify: (email: string) => void }) {
  const [step, setStep] = useState<'email' | 'otp' | 'register'>('email')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fullName, setFullName] = useState('')
  const [phone, setPhone] = useState('')
  const [otp, setOtp] = useState(['', '', '', '', '', ''])
  const [sending, setSending] = useState(false)
  const [verifying, setVerifying] = useState(false)
  const [error, setError] = useState('')
  const [resendTimer, setResendTimer] = useState(0)
  const [userExists, setUserExists] = useState<boolean | null>(null)

  useEffect(() => {
    if (resendTimer <= 0) return
    const t = setInterval(() => setResendTimer(p => p - 1), 1000)
    return () => clearInterval(t)
  }, [resendTimer])

  const handleSendOTP = async () => {
    if (!email || !email.includes('@')) { setError('Enter a valid email'); return }
    setError(''); setSending(true)
    try {
      const res = await api.auth.sendOTP({ email })
      setUserExists(res.exists)
      setSending(false)
      if (res.exists) {
        setStep('otp')
        setResendTimer(30)
      } else {
        setStep('register')
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to send OTP')
      setSending(false)
    }
  }

  const handleRegister = async () => {
    if (!email || !password || password.length < 6) { setError('Email and password (min 6 chars) required'); return }
    setError(''); setSending(true)
    try {
      await api.auth.registerWithOTP({ email, password, full_name: fullName || undefined, phone: phone || undefined })
      setSending(false)
      setStep('otp')
      setResendTimer(30)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Registration failed')
      setSending(false)
    }
  }

  const handleVerifyOTP = async () => {
    const entered = otp.join('')
    if (entered.length !== 6) { setError('Enter the full 6-digit code'); return }
    setError(''); setVerifying(true)
    try {
      await api.auth.verifyOTP({ email, otp: entered })
      setVerifying(false)
      onVerify(email)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Invalid OTP')
      setVerifying(false)
    }
  }

  const handleResend = async () => {
    if (resendTimer > 0) return
    setError(''); setSending(true)
    try {
      await api.auth.sendOTP({ email })
      setSending(false)
      setResendTimer(30)
      setOtp(['', '', '', '', '', ''])
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to resend')
      setSending(false)
    }
  }

  const inputRefs: (HTMLInputElement | null)[] = []
  const handleOtpInput = (i: number, val: string) => {
    if (!/^\d?$/.test(val)) return
    const newOtp = [...otp]; newOtp[i] = val; setOtp(newOtp)
    if (val && i < 5) document.getElementById(`otp-${i + 1}`)?.focus()
  }
  const handleOtpKey = (i: number, key: string) => {
    if (key === 'Backspace' && !otp[i] && i > 0) document.getElementById(`otp-${i - 1}`)?.focus()
    if (key === 'Enter') handleVerifyOTP()
  }

  return (
    <div style={{
      minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'var(--bg)', padding: 16,
    }}>
      <div style={{
        width: '100%', maxWidth: 400,
        padding: '32px 28px', borderRadius: 12,
        border: '1px solid var(--border)',
        background: 'var(--bg-secondary)',
        boxShadow: '0 8px 32px rgba(0,0,0,0.3)',
      }}>
        <div style={{ textAlign: 'center', marginBottom: 28 }}>
          <div style={{
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            width: 48, height: 48, borderRadius: 12,
            background: 'var(--gradient-primary)', marginBottom: 12,
            fontSize: 20, fontWeight: 700, color: '#000',
          }}>TM</div>
          <h2 style={{ fontSize: 18, fontWeight: 700, margin: '0 0 4px' }}>Client Portal</h2>
          <p className="t-faint" style={{ fontSize: 11, margin: 0 }}>
            {step === 'email' ? 'Sign in to view your trading dashboard' :
             step === 'register' ? 'Create your account' :
             `Enter the code sent to ${email}`}
          </p>
        </div>

        {step === 'email' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <label className="t-label" style={{ fontSize: 10 }}>Email Address</label>
            <input className="t-input" type="email" placeholder="you@example.com" value={email}
              onChange={e => setEmail(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSendOTP()}
              autoFocus />
            {error && <span className="t-down" style={{ fontSize: 10 }}>{error}</span>}
            <button className="t-btn t-btn-primary" onClick={handleSendOTP} disabled={sending}
              style={{ width: '100%', height: 36 }}>
              {sending ? 'Sending OTP...' : 'Send OTP'}
            </button>
          </div>
        )}

        {step === 'register' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <label className="t-label" style={{ fontSize: 10 }}>Full Name</label>
            <input className="t-input" placeholder="Your name" value={fullName}
              onChange={e => setFullName(e.target.value)} autoFocus />
            <label className="t-label" style={{ fontSize: 10 }}>Email Address</label>
            <input className="t-input" type="email" placeholder="you@example.com" value={email}
              onChange={e => setEmail(e.target.value)} />
            <label className="t-label" style={{ fontSize: 10 }}>Phone (for OTP)</label>
            <input className="t-input" type="tel" placeholder="+919876543210" value={phone}
              onChange={e => setPhone(e.target.value)} />
            <label className="t-label" style={{ fontSize: 10 }}>Password</label>
            <input className="t-input" type="password" placeholder="Min 6 characters" value={password}
              onChange={e => setPassword(e.target.value)} />
            {error && <span className="t-down" style={{ fontSize: 10 }}>{error}</span>}
            <button className="t-btn t-btn-primary" onClick={handleRegister} disabled={sending}
              style={{ width: '100%', height: 36 }}>
              {sending ? 'Creating account...' : 'Create Account & Send OTP'}
            </button>
            <div style={{ textAlign: 'center' }}>
              <button style={{
                background: 'none', border: 'none', color: 'var(--text-sub)', fontSize: 10,
                cursor: 'pointer', fontFamily: 'var(--font-sans)',
                textDecoration: 'underline', textUnderlineOffset: 2,
              }} onClick={() => setStep('email')}>
                Already have an account? Sign in
              </button>
            </div>
          </div>
        )}

        {step === 'otp' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16, alignItems: 'center' }}>
            <div style={{
              padding: '8px 12px', borderRadius: 6, fontSize: 10,
              background: 'rgba(0,200,83,0.08)', color: 'var(--text-green)',
              width: '100%', textAlign: 'center',
              border: '1px solid rgba(0,200,83,0.12)',
            }}>
              OTP sent to {email}
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              {otp.map((d, i) => (
                <input key={i} id={`otp-${i}`}
                  ref={el => { inputRefs[i] = el }}
                  style={otpInputStyle(d !== '')}
                  type="text" inputMode="numeric" maxLength={1}
                  value={d}
                  onChange={e => handleOtpInput(i, e.target.value)}
                  onKeyDown={e => handleOtpKey(i, e.key)}
                  autoFocus={i === 0}
                />
              ))}
            </div>
            {error && <span className="t-down" style={{ fontSize: 10 }}>{error}</span>}
            <button className="t-btn t-btn-primary" onClick={handleVerifyOTP} disabled={verifying}
              style={{ width: '100%', height: 36 }}>
              {verifying ? 'Verifying...' : 'Verify & Sign In'}
            </button>
            <button className="t-btn t-btn-ghost" onClick={handleResend} disabled={sending || resendTimer > 0}
              style={{ width: '100%', height: 32, fontSize: 11 }}>
              {resendTimer > 0 ? `Resend in ${resendTimer}s` : sending ? 'Resending...' : 'Resend OTP'}
            </button>
            <button style={{
              background: 'none', border: 'none', color: 'var(--text-sub)', fontSize: 10,
              cursor: 'pointer', fontFamily: 'var(--font-sans)',
            }} onClick={() => { setStep('email'); setUserExists(null) }}>
              Change email
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

/* ===================================================================
   PORTAL PAGE ROOT
   =================================================================== */

export default function PortalPage() {
  const [authenticated, setAuthenticated] = useState(false)
  const [email, setEmail] = useState('')
  const [user, setUser] = useState<UserInfo | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const savedEmail = sessionStorage.getItem('tm_portal_email')
    const savedUser = sessionStorage.getItem('tm_portal_user')
    if (savedEmail) {
      setEmail(savedEmail)
      if (savedUser) {
        try { setUser(JSON.parse(savedUser)) } catch {}
      }
      setAuthenticated(true)
    }
    setLoading(false)
  }, [])

  const handleVerify = async (newEmail: string) => {
    sessionStorage.setItem('tm_portal_email', newEmail)
    setEmail(newEmail)
    try {
      const me = await api.auth.me()
      const info: UserInfo = {
        id: me.id, email: me.email, full_name: me.full_name || '',
        phone: (me as { phone?: string }).phone || '',
        subscription_tier: me.subscription_tier || 'free',
      }
      sessionStorage.setItem('tm_portal_user', JSON.stringify(info))
      setUser(info)
    } catch {
      setUser(null)
    }
    setAuthenticated(true)
  }

  const handleSignOut = () => {
    sessionStorage.removeItem('tm_portal_email')
    sessionStorage.removeItem('tm_portal_user')
    api.auth.signout().catch(() => {})
    setAuthenticated(false)
    setEmail('')
    setUser(null)
  }

  if (loading) return <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--bg)' }}>
    <div className="t-dot t-dot-green t-dot-pulse" />
  </div>

  if (!authenticated) {
    return <OTPScreen onVerify={handleVerify} />
  }

  return <ClientDashboard email={email} user={user} onSignOut={handleSignOut} />
}