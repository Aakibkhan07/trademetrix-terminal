'use client'

import Link from 'next/link'
import { useApi } from '@/lib/use-api'
import { SkeletonGrid } from '@/components/skeleton'
import { ErrorMessage } from '@/components/error-message'

interface Funds {
  total_margin: number
  used_margin: number
  available_margin: number
  payin?: number
  payout?: number
  collateral?: number
  m2m_unrealised?: number
}

interface PnlResponse {
  pnl: {
    daily?: number
    realised_pnl?: number
    unrealised_pnl?: number
  } | null
  period: string
  broker: string | null
}

export default function FundsPage() {
  const { data: fundsData, loading: fundsLoading, error: fundsError } = useApi<{ funds: Funds }>('/engine/funds')
  const { data: pnlData, loading: pnlLoading, error: pnlError } = useApi<PnlResponse>('/analytics/pnl?period=1d')

  const loading = fundsLoading || pnlLoading
  const error = fundsError || pnlError

  if (loading) return <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}><SkeletonGrid count={4} /></div>
  if (error) return <ErrorMessage message="Failed to load funds" onRetry={() => window.location.reload()} />

  const funds = fundsData?.funds
  const pnl = pnlData?.pnl ?? null
  const broker = pnlData?.broker ?? null
  const hasBroker = funds && (funds.total_margin > 0 || funds.available_margin > 0 || broker)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1 style={{ fontFamily: 'var(--font-body)', fontWeight: 700, fontSize: 18, margin: 0, color: 'var(--text)' }}>Funds</h1>
          <p style={{ color: 'var(--text-sub)', fontSize: 12, margin: '2px 0 0' }}>
            Available capital and margin {broker ? `· ${broker}` : ''}
          </p>
        </div>
        <Link href="/brokers" className="t-btn t-btn-sm" style={{ textDecoration: 'none', fontSize: 10 }}>
          Manage Brokers
        </Link>
      </div>

      {!hasBroker && (
        <div className="t-panel" style={{ padding: 24, textAlign: 'center' }}>
          <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text)', marginBottom: 6 }}>No broker connected</div>
          <p style={{ fontSize: 12, color: 'var(--text-faint)', margin: '0 0 16px' }}>
            Connect a broker to see your live funds, margin and buying power.
          </p>
          <Link href="/brokers" className="t-btn t-btn-primary t-btn-sm" style={{ textDecoration: 'none', fontSize: 11 }}>
            Connect Broker
          </Link>
        </div>
      )}

      {hasBroker && funds && (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10 }}>
            {[
              { label: 'Total Margin', value: funds.total_margin || 0, color: 'var(--cyan)' },
              { label: 'Used Margin', value: funds.used_margin || 0, color: 'var(--amber)' },
              { label: 'Available Margin', value: funds.available_margin || 0, color: 'var(--green)' },
            ].map(m => (
              <div key={m.label} className="t-panel" style={{ padding: 12 }}>
                <div style={{ fontSize: 10, color: 'var(--text-faint)', fontWeight: 700, marginBottom: 4 }}>{m.label}</div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 16, fontWeight: 700, color: 'var(--text)', marginBottom: 6 }}>
                  ₹{m.value.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                </div>
                <div className="t-progress">
                  <div className="t-progress-fill" style={{ width: `${funds.total_margin ? Math.min((m.value / funds.total_margin) * 100, 100) : 0}%`, background: m.color }} />
                </div>
              </div>
            ))}
          </div>

          <div className="t-panel" style={{ padding: 12 }}>
            <div style={{ fontSize: 10, color: 'var(--text-faint)', fontWeight: 700, marginBottom: 8 }}>Margin Breakdown</div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 8 }}>
              {[
                { label: 'Pay-in', value: funds.payin ?? 0 },
                { label: 'Pay-out', value: funds.payout ?? 0 },
                { label: 'Collateral', value: funds.collateral ?? 0 },
                { label: 'MTM (Unrealized)', value: funds.m2m_unrealised ?? 0 },
              ].map(m => (
                <div key={m.label} style={{ padding: '8px 10px', borderRadius: 6, background: 'color-mix(in srgb, var(--violet) 4%, transparent)' }}>
                  <div style={{ fontSize: 9, color: 'var(--text-faint)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 2 }}>{m.label}</div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 14, fontWeight: 700, fontVariantNumeric: 'tabular-nums', color: m.value >= 0 ? 'var(--text)' : 'var(--text-red)' }}>
                    ₹{m.value.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {pnl && (
            <div className="t-panel" style={{ padding: 12 }}>
              <div style={{ fontSize: 10, color: 'var(--text-faint)', fontWeight: 700, marginBottom: 8 }}>P&L</div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 8 }}>
                {[
                  { label: 'Today (realized)', value: pnl.daily ?? 0, color: (pnl.daily ?? 0) >= 0 ? 'var(--text-green)' : 'var(--text-red)' },
                  { label: 'Realized', value: pnl.realised_pnl ?? 0, color: (pnl.realised_pnl ?? 0) >= 0 ? 'var(--text-green)' : 'var(--text-red)' },
                  { label: 'Unrealized', value: pnl.unrealised_pnl ?? 0, color: (pnl.unrealised_pnl ?? 0) >= 0 ? 'var(--text-green)' : 'var(--text-red)' },
                ].map(m => (
                  <div key={m.label} style={{ padding: '8px 10px', borderRadius: 6, background: 'color-mix(in srgb, var(--violet) 4%, transparent)' }}>
                    <div style={{ fontSize: 9, color: 'var(--text-faint)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 2 }}>{m.label}</div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 14, fontWeight: 700, fontVariantNumeric: 'tabular-nums', color: m.color }}>
                      {m.value >= 0 ? '+' : ''}{m.value.toFixed(0)}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          <p style={{ fontSize: 10, color: 'var(--text-faint)', margin: 0 }}>
            Funds data is fetched live from your broker. Broker connection and tokens are managed on the Brokers page.
          </p>
        </>
      )}
    </div>
  )
}
