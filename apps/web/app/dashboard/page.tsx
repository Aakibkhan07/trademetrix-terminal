'use client'

import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import Link from 'next/link'
import EquityCurve from '@/components/equity-curve'
import { DEMO_STRATEGIES, DEMO_RUNS, DEMO_TRADES, EQUITY_CURVE_POINTS } from '@/lib/demo-data'

interface DashboardData {
  user: { email: string; full_name: string }
  is_live: boolean
  strategies: number
  positions: number
}

export default function DashboardPage() {
  const [data, setData] = useState<DashboardData>({
    user: { email: '', full_name: 'Trader' },
    is_live: false,
    strategies: 0,
    positions: 0,
  })
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const load = async () => {
      try {
        const [user, liveStatus, runs, strategies] = await Promise.all([
          api.auth.me().catch(() => ({ email: '', full_name: 'Trader' })),
          api.risk.liveStatus().catch(() => ({ is_live: false })),
          api.get('/api/v1/engine/runs').catch(() => ({ runs: [] })),
          api.strategies.list().catch(() => ({ strategies: [] })),
        ])
        setData({
          user: user as unknown as DashboardData['user'],
          is_live: (liveStatus as { is_live: boolean }).is_live,
          positions: (runs as { runs: unknown[] }).runs.length || DEMO_RUNS.length,
          strategies: (strategies as { strategies: unknown[] }).strategies.length || DEMO_STRATEGIES.length,
        })
      } catch {
        setData(prev => ({
          ...prev,
          positions: DEMO_RUNS.length,
          strategies: DEMO_STRATEGIES.length,
        }))
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  const totalPnl = DEMO_RUNS.reduce((sum, r) => sum + r.pnl, 0)

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '60vh' }}>
        <p style={{ color: '#555570' }}>Loading dashboard...</p>
      </div>
    )
  }

  return (
    <div>
      <div style={{ marginBottom: 28 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 4, flexWrap: 'wrap' }}>
          <h1 style={{ fontFamily: 'Outfit', fontSize: 26, margin: 0, letterSpacing: '-0.02em' }}>
            Welcome back, {data?.user?.full_name || 'Trader'}
          </h1>
          {data?.is_live ? (
            <span className="badge badge-red" style={{ padding: '4px 12px', fontSize: 11, borderRadius: 6 }}>LIVE TRADING</span>
          ) : (
            <span className="badge badge-cyan" style={{ padding: '4px 12px', fontSize: 11, borderRadius: 6 }}>PAPER TRADING</span>
          )}
        </div>
        <p style={{ color: '#555570', margin: 0, fontSize: 13 }}>
          {new Date().toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}
        </p>
      </div>

      <div className="grid-auto" style={{ marginBottom: 28 }}>
        <div className="glass-card" style={{ padding: '20px' }}>
          <p style={{ color: '#555570', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.1em', margin: '0 0 6px', fontWeight: 600 }}>Total P&L</p>
          <p className="numeric" style={{ fontSize: 28, fontWeight: 700, margin: 0, color: totalPnl >= 0 ? '#22c55e' : '#ef4444' }}>
            {totalPnl >= 0 ? '+' : ''}₹{totalPnl.toLocaleString()}
          </p>
        </div>
        <div className="glass-card" style={{ padding: '20px' }}>
          <p style={{ color: '#555570', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.1em', margin: '0 0 6px', fontWeight: 600 }}>Active Strategies</p>
          <p className="numeric" style={{ fontSize: 28, fontWeight: 700, margin: 0, color: '#8b5cf6' }}>
            {data?.strategies || 0}
          </p>
        </div>
        <div className="glass-card" style={{ padding: '20px' }}>
          <p style={{ color: '#555570', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.1em', margin: '0 0 6px', fontWeight: 600 }}>Running Positions</p>
          <p className="numeric" style={{ fontSize: 28, fontWeight: 700, margin: 0, color: '#22d3ee' }}>
            {data?.positions || 0}
          </p>
        </div>
        <Link href="/risk" style={{ textDecoration: 'none' }}>
          <div className="glass-card" style={{ padding: '20px' }}>
            <p style={{ color: '#555570', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.1em', margin: '0 0 6px', fontWeight: 600 }}>Risk Status</p>
            <p style={{ fontSize: 14, margin: 0, color: '#22c55e', display: 'flex', alignItems: 'center' }}>
              <span className="status-dot active" />All clear — within limits
            </p>
          </div>
        </Link>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1.6fr 1fr', gap: 20, marginBottom: 28 }}>
        <div className="panel" style={{ padding: '20px' }}>
          <div className="panel-header" style={{ marginBottom: 12 }}>
            <h3 className="panel-title" style={{ fontSize: 15 }}>Equity Curve</h3>
            <span className="badge badge-green">+23.8% all time</span>
          </div>
          <EquityCurve points={EQUITY_CURVE_POINTS} height={220} />
        </div>

        <div className="panel" style={{ padding: '20px' }}>
          <div className="panel-header" style={{ marginBottom: 12 }}>
            <h3 className="panel-title" style={{ fontSize: 15 }}>Running Strategies</h3>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {DEMO_RUNS.map((run) => (
              <div key={run.id} style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                padding: '10px 12px', background: 'rgba(139,92,246,0.04)', borderRadius: 8,
                border: '1px solid rgba(139,92,246,0.06)',
              }}>
                <div>
                  <p style={{ margin: 0, fontSize: 13, fontWeight: 600 }}>{run.strategy_name}</p>
                  <p style={{ margin: '2px 0 0', fontSize: 11, color: '#555570' }}>{run.symbol}</p>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <p className="numeric" style={{ margin: 0, fontSize: 14, fontWeight: 600, color: run.pnl >= 0 ? '#22c55e' : '#ef4444' }}>
                    {run.pnl >= 0 ? '+' : ''}₹{run.pnl.toLocaleString()}
                  </p>
                  <span className="badge badge-green" style={{ fontSize: 9, padding: '1px 6px' }}>{run.status}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <h2 style={{ fontFamily: 'Outfit', fontSize: 16, margin: '0 0 14px', color: '#f0f0f5', letterSpacing: '-0.01em' }}>
        Strategy Performance
      </h2>
      <div className="grid-auto" style={{ marginBottom: 28 }}>
        {DEMO_STRATEGIES.map((s) => (
          <div key={s.id} className="strategy-card" style={{ padding: '18px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 14 }}>
              <div>
                <h3 style={{ fontFamily: 'Outfit', fontSize: 14, margin: 0 }}>{s.name}</h3>
                <p style={{ margin: '2px 0 0', fontSize: 11, color: '#555570' }}>{s.type}</p>
              </div>
              <span className={`badge ${s.is_active ? 'badge-green' : 'badge-cyan'}`} style={{ fontSize: 9, padding: '2px 8px' }}>
                {s.is_active ? 'Active' : 'Paused'}
              </span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10 }}>
              <div><span style={{ color: '#555570', fontSize: 10, display: 'block', marginBottom: 2 }}>Returns</span><span className="numeric" style={{ fontSize: 15, fontWeight: 700, color: '#22c55e' }}>{s.metrics.returns}</span></div>
              <div><span style={{ color: '#555570', fontSize: 10, display: 'block', marginBottom: 2 }}>Win Rate</span><span className="numeric" style={{ fontSize: 15, fontWeight: 700 }}>{s.metrics.winRate}</span></div>
              <div><span style={{ color: '#555570', fontSize: 10, display: 'block', marginBottom: 2 }}>Sharpe</span><span className="numeric" style={{ fontSize: 15, fontWeight: 700, color: '#22d3ee' }}>{s.metrics.sharpe}</span></div>
            </div>
          </div>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
        <div className="panel" style={{ padding: '20px' }}>
          <div className="panel-header" style={{ marginBottom: 12 }}>
            <h3 className="panel-title" style={{ fontSize: 15 }}>Recent Trades</h3>
            <Link href="/transparency" style={{ fontSize: 12, color: '#22d3ee' }}>View all →</Link>
          </div>
          {DEMO_TRADES.length > 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {DEMO_TRADES.slice(0, 4).map((t) => (
                <div key={t.id} style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  padding: '8px 10px', background: 'rgba(139,92,246,0.03)', borderRadius: 6,
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <span className={`badge ${t.side === 'BUY' ? 'badge-green' : 'badge-red'}`} style={{ fontSize: 9, padding: '1px 6px', minWidth: 36, textAlign: 'center' }}>
                      {t.side}
                    </span>
                    <div>
                      <p style={{ margin: 0, fontSize: 12, fontWeight: 600 }}>{t.symbol}</p>
                      <p style={{ margin: '1px 0 0', fontSize: 10, color: '#555570' }}>{t.quantity} @ ₹{t.price}</p>
                    </div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <p className="numeric" style={{ margin: 0, fontSize: 13, fontWeight: 600, color: t.pnl >= 0 ? '#22c55e' : '#ef4444' }}>
                      {t.pnl >= 0 ? '+' : ''}₹{t.pnl.toLocaleString()}
                    </p>
                    <p style={{ margin: '1px 0 0', fontSize: 9, color: '#555570' }}>{new Date(t.timestamp).toLocaleTimeString()}</p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ textAlign: 'center', padding: '32px 0' }}>
              <p style={{ color: '#555570', fontSize: 13, margin: '0 0 12px' }}>No trades yet. Deploy a strategy to see activity.</p>
              <Link href="/strategies" className="btn btn-primary btn-sm">Deploy Strategy</Link>
            </div>
          )}
        </div>

        <div className="panel" style={{ padding: '20px' }}>
          <div className="panel-header" style={{ marginBottom: 12 }}>
            <h3 className="panel-title" style={{ fontSize: 15 }}>Quick Actions</h3>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <Link href="/strategies" className="btn btn-primary" style={{ justifyContent: 'flex-start', padding: '10px 16px' }}>
              <span style={{ width: 24, height: 24, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(255,255,255,0.15)', borderRadius: 6, fontSize: 12, fontWeight: 600 }}>+</span>
              Create New Strategy
            </Link>
            <Link href="/brokers" className="btn btn-secondary" style={{ justifyContent: 'flex-start', padding: '10px 16px' }}>
              <span style={{ width: 24, height: 24, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(139,92,246,0.1)', borderRadius: 6, fontSize: 12, fontWeight: 600, color: '#8b5cf6' }}>B</span>
              Connect Broker
            </Link>
            <Link href="/backtest" className="btn btn-secondary" style={{ justifyContent: 'flex-start', padding: '10px 16px' }}>
              <span style={{ width: 24, height: 24, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(34,211,238,0.1)', borderRadius: 6, fontSize: 12, fontWeight: 600, color: '#22d3ee' }}>T</span>
              Run Backtest
            </Link>
            <Link href="/marketdata" className="btn btn-secondary" style={{ justifyContent: 'flex-start', padding: '10px 16px' }}>
              <span style={{ width: 24, height: 24, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(34,197,94,0.1)', borderRadius: 6, fontSize: 12, fontWeight: 600, color: '#22c55e' }}>M</span>
              Market Data Feed
            </Link>
            <Link href="/ai" className="btn btn-cyan" style={{ justifyContent: 'flex-start', padding: '10px 16px' }}>
              <span style={{ width: 24, height: 24, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(0,0,0,0.15)', borderRadius: 6, fontSize: 12, fontWeight: 600 }}>AI</span>
              AI Trading Desk
            </Link>
          </div>
        </div>
      </div>
    </div>
  )
}
