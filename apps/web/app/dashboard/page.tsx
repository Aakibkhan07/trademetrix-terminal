'use client'

import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import Link from 'next/link'

interface DashboardData {
  user: { email: string; full_name: string }
  funds: { available_margin: number }
  positions: number
  strategies: number
  is_live: boolean
}

export default function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const load = async () => {
      try {
        const [user, liveStatus, funds, positions, strategies] = await Promise.all([
          api.auth.me(),
          api.risk.liveStatus(),
          api.get('/api/v1/brokers/credentials').catch(() => ({ credentials: [] })),
          api.get('/api/v1/engine/runs').catch(() => ({ runs: [] })),
          api.strategies.list(),
        ])
        setData({
          user: user as unknown as { email: string; full_name: string },
          is_live: (liveStatus as { is_live: boolean }).is_live,
          funds: { available_margin: 0 },
          positions: (positions as { runs: unknown[] }).runs.length,
          strategies: (strategies as { strategies: unknown[] }).strategies.length,
        })
      } catch {
        setData({
          user: { email: '', full_name: 'User' },
          is_live: false,
          funds: { available_margin: 0 },
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
        <h1 style={{ fontFamily: 'Outfit', fontSize: 28, margin: 0 }}>
          Welcome back, {data?.user?.full_name || 'Trader'}
        </h1>
        <p style={{ color: '#8888a0', marginTop: 4, fontSize: 14 }}>
          {data?.is_live ? (
            <span className="badge badge-red">LIVE MODE</span>
          ) : (
            <span className="badge badge-cyan">PAPER MODE</span>
          )}
          {' '}Trade Metrix Terminal
        </p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 16 }}>
        <div className="glass-card">
          <p style={{ color: '#8888a0', fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.05em', margin: '0 0 8px' }}>
            Available Margin
          </p>
          <p className="numeric neon-cyan" style={{ fontSize: 24, fontWeight: 600, margin: 0 }}>
            {(data?.funds?.available_margin || 0).toLocaleString()}
          </p>
        </div>

        <div className="glass-card">
          <p style={{ color: '#8888a0', fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.05em', margin: '0 0 8px' }}>
            Active Strategies
          </p>
          <p className="numeric neon-violet" style={{ fontSize: 24, fontWeight: 600, margin: 0 }}>
            {data?.strategies || 0}
          </p>
        </div>

        <div className="glass-card">
          <p style={{ color: '#8888a0', fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.05em', margin: '0 0 8px' }}>
            Mode
          </p>
          <p style={{ fontSize: 24, fontWeight: 600, margin: 0 }}>
            {data?.is_live ? (
              <span style={{ color: '#ef4444' }}>LIVE</span>
            ) : (
              <span style={{ color: '#22d3ee' }}>PAPER</span>
            )}
          </p>
        </div>

        <Link href="/risk" style={{ textDecoration: 'none' }}>
          <div className="glass-card" style={{ cursor: 'pointer' }}>
            <p style={{ color: '#8888a0', fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.05em', margin: '0 0 8px' }}>
              Risk Status
            </p>
            <p style={{ fontSize: 14, margin: 0, color: '#22c55e' }}>
              <span className="status-dot active" />
              All clear
            </p>
          </div>
        </Link>
      </div>

      <div style={{ marginTop: 32, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <div className="panel">
          <div className="panel-header">
            <h3 className="panel-title">Quick Actions</h3>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <Link href="/strategies" className="btn btn-primary">
              Create Strategy
            </Link>
            <Link href="/brokers" className="btn btn-secondary">
              Connect Broker
            </Link>
            <Link href="/ai" className="btn btn-cyan">
              AI Trading Desk
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
