'use client'

import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import Link from 'next/link'

interface DashboardData {
  user: { email: string; full_name: string }
  is_live: boolean
  strategies: number
  positions: number
}

const STRATEGY_CARDS = [
  { name: 'Momentum Pro', return_: '+32.4%', drawdown: '-8.2%', winRate: '68%', sharpe: '2.1', color: 'violet' },
  { name: 'Mean Reversion', return_: '+24.8%', drawdown: '-5.1%', winRate: '72%', sharpe: '1.8', color: 'cyan' },
  { name: 'Breakout Hunter', return_: '+45.2%', drawdown: '-15.3%', winRate: '55%', sharpe: '1.5', color: 'green' },
]

export default function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const load = async () => {
      try {
        const [user, liveStatus, runs, strategies] = await Promise.all([
          api.auth.me(),
          api.risk.liveStatus(),
          api.get('/api/v1/engine/runs').catch(() => ({ runs: [] })),
          api.strategies.list(),
        ])
        setData({
          user: user as unknown as { email: string; full_name: string },
          is_live: (liveStatus as { is_live: boolean }).is_live,
          positions: (runs as { runs: unknown[] }).runs.length,
          strategies: (strategies as { strategies: unknown[] }).strategies.length,
        })
      } catch {
        setData({
          user: { email: '', full_name: 'Trader' },
          is_live: false,
          positions: 0,
          strategies: 0,
        })
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  if (loading) {
    return <p style={{ color: '#8888a0' }}>Loading dashboard...</p>
  }

  return (
    <div>
      <div style={{ marginBottom: 32 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 4 }}>
          <h1 style={{ fontFamily: 'Outfit', fontSize: 28, margin: 0 }}>
            Welcome back, {data?.user?.full_name || 'Trader'}
          </h1>
          {data?.is_live ? (
            <span className="badge badge-red" style={{ padding: '4px 12px', fontSize: 11 }}>LIVE</span>
          ) : (
            <span className="badge badge-cyan" style={{ padding: '4px 12px', fontSize: 11 }}>PAPER</span>
          )}
        </div>
        <p style={{ color: '#8888a0', margin: 0, fontSize: 14 }}>
          Algorithmic trading terminal — {new Date().toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}
        </p>
      </div>

      <div className="grid-auto" style={{ marginBottom: 32 }}>
        <div className="glass-card">
          <p style={{ color: '#8888a0', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.08em', margin: '0 0 8px' }}>
            Active Strategies
          </p>
          <p style={{ fontSize: 28, fontWeight: 700, margin: 0, color: '#8b5cf6' }}>
            {data?.strategies || 0}
          </p>
        </div>
        <div className="glass-card">
          <p style={{ color: '#8888a0', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.08em', margin: '0 0 8px' }}>
            Running Positions
          </p>
          <p style={{ fontSize: 28, fontWeight: 700, margin: 0, color: '#22d3ee' }}>
            {data?.positions || 0}
          </p>
        </div>
        <Link href="/risk" style={{ textDecoration: 'none' }}>
          <div className="glass-card">
            <p style={{ color: '#8888a0', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.08em', margin: '0 0 8px' }}>
              Risk Status
            </p>
            <p style={{ fontSize: 14, margin: 0, color: '#22c55e', display: 'flex', alignItems: 'center' }}>
              <span className="status-dot active" />
              All clear
            </p>
          </div>
        </Link>
        <Link href="/strategies" style={{ textDecoration: 'none' }}>
          <div className="glass-card">
            <p style={{ color: '#8888a0', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.08em', margin: '0 0 8px' }}>
              Quick Action
            </p>
            <p style={{ fontSize: 14, margin: 0, color: '#22d3ee' }}>
              Create Strategy →
            </p>
          </div>
        </Link>
      </div>

      <h2 style={{ fontFamily: 'Outfit', fontSize: 18, margin: '0 0 16px', color: '#f0f0f5' }}>
        Top Strategies
      </h2>
      <div className="grid-3" style={{ marginBottom: 32 }}>
        {STRATEGY_CARDS.map((s) => (
          <div key={s.name} className="strategy-card">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
              <h3 style={{ fontFamily: 'Outfit', fontSize: 16, margin: 0 }}>{s.name}</h3>
              <span className={`badge badge-${s.color}`}>Strategy</span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <div className="metric">
                <span className="metric-label">Returns</span>
                <span className="metric-value" style={{ color: '#22c55e' }}>{s.return_}</span>
              </div>
              <div className="metric">
                <span className="metric-label">Max DD</span>
                <span className="metric-value" style={{ color: '#ef4444' }}>{s.drawdown}</span>
              </div>
              <div className="metric">
                <span className="metric-label">Win Rate</span>
                <span className="metric-value">{s.winRate}</span>
              </div>
              <div className="metric">
                <span className="metric-label">Sharpe</span>
                <span className="metric-value">{s.sharpe}</span>
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="grid-2">
        <div className="panel">
          <div className="panel-header">
            <h3 className="panel-title">Getting Started</h3>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <Link href="/brokers" className="btn btn-primary" style={{ justifyContent: 'flex-start' }}>
              Connect Your Broker
            </Link>
            <Link href="/strategies" className="btn btn-secondary" style={{ justifyContent: 'flex-start' }}>
              Deploy a Strategy
            </Link>
            <Link href="/backtest" className="btn btn-secondary" style={{ justifyContent: 'flex-start' }}>
              Run Backtest
            </Link>
          </div>
        </div>

        <div className="panel">
          <div className="panel-header">
            <h3 className="panel-title">Recent Activity</h3>
          </div>
          <p style={{ color: '#555570', fontSize: 13 }}>
            No recent activity to display. Connect a broker and start a strategy to see your trading activity here.
          </p>
        </div>
      </div>
    </div>
  )
}
