'use client'

import { useEffect, useState, useCallback, useMemo, memo } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { api } from '@/lib/api'
import { useMarketData } from '@/lib/use-market-data'
import { usePolling } from '@/lib/use-polling'
import { useAuth } from '@/lib/auth-context'
import { useToast } from '@/lib/use-toast'
import { SkeletonCard, SkeletonTable } from '@/components/skeleton'
import { ErrorMessage } from '@/components/error-message'
import EquityCurve from '@/components/equity-curve'

interface BrokerCred {
  id: string; broker: string; is_active: boolean; created_at: string
}

interface AggPosition {
  symbol: string; exchange: string; quantity: number
  average_buy_price: number; last_price: number
  unrealised_pnl: number; realised_pnl: number; m2m: number
  product: string; instrument_type: string
  strike_price: number | null; expiry_date: string | null; option_type: string | null
  broker: string
}

function shallowArrayEqual<T>(a: T[], b: T[], key?: (x: T) => unknown): boolean {
  if (!Array.isArray(a) || !Array.isArray(b)) return false
  if (a.length !== b.length) return false
  if (a.length === 0) return true
  if (key) return a.every((item, i) => key(item) === key(b[i]))
  return a.every((item, i) => item === b[i])
}

function shallowObjectEqual(a: Record<string, unknown> | null, b: Record<string, unknown> | null): boolean {
  if (a === b) return true
  if (!a || !b || typeof a !== 'object' || typeof b !== 'object') return false
  const ka = Object.keys(a)
  const kb = Object.keys(b)
  if (ka.length !== kb.length) return false
  return ka.every(k => a[k] === b[k])
}

