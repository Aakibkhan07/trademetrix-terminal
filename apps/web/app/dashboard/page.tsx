'use client'

import { useEffect, useState, useCallback } from 'react'
import Link from 'next/link'
import { api } from '@/lib/api'
import { useMarketData } from '@/lib/use-market-data'
import { usePolling } from '@/lib/use-polling'
import { useAuth } from '@/lib/auth-context'
import { SkeletonCard, SkeletonTable } from '@/components/skeleton'
import { ErrorMessage } from '@/components/error-message'
import EquityCurve from '@/components/equity-curve'

const WATCH_SYMBOLS = [
  { name: 'NIFTY', key: 'NSE:NIFTY50-INDEX' },
  { name: 'BANKNIFTY', key: 'NSE:NIFTYBANK-INDEX' },
  { name: 'FINNIFTY', key: 'NSE:FINNIFTY-INDEX' },
  { name: 'SENSEX', key: 'BSE:SENSEX-INDEX' },
]

export default function DashboardPage() {
  const { token } = useAuth()
  const { ticks, connected, subscribe, startFeed } = useMarketData()
  const [positions, setPositions] = useState<any[]>([])
  const [funds, setFunds] = useState<Record<string, number> | null>(null)
  const [orders, setOrders] = useState<any[]>([])
  const [lastRefresh, setLastRefresh] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const loadData = useCallback(async (isInitial = false) => {
    if (isInitial) setLoading(true)
    setError('')
    try {
      const [p, f, o] = await Promise.all([
        api.engine.positions(),
        api.engine.funds(),
        api.engine.orders(),
      ])
      setPositions((p as any).positions || [])
      setFunds((f as any).funds || null)
      setOrders((o as any).orders || [])
      setLastRefresh(new Date().toLocaleTimeString())
    } catch {
      setError('Failed to load dashboard data')
    } finally {
      if (isInitial) setLoading(false)
    }
  }, [])

  useEffect(() => {
    subscribe(WATCH_SYMBOLS.map((s) => s.key))
    startFeed()
  }, [subscribe, startFeed])

  useEffect(() => { if (token) loadData(true) }, [token, loadData])
  usePolling(() => loadData(), 4000, !!token)

  const totalPnl = positions.reduce((sum: number, p: any) => {
    const live = ticks[p.symbol]
    const ltp = live?.last_price || p.last_price || 0
    return sum + (live ? (p.quantity * (ltp - p.average_buy_price)) : (p.unrealised_pnl || 0))
  }, 0)

  const filledOrders = orders.filter((o: any) => o.status === 'FILLED').length
  const winRate = filledOrders > 0 ? Math.round((filledOrders / Math.max(orders.length, 1)) * 100) : 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {/* Page Header */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        flexWrap: 'wrap', gap: 8,
      }}>
        <div>
          <h1 style={{
            fontFamily: "'Inter', sans-serif", fontWeight: 700,
            fontSize: 18, margin: 0, color: 'var(--text)',
          }}>Dashboard</h1>
          <p style={{ color: 'var(--text-sub)', fontSize: 12, margin: '2px 0 0' }}>
            Portfolio overview & market summary
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span className={`t-dot ${connected ? 't-dot-green t-dot-pulse' : 't-dot-red'}`} />
          <span style={{ fontSize: 11, color: connected ? 'var(--text-green)' : 'var(--text-red)', fontWeight: 600 }}>
            {connected ? 'Live' : 'Connecting...'}
          </span>
          <span style={{ fontSize: 10, color: 'var(--text-faint)' }}>Updated {lastRefresh}</span>
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

      {/* Market Tickers */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10 }}>
        {WATCH_SYMBOLS.map((s) => {
          const t = ticks[s.key]
          const pct = t?.change_pct ?? 0
          return (
            <div key={s.key} style={{
              background: 'var(--panel)', border: '1px solid var(--border)',
              borderRadius: 'var(--radius-md)', padding: '10px 12px',
            }}>
              <div style={{ fontSize: 10, color: 'var(--text-faint)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                {s.name}
              </div>
              {t ? (
                <>
                  <div style={{
                    fontFamily: 'var(--font-mono)', fontSize: 20, fontWeight: 700,
                    fontVariantNumeric: 'tabular-nums', color: 'var(--text)',
                    margin: '4px 0',
                  }}>
                    {t.last_price.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 })}
                  </div>
                  <div style={{
                    display: 'flex', alignItems: 'center', gap: 6, fontSize: 11,
                    color: pct >= 0 ? 'var(--text-green)' : 'var(--text-red)',
                    fontWeight: 700,
                  }}>
                    <span>{pct >= 0 ? '▲' : '▼'}</span>
                    <span>{pct >= 0 ? '+' : ''}{pct.toFixed(2)}%</span>
                    <span style={{ color: 'var(--text-faint)', fontWeight: 400 }}>
                      {t.change >= 0 ? '+' : ''}{t.change.toFixed(1)}
                    </span>
                  </div>
                </>
              ) : (
                <div style={{ color: 'var(--text-faint)', fontSize: 12, marginTop: 8 }}>Waiting...</div>
              )}
            </div>
          )
        })}
      </div>

      {/* KPI Row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10 }}>
        {[
          { label: 'Total P&L', value: `${totalPnl >= 0 ? '+' : ''}${(totalPnl || 0).toFixed(0)}`, sub: `${positions.length} positions`, up: totalPnl >= 0 },
          { label: 'Win Rate', value: `${winRate}%`, sub: `${filledOrders} filled / ${orders.length} total`, up: winRate >= 50 },
          { label: 'Available Margin', value: `₹${(funds?.available_margin || 0).toLocaleString()}`, sub: `of ₹${(funds?.total_margin || 0).toLocaleString()}`, up: true },
          { label: 'Open Positions', value: `${positions.length}`, sub: `${positions.filter((p: any) => p.quantity > 0).length} long / ${positions.filter((p: any) => p.quantity < 0).length} short`, up: true },
        ].map((kpi) => (
          <div key={kpi.label} style={{
            background: 'var(--panel)', border: '1px solid var(--border)',
            borderRadius: 'var(--radius-md)', padding: '12px',
          }}>
            <div style={{ fontSize: 10, color: 'var(--text-faint)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>
              {kpi.label}
            </div>
            <div style={{
              fontFamily: 'var(--font-mono)', fontSize: 20, fontWeight: 700,
              fontVariantNumeric: 'tabular-nums',
              color: kpi.up !== undefined ? (kpi.up ? 'var(--text-green)' : 'var(--text-red)') : 'var(--text)',
              marginBottom: 2,
            }}>
              {kpi.value}
            </div>
            <div style={{ fontSize: 10, color: 'var(--text-faint)' }}>{kpi.sub}</div>
          </div>
        ))}
      </div>

      {/* Main 3-Column Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr 1fr', gap: 10, minHeight: 300 }}>
        {/* Left: Quick Actions + Active Strategies */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {/* Quick Actions */}
          <div style={{
            background: 'var(--panel)', border: '1px solid var(--border)',
            borderRadius: 'var(--radius-md)',
          }}>
            <div style={{
              padding: '8px 12px', borderBottom: '1px solid var(--border)',
              fontSize: 11, fontWeight: 700, color: 'var(--text)',
            }}>Quick Actions</div>
            <div style={{ padding: 8, display: 'flex', flexDirection: 'column', gap: 6 }}>
              {[
                { label: 'New Strategy', href: '/strategies/builder', icon: '✦', color: 'var(--cyan)' },
                { label: 'Run Backtest', href: '/backtest', icon: '◆', color: 'var(--violet)' },
                { label: 'Place Trade', href: '/terminal', icon: '▶', color: 'var(--green)' },
                { label: 'View Risk', href: '/risk', icon: '▲', color: 'var(--amber)' },
              ].map((action) => (
                <Link key={action.label} href={action.href} style={{
                  display: 'flex', alignItems: 'center', gap: 8,
                  padding: '7px 10px', borderRadius: 'var(--radius-sm)',
                  color: 'var(--text-sub)', fontSize: 11, fontWeight: 600,
                  textDecoration: 'none', transition: 'all 120ms ease',
                }}
                  onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg-hover)'; e.currentTarget.style.color = 'var(--text)' }}
                  onMouseLeave={e => { e.currentTarget.style.background = 'none'; e.currentTarget.style.color = 'var(--text-sub)' }}
                >
                  <span style={{ color: action.color, fontSize: 13 }}>{action.icon}</span>
                  {action.label}
                </Link>
              ))}
            </div>
          </div>

          {/* Active Strategies */}
          <div style={{
            flex: 1, background: 'var(--panel)', border: '1px solid var(--border)',
            borderRadius: 'var(--radius-md)',
          }}>
            <div style={{
              padding: '8px 12px', borderBottom: '1px solid var(--border)',
              fontSize: 11, fontWeight: 700, color: 'var(--text)',
            }}>Active Strategies</div>
            <div style={{ padding: 8 }}>
              <p style={{ color: 'var(--text-faint)', fontSize: 11, textAlign: 'center', margin: '24px 0' }}>
                No active strategies
              </p>
            </div>
          </div>
        </div>

        {/* Center: Equity Curve */}
        <div style={{
          background: 'var(--panel)', border: '1px solid var(--border)',
          borderRadius: 'var(--radius-md)', display: 'flex', flexDirection: 'column',
        }}>
          <div style={{
            padding: '8px 12px', borderBottom: '1px solid var(--border)',
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          }}>
            <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--text)' }}>Equity Curve</span>
            <div style={{ display: 'flex', gap: 4 }}>
              {['1D', '1W', '1M', '1Y'].map((p) => (
                <button key={p} style={{
                  padding: '2px 8px', borderRadius: 4, border: 'none',
                  background: p === '1M' ? 'var(--bg-active)' : 'transparent',
                  color: p === '1M' ? 'var(--cyan)' : 'var(--text-faint)',
                  fontSize: 10, fontWeight: 600, cursor: 'pointer',
                  fontFamily: "'Inter', sans-serif",
                }}>{p}</button>
              ))}
            </div>
          </div>
          <div style={{ flex: 1, padding: 4, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            {positions.length > 0 ? (
              <EquityCurve points={(() => {
                let cum = 0
                return positions.map((p: any) => {
                  const live = ticks[p.symbol]
                  const ltp = live?.last_price || p.last_price || 0
                  const pnl = live ? (p.quantity * (ltp - p.average_buy_price)) : (p.unrealised_pnl || 0)
                  cum += pnl || 0
                  return cum
                })
              })()} height={200} />
            ) : (
              <p style={{ color: 'var(--text-faint)', fontSize: 11 }}>No position data to chart</p>
            )}
          </div>
        </div>

        {/* Right: Top Movers + Recent Trades */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div style={{
            background: 'var(--panel)', border: '1px solid var(--border)',
            borderRadius: 'var(--radius-md)',
          }}>
            <div style={{
              padding: '8px 12px', borderBottom: '1px solid var(--border)',
              fontSize: 11, fontWeight: 700, color: 'var(--text)',
            }}>Top Movers</div>
            <div style={{ padding: 8 }}>
              {positions.slice(0, 5).map((p: any, i: number) => {
                const live = ticks[p.symbol]
                const ltp = live?.last_price || p.last_price || 0
                const pnl = live ? (p.quantity * (ltp - p.average_buy_price)) : (p.unrealised_pnl || 0)
                return (
                  <div key={i} style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    padding: '4px 0', borderBottom: i < positions.length - 1 ? '1px solid rgba(255,255,255,0.03)' : 'none',
                  }}>
                    <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text)' }}>
                      {p.symbol?.split(':').pop()}
                    </span>
                    <span style={{
                      fontFamily: 'var(--font-mono)', fontSize: 11,
                      color: pnl >= 0 ? 'var(--text-green)' : 'var(--text-red)',
                      fontWeight: 700,
                    }}>
                      {pnl >= 0 ? '+' : ''}{pnl?.toFixed(0) || '0'}
                    </span>
                  </div>
                )
              })}
              {positions.length === 0 && (
                <p style={{ color: 'var(--text-faint)', fontSize: 11, textAlign: 'center', margin: '16px 0' }}>
                  No positions
                </p>
              )}
            </div>
          </div>

          <div style={{
            background: 'var(--panel)', border: '1px solid var(--border)',
            borderRadius: 'var(--radius-md)',
          }}>
            <div style={{
              padding: '8px 12px', borderBottom: '1px solid var(--border)',
              fontSize: 11, fontWeight: 700, color: 'var(--text)',
            }}>Recent Orders</div>
            <div style={{ padding: 8 }}>
              {orders.slice(0, 5).map((o: any, i: number) => (
                <div key={i} style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  padding: '4px 0', borderBottom: i < Math.min(orders.length, 5) - 1 ? '1px solid rgba(255,255,255,0.03)' : 'none',
                }}>
                  <div>
                    <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text)' }}>
                      {o.symbol?.split(':').pop()}
                    </span>
                    <span style={{ fontSize: 10, color: 'var(--text-faint)', marginLeft: 6 }}>
                      {o.quantity} {o.side}
                    </span>
                  </div>
                  <span className={`t-badge ${o.status === 'FILLED' ? 't-badge-green' : o.status === 'REJECTED' ? 't-badge-red' : 't-badge-sub'}`} style={{ fontSize: 9 }}>
                    {o.status || 'PENDING'}
                  </span>
                </div>
              ))}
              {orders.length === 0 && (
                <p style={{ color: 'var(--text-faint)', fontSize: 11, textAlign: 'center', margin: '16px 0' }}>
                  No recent orders
                </p>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Open Positions Table */}
      <div style={{
        background: 'var(--panel)', border: '1px solid var(--border)',
        borderRadius: 'var(--radius-md)',
      }}>
        <div style={{
          padding: '8px 12px', borderBottom: '1px solid var(--border)',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}>
          <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--text)' }}>
            Open Positions ({positions.length})
          </span>
          <Link href="/positions" style={{
            fontSize: 11, color: 'var(--cyan)', fontWeight: 600,
            textDecoration: 'none',
          }}>View All →</Link>
        </div>
        {positions.length > 0 ? (
          <div style={{ overflowX: 'auto' }}>
            <table className="t-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th className="num">Qty</th>
                  <th className="num">Avg</th>
                  <th className="num">LTP</th>
                  <th className="num">P&L</th>
                  <th>Type</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((p: any, i: number) => {
                  const live = ticks[p.symbol]
                  const ltp = live?.last_price || p.last_price || 0
                  const pnl = live ? (p.quantity * (ltp - p.average_buy_price)) : p.unrealised_pnl
                  return (
                    <tr key={i}>
                      <td style={{ fontWeight: 600 }}>{p.symbol?.split(':').pop()}</td>
                      <td className="num">{p.quantity}</td>
                      <td className="num">{p.average_buy_price?.toFixed(1) || '-'}</td>
                      <td className="num">{ltp?.toFixed(1) || '-'}</td>
                      <td className={`num ${pnl >= 0 ? 't-up' : 't-down'}`} style={{ fontWeight: 600 }}>
                        {pnl >= 0 ? '+' : ''}{pnl?.toFixed(0) || '0'}
                      </td>
                      <td>
                        <span className={`t-badge ${p.instrument_type === 'OPT' ? 't-badge-violet' : 't-badge-cyan'}`} style={{ fontSize: 9 }}>
                          {p.instrument_type || 'EQ'}
                        </span>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <p style={{ color: 'var(--text-faint)', fontSize: 11, textAlign: 'center', padding: 24, margin: 0 }}>
            No open positions
          </p>
        )}
      </div>

      </>
      )}
    </div>
  )
}
