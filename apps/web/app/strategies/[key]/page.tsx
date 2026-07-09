'use client'

import { useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import { api } from '@/lib/api'
import { useToast } from '@/lib/use-toast'

interface RecentTrade {
  id: string
  symbol: string
  side: string
  quantity: number
  price: number
  status: string
  filled_quantity: number
  average_price: number
  is_paper: boolean
  created_at: string
}

interface StrategyDetail {
  key: string
  name: string
  description: string
  required_tier: string
  category: string
  user_count: number
  total_trades: number
  total_pnl: number
  win_rate: number
  avg_return: number
  recent_trades: RecentTrade[]
}

const TIER_COLORS: Record<string, string> = {
  free: 'color-mix(in srgb, var(--text-sub) 15%, transparent)',
  starter: 'color-mix(in srgb, var(--cyan) 15%, transparent)',
  pro: 'color-mix(in srgb, var(--violet) 15%, transparent)',
  enterprise: 'color-mix(in srgb, var(--red) 15%, transparent)',
}

const TIER_TEXT: Record<string, string> = {
  free: 'var(--text-sub)',
  starter: 'var(--cyan)',
  pro: 'var(--violet)',
  enterprise: 'var(--red)',
}

function MetricCard({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div style={{
      background: 'var(--panel)', border: '1px solid var(--border)',
      borderRadius: 'var(--radius-md)', padding: '14px 16px',
    }}>
      <div style={{ fontSize: 10, color: 'var(--text-faint)', marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 18, fontWeight: 700, color: color || 'var(--text)' }}>{value}</div>
    </div>
  )
}

export default function StrategyDetailPage() {
  const params = useParams()
  const router = useRouter()
  const { toast } = useToast()
  const key = params.key as string

  const [detail, setDetail] = useState<StrategyDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [deploying, setDeploying] = useState(false)

  useEffect(() => {
    if (!key) return
    setLoading(true)
    setError('')
    api.get<StrategyDetail>(`/strategies/${key}/detail`)
      .then(setDetail)
      .catch(e => setError(e instanceof Error ? e.message : 'Failed to load strategy'))
      .finally(() => setLoading(false))
  }, [key])

  const handleDeploy = async () => {
    if (!detail) return
    setDeploying(true)
    try {
      await api.userStrategies.create({
        name: detail.name,
        strategy_type: detail.key,
        config: { symbol: 'NIFTY' },
      })
      toast('success', `${detail.name} deployed! Configure it in Strategies.`)
    } catch {
      toast('error', `Failed to deploy ${detail.name}`)
    } finally {
      setDeploying(false)
    }
  }

  if (loading) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div style={{ width: '40%', height: 20, background: 'color-mix(in srgb, var(--text-inverse) 4%, transparent)', borderRadius: 4 }} />
        <div style={{ width: '70%', height: 12, background: 'color-mix(in srgb, var(--text-inverse) 3%, transparent)', borderRadius: 4 }} />
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10 }}>
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} style={{ height: 80, background: 'color-mix(in srgb, var(--text-inverse) 3%, transparent)', borderRadius: 'var(--radius-md)' }} />
          ))}
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div style={{
        background: 'color-mix(in srgb, var(--red) 8%, transparent)', border: '1px solid color-mix(in srgb, var(--red) 20%, transparent)',
        borderRadius: 'var(--radius-md)', padding: '10px 12px', color: 'var(--text-red)', fontSize: 12,
      }}>
        {error}
      </div>
    )
  }

  if (!detail) return null

  const catLabel = detail.category.charAt(0).toUpperCase() + detail.category.slice(1).replace('_', ' ')

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Back button */}
      <Link
        href="/marketplace"
        style={{
          display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 12,
          color: 'var(--text-sub)', textDecoration: 'none',
        }}
      >
        ← Back to Marketplace
      </Link>

      {/* Header */}
      <div style={{
        background: 'var(--panel)', border: '1px solid var(--border)',
        borderRadius: 'var(--radius-md)', padding: 20,
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
              <h1 style={{ fontFamily: 'var(--font-body)', fontWeight: 700, fontSize: 20, margin: 0, color: 'var(--text)' }}>
                {detail.name}
              </h1>
              <span style={{
                display: 'inline-flex', alignItems: 'center', padding: '2px 8px',
                borderRadius: 4, fontSize: 9, fontWeight: 500,
                background: TIER_COLORS[detail.required_tier] || TIER_COLORS.free,
                color: TIER_TEXT[detail.required_tier] || TIER_TEXT.free,
                border: `1px solid ${TIER_COLORS[detail.required_tier] || TIER_COLORS.free}`,
                textTransform: 'capitalize',
              }}>
                {detail.required_tier}
              </span>
              <span className="t-badge t-badge-violet" style={{ fontSize: 9 }}>{catLabel}</span>
            </div>
            <p style={{ fontSize: 11, color: 'var(--text-sub)', margin: 0, lineHeight: 1.5 }}>{detail.description}</p>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <span style={{ fontSize: 11, color: 'var(--text-faint)' }}>
              {detail.user_count} user{detail.user_count !== 1 ? 's' : ''}
            </span>
          </div>
        </div>

        {/* Deploy button */}
        <button
          className="t-btn t-btn-primary"
          onClick={handleDeploy}
          disabled={deploying}
        >
          {deploying ? 'Deploying...' : 'Deploy Strategy'}
        </button>
      </div>

      {/* Performance Metrics */}
      <div>
        <h2 style={{ fontFamily: 'var(--font-body)', fontSize: 14, fontWeight: 700, margin: '0 0 10px', color: 'var(--text)' }}>
          Performance Metrics
        </h2>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 10 }}>
          <MetricCard label="Total Trades" value={String(detail.total_trades)} />
          <MetricCard label="Win Rate" value={`${detail.win_rate}%`} color="var(--text-green)" />
          <MetricCard label="Avg Return" value={detail.avg_return > 0 ? `+${detail.avg_return}%` : `${detail.avg_return}%`} color={detail.avg_return >= 0 ? 'var(--text-green)' : 'var(--text-red)'} />
          <MetricCard label="Total P&L" value={`₹${detail.total_pnl.toLocaleString()}`} color={detail.total_pnl >= 0 ? 'var(--text-green)' : 'var(--text-red)'} />
        </div>
      </div>

      {/* Recent Trades */}
      {detail.recent_trades.length > 0 && (
        <div>
          <h2 style={{ fontFamily: 'var(--font-body)', fontSize: 14, fontWeight: 700, margin: '0 0 10px', color: 'var(--text)' }}>
            Recent Trades
          </h2>
          <div style={{
            background: 'var(--panel)', border: '1px solid var(--border)',
            borderRadius: 'var(--radius-md)', overflow: 'hidden',
          }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border)' }}>
                  <th style={{ padding: '10px 12px', textAlign: 'left', color: 'var(--text-faint)', fontWeight: 500 }}>Symbol</th>
                  <th style={{ padding: '10px 12px', textAlign: 'left', color: 'var(--text-faint)', fontWeight: 500 }}>Side</th>
                  <th style={{ padding: '10px 12px', textAlign: 'right', color: 'var(--text-faint)', fontWeight: 500 }}>Qty</th>
                  <th style={{ padding: '10px 12px', textAlign: 'right', color: 'var(--text-faint)', fontWeight: 500 }}>Price</th>
                  <th style={{ padding: '10px 12px', textAlign: 'center', color: 'var(--text-faint)', fontWeight: 500 }}>Status</th>
                  <th style={{ padding: '10px 12px', textAlign: 'right', color: 'var(--text-faint)', fontWeight: 500 }}>Date</th>
                </tr>
              </thead>
              <tbody>
                {detail.recent_trades.map((t) => (
                  <tr key={t.id} style={{ borderBottom: '1px solid var(--border)' }}>
                    <td style={{ padding: '8px 12px', color: 'var(--text)' }}>{t.symbol}</td>
                    <td style={{
                      padding: '8px 12px',
                      color: t.side === 'BUY' ? 'var(--text-green)' : 'var(--text-red)',
                      fontWeight: 600,
                    }}>
                      {t.side}
                    </td>
                    <td style={{ padding: '8px 12px', textAlign: 'right', color: 'var(--text)' }}>{t.quantity}</td>
                    <td style={{ padding: '8px 12px', textAlign: 'right', color: 'var(--text)' }}>
                      {t.price > 0 ? `₹${t.price.toLocaleString()}` : '-'}
                    </td>
                    <td style={{ padding: '8px 12px', textAlign: 'center' }}>
                      <span className={`t-badge ${
                        t.status === 'FILLED' ? 't-badge-green' :
                        t.status === 'REJECTED' || t.status === 'CANCELLED' ? 't-badge-red' :
                        't-badge-sub'
                      }`} style={{ fontSize: 8 }}>
                        {t.status}
                      </span>
                    </td>
                    <td style={{ padding: '8px 12px', textAlign: 'right', color: 'var(--text-faint)', fontSize: 10 }}>
                      {t.created_at ? new Date(t.created_at).toLocaleDateString() : '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {detail.recent_trades.length === 0 && (
        <div style={{
          background: 'rgba(34,211,238,0.04)', border: '1px solid rgba(34,211,238,0.1)',
          borderRadius: 'var(--radius-md)', padding: 24, textAlign: 'center',
        }}>
          <p style={{ color: 'var(--text-sub)', fontSize: 13, margin: '0 0 4px' }}>No trades yet</p>
          <p style={{ color: 'var(--text-faint)', fontSize: 11, margin: 0 }}>
            Deploy this strategy to start trading
          </p>
        </div>
      )}
    </div>
  )
}