export default function DashboardPage() {
  const { token, isAdmin } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (isAdmin) {
      router.replace('/admin')
    }
  }, [isAdmin, router])
  const { ticks, connected } = useMarketData()
  const { toast } = useToast()
  const [positions, setPositions] = useState<AggPosition[]>([])
  const [funds, setFunds] = useState<Record<string, number> | null>(null)
  const [orders, setOrders] = useState<any[]>([])
  const [lastRefresh, setLastRefresh] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [creds, setCreds] = useState<BrokerCred[]>([])
  const [selectedBroker, setSelectedBroker] = useState('all')
  const [sqConfig, setSqConfig] = useState<{ enabled: boolean; time: string; days: number[] } | null>(null)
  const [showSqSettings, setShowSqSettings] = useState(false)

  const loadData = useCallback(async (isInitial = false) => {
    if (isInitial) setLoading(true)
    setError('')
    const withTimeout = (p: Promise<unknown>, ms: number, fallbackVal: unknown): Promise<unknown> =>
      Promise.race([p, new Promise((_, reject) => setTimeout(() => reject(new Error('timeout')), ms))])
        .catch(() => fallbackVal)

    const [p, f, o, c] = await Promise.all([
      withTimeout(api.engine.positions(), 8000, { positions: [] }),
      withTimeout(api.engine.funds(), 8000, { funds: null }),
      withTimeout(api.engine.orders(), 8000, { orders: [] }),
      api.brokers.credentials().catch(() => []),
    ])
    const newPositions = (p as any).positions || []
    const newFunds = (f as any).funds || null
    const newOrders = (o as any).orders || []
    const newCreds = (c as any) || []

    setPositions(prev => shallowArrayEqual(prev, newPositions, x => (x as any).symbol + (x as any).broker) ? prev : newPositions)
    setFunds(prev => shallowObjectEqual(prev as any, newFunds as any) ? prev : newFunds)
    setOrders(prev => shallowArrayEqual(prev, newOrders, x => (x as any).id) ? prev : newOrders)
    setCreds(prev => shallowArrayEqual(prev, newCreds, x => (x as any).id) ? prev : newCreds)
    setLastRefresh(new Date().toLocaleTimeString())
    if (isInitial) setLoading(false)
  }, [])

  useEffect(() => { if (token) loadData(true) }, [token, loadData])
  usePolling(() => loadData(), 4000, !!token)

  const loadSqConfig = async () => {
    try {
      const res = await api.squareoff.config() as any
      setSqConfig(res.config)
    } catch {}
  }

  useEffect(() => { if (token) loadSqConfig() }, [token])

  const filtered = useMemo(() =>
    selectedBroker === 'all'
      ? positions
      : positions.filter(p => p.broker === selectedBroker),
    [positions, selectedBroker]
  )

  const totalPnl = useMemo(() =>
    filtered.reduce((sum: number, p: any) => {
      const live = ticks[p.symbol]
      const ltp = live?.last_price || p.last_price || p.average_buy_price || 0
      const pnl = live ? (p.quantity * (ltp - p.average_buy_price)) : (p.unrealised_pnl || 0)
      return sum + (pnl || 0)
    }, 0),
    [filtered, ticks]
  )

  const filledOrders = useMemo(() =>
    orders.filter((o: any) => o.status === 'FILLED').length,
    [orders]
  )

  const winRate = useMemo(() => {
    if (orders.length === 0) return 0
    return Math.round((filledOrders / orders.length) * 100)
  }, [orders, filledOrders])

  const activeBrokers = useMemo(() =>
    [...new Set(positions.map(p => p.broker).filter(Boolean))],
    [positions]
  )

  const equityPoints = useMemo(() => {
    let cum = 0
    return filtered.map((p: any) => {
      const live = ticks[p.symbol]
      const ltp = live?.last_price || p.last_price || 0
      const pnl = live ? (p.quantity * (ltp - p.average_buy_price)) : (p.unrealised_pnl || 0)
      cum += pnl || 0
      return cum
    })
  }, [filtered, ticks])

  const EquityCurveMemo = useMemo(() => memo(EquityCurve), [])

  const sqOffAll = async () => {
    try {
      const res = await api.squareoff.run() as any
      toast('success', `Squared off ${res.squareoff_count || 0} positions`)
      setTimeout(() => loadData(), 1000)
    } catch { toast('error', 'Squareoff failed') }
  }

  const toggleSqAuto = async () => {
    const current = sqConfig || { enabled: false, time: '15:15', days: [0, 1, 2, 3, 4] }
    try {
      await api.squareoff.setConfig({ ...current, enabled: !current.enabled })
      setSqConfig({ ...current, enabled: !current.enabled })
      toast('success', `Auto-squareoff ${!current.enabled ? 'enabled' : 'disabled'}`)
    } catch { toast('error', 'Failed to update squareoff config') }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
        <div>
          <h1 className="t-page-title">Dashboard</h1>
          <p className="t-page-subtitle" style={{ margin: 0 }}>Portfolio overview & market summary</p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span className={`t-dot ${connected ? 't-dot-green t-dot-pulse' : 't-dot-red'}`} />
          <span style={{ fontSize: 11, color: connected ? 'var(--text-green)' : 'var(--text-red)', fontWeight: 600 }}>
            {connected ? 'Live' : 'Connecting...'}
          </span>
          <span className="t-faint" style={{ fontSize: 10 }}>Updated {lastRefresh}</span>
          <button className="t-btn t-btn-sm" onClick={() => loadData(true)}>Refresh</button>
        </div>
      </div>

      {loading ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10 }}>
            {Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} />)}
          </div>
          <SkeletonCard />
          <SkeletonTable rows={4} />
        </div>
      ) : error ? (
        <ErrorMessage message={error} onRetry={() => loadData(true)} />
      ) : (
      <>



      {/* KPI Row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8 }}>
        {[
          { label: 'Total P&L', value: `${totalPnl >= 0 ? '+' : ''}${(totalPnl || 0).toFixed(0)}`, sub: `${positions.length} positions`, up: totalPnl >= 0 },
          { label: 'Win Rate', value: `${winRate}%`, sub: `${filledOrders} filled / ${orders.length} total`, up: winRate >= 50 },
          { label: 'Available Margin', value: `₹${(funds?.available_margin || 0).toLocaleString()}`, sub: `of ₹${(funds?.total_margin || 0).toLocaleString()}`, up: true },
          { label: 'Open Positions', value: `${positions.length}`, sub: `${positions.filter((p: any) => p.quantity > 0).length} long / ${positions.filter((p: any) => p.quantity < 0).length} short`, up: true },
        ].map((kpi) => (
          <div key={kpi.label} className="t-panel" style={{ padding: '8px 10px' }}>
            <div className="t-stat-label" style={{ fontSize: 10 }}>{kpi.label}</div>
            <div className={`t-stat-value ${kpi.up !== undefined ? (kpi.up ? 't-up' : 't-down') : ''}`} style={{ fontSize: 17, marginBottom: 1 }}>
              {kpi.value}
            </div>
            <div className="t-faint" style={{ fontSize: 9 }}>{kpi.sub}</div>
          </div>
        ))}
      </div>

      {/* Main 3-Column Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr 1fr', gap: 10, minHeight: 300 }}>
        {/* Left Column */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {/* Quick Actions */}
          <div className="t-panel">
            <div className="t-panel-header" style={{ padding: '8px 12px' }}>
              <span className="t-panel-title">Quick Actions</span>
            </div>
            <div style={{ padding: 8, display: 'flex', flexDirection: 'column', gap: 6 }}>
              {[
                { label: 'Multi-Leg Strategy', href: '/strategies/multi-leg', icon: '✦', color: 'var(--cyan)' },
                { label: 'Place Trade', href: '/terminal', icon: '▶', color: 'var(--green)' },
                { label: 'View Positions', href: '/positions', icon: '◆', color: 'var(--violet)' },
                { label: 'Run Backtest', href: '/backtest', icon: '◆', color: 'var(--violet)' },
                { label: 'View Risk', href: '/risk', icon: '▲', color: 'var(--amber)' },
              ].map((action) => (
                <Link key={action.label} href={action.href} className="t-link-row" style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 10px', fontSize: 11, fontWeight: 600, color: 'var(--text-sub)', textDecoration: 'none' }}>
                  <span style={{ color: action.color, fontSize: 13 }}>{action.icon}</span>
                  {action.label}
                </Link>
              ))}
            </div>
          </div>

          {/* Square-off Panel */}
          <div className="t-panel">
            <div className="t-panel-header" style={{ padding: '8px 12px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span className="t-panel-title">Square-Off</span>
              <button className="t-btn t-btn-xs t-btn-ghost" onClick={() => setShowSqSettings(!showSqSettings)}>
                {showSqSettings ? '▲' : '▼'}
              </button>
            </div>
            {showSqSettings && sqConfig && (
              <div style={{ padding: '8px 12px', borderBottom: '1px solid var(--border)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                  <span className="t-faint" style={{ fontSize: 11 }}>Auto square-off at {sqConfig.time}</span>
                  <button
                    className={`t-btn t-btn-xs ${sqConfig.enabled ? 't-btn-green' : 't-btn-ghost'}`}
                    onClick={toggleSqAuto}
                  >
                    {sqConfig.enabled ? 'ON' : 'OFF'}
                  </button>
                </div>
                <div style={{ display: 'flex', gap: 6 }}>
                  <select className="t-input t-input-xs" value={sqConfig.time} onChange={async (e) => {
                    const updated = { ...sqConfig, time: e.target.value }
                    setSqConfig(updated)
                    await api.squareoff.setConfig(updated)
                  }} style={{ flex: 1 }}>
                    {['09:15', '09:30', '10:00', '11:00', '12:00', '13:00', '14:00', '14:30', '15:00', '15:15', '15:20', '15:25'].map(t => (
                      <option key={t} value={t}>{t} IST</option>
                    ))}
                  </select>
                </div>
              </div>
            )}
            <div style={{ padding: 8 }}>
              <button className="t-btn t-btn-sm t-btn-danger" onClick={sqOffAll} style={{ width: '100%' }}>
                Square-Off All Intraday
              </button>
            </div>
          </div>

          {/* Active Strategies */}
          <div className="t-panel" style={{ flex: 1 }}>
            <div className="t-panel-header" style={{ padding: '8px 12px' }}>
              <span className="t-panel-title">Brokers</span>
            </div>
            <div style={{ padding: 8 }}>
              {activeBrokers.length > 0 ? activeBrokers.map(b => (
                <div key={b} className="t-link-row" style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 8px', fontSize: 11 }}>
                  <span className="t-dot t-dot-green" />
                  <span style={{ fontWeight: 600, color: 'var(--text)' }}>{b}</span>
                </div>
              )) : (
                <p className="t-faint" style={{ fontSize: 11, textAlign: 'center', margin: '12px 0' }}>
                  <Link href="/brokers" style={{ color: 'var(--cyan)' }}>Connect a broker</Link> to get started
                </p>
              )}
            </div>
          </div>
        </div>

        {/* Center: Equity Curve */}
        <div className="t-panel" style={{ display: 'flex', flexDirection: 'column' }}>
          <div className="t-panel-header" style={{ padding: '8px 12px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span className="t-panel-title">Equity Curve</span>
            <select className="t-input t-input-xs" value={selectedBroker} onChange={e => setSelectedBroker(e.target.value)} style={{ width: 120 }}>
              <option value="all">All Brokers</option>
              {activeBrokers.map(b => <option key={b} value={b}>{b}</option>)}
            </select>
          </div>
          <div style={{ flex: 1, padding: 4, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            {filtered.length > 0 ? (
              <EquityCurveMemo points={equityPoints} height={200} />
            ) : (
              <p className="t-faint" style={{ fontSize: 11 }}>No position data to chart</p>
            )}
          </div>
        </div>

        {/* Right: Top Movers + Recent Trades */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div className="t-panel">
            <div className="t-panel-header" style={{ padding: '8px 12px' }}>
              <span className="t-panel-title">Top Movers</span>
            </div>
            <div style={{ padding: 8 }}>
              {filtered.slice(0, 5).map((p: any, i: number) => {
                const live = ticks[p.symbol]
                const ltp = live?.last_price || p.last_price || 0
                const pnl = live ? (p.quantity * (ltp - p.average_buy_price)) : (p.unrealised_pnl || 0)
                return (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '4px 0', borderBottom: i < filtered.length - 1 ? '1px solid rgba(255,255,255,0.03)' : 'none' }}>
                    <div>
                      <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text)' }}>{p.symbol?.split(':').pop()}</span>
                      <span className="t-faint" style={{ fontSize: 9, marginLeft: 4 }}>{p.broker}</span>
                    </div>
                    <span className={`t-num ${pnl >= 0 ? 't-up' : 't-down'}`} style={{ fontSize: 11, fontWeight: 700 }}>
                      {pnl >= 0 ? '+' : ''}{pnl?.toFixed(0) || '0'}
                    </span>
                  </div>
                )
              })}
              {filtered.length === 0 && (
                <p className="t-faint" style={{ fontSize: 11, textAlign: 'center', margin: '16px 0' }}>No positions</p>
              )}
            </div>
          </div>

          <div className="t-panel">
            <div className="t-panel-header" style={{ padding: '8px 12px' }}>
              <span className="t-panel-title">Recent Orders</span>
            </div>
            <div style={{ padding: 8 }}>
              {orders.slice(0, 5).map((o: any, i: number) => (
                <div key={i} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '4px 0', borderBottom: i < Math.min(orders.length, 5) - 1 ? '1px solid rgba(255,255,255,0.03)' : 'none' }}>
                  <div>
                    <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text)' }}>{o.symbol?.split(':').pop()}</span>
                    <span className="t-faint" style={{ fontSize: 10, marginLeft: 6 }}>{o.quantity} {o.side}</span>
                  </div>
                  <span className={`t-badge ${o.status === 'FILLED' ? 't-badge-green' : o.status === 'REJECTED' ? 't-badge-red' : 't-badge-sub'}`} style={{ fontSize: 9 }}>
                    {o.status || 'PENDING'}
                  </span>
                </div>
              ))}
              {orders.length === 0 && (
                <p className="t-faint" style={{ fontSize: 11, textAlign: 'center', margin: '16px 0' }}>No recent orders</p>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Open Positions Table */}
      <div className="t-panel" style={{ padding: 0 }}>
        <div className="t-panel-header" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span className="t-panel-title">Open Positions ({filtered.length})</span>
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <select className="t-input t-input-xs" value={selectedBroker} onChange={e => setSelectedBroker(e.target.value)} style={{ width: 120 }}>
              <option value="all">All Brokers</option>
              {activeBrokers.map(b => <option key={b} value={b}>{b}</option>)}
            </select>
            <Link href="/positions" className="t-btn t-btn-xs t-btn-ghost">View All →</Link>
          </div>
        </div>
        {filtered.length > 0 ? (
          <div style={{ overflowX: 'auto' }}>
            <table className="t-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th className="t-num">Qty</th>
                  <th className="t-num">Avg</th>
                  <th className="t-num">LTP</th>
                  <th className="t-num">P&L</th>
                  <th>Type</th>
                  <th>Broker</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((p: any, i: number) => {
                  const live = ticks[p.symbol]
                  const ltp = live?.last_price || p.last_price || 0
                  const pnl = live ? (p.quantity * (ltp - p.average_buy_price)) : p.unrealised_pnl
                  return (
                    <tr key={i}>
                      <td style={{ fontWeight: 600 }}>{p.symbol?.split(':').pop()}</td>
                      <td className="t-num">{p.quantity}</td>
                      <td className="t-num">{p.average_buy_price?.toFixed(1) || '-'}</td>
                      <td className="t-num">{ltp?.toFixed(1) || '-'}</td>
                      <td className={`t-num ${pnl >= 0 ? 't-up' : 't-down'}`} style={{ fontWeight: 600 }}>
                        {pnl >= 0 ? '+' : ''}{pnl?.toFixed(0) || '0'}
                      </td>
                      <td>
                        <span className={`t-badge ${p.instrument_type === 'OPT' ? 't-badge-violet' : 't-badge-cyan'}`} style={{ fontSize: 9 }}>
                          {p.instrument_type || 'EQ'}
                        </span>
                      </td>
                      <td><span className="t-faint" style={{ fontSize: 10 }}>{p.broker}</span></td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="t-faint" style={{ fontSize: 11, textAlign: 'center', padding: 24, margin: 0 }}>
            No open positions
          </p>
        )}
      </div>

      </>
      )}
    </div>
  )
}
