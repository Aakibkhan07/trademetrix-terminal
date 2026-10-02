'use client'

import Link from 'next/link'
import { useApi } from '@/lib/use-api'
import { SkeletonGrid } from '@/components/skeleton'
import { ErrorMessage } from '@/components/error-message'

// The two `/analytics/pnl` response shapes and the tile mapping live in `lib/pnl.ts`, with
// assertions in `lib/pnl.test.ts`. Kept out of the page rather than inline because the bug
// this replaced was a silent zero, and inline JSX cannot be asserted on.
import { formatPnlTile, pnlTiles } from '@/lib/pnl'
import type { CumulativePnl, DailyPnl, PnlEnvelope } from '@/lib/pnl'

interface Funds {
  total_margin: number
  used_margin: number
  available_margin: number
  payin?: number
  payout?: number
  collateral?: number
  m2m_unrealised?: number
}

export default function FundsPage() {
  const { data: fundsData, loading: fundsLoading, error: fundsError } = useApi<{ funds: Funds }>('/engine/funds')
  // Two calls because the endpoint has two shapes, not because two numbers are wanted.
  // `/analytics` already does exactly this; this page was trying to get both from one.
  const { data: dailyPnlData, loading: dailyPnlLoading, error: dailyPnlError } =
    useApi<PnlEnvelope<DailyPnl>>('/analytics/pnl?period=1d')
  const { data: cumPnlData, loading: cumPnlLoading, error: cumPnlError } =
    useApi<PnlEnvelope<CumulativePnl>>('/analytics/pnl?period=1w')

  const loading = fundsLoading || dailyPnlLoading || cumPnlLoading
  const error = fundsError || dailyPnlError || cumPnlError

  if (loading) return <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}><SkeletonGrid count={4} /></div>
  if (error) return <ErrorMessage message="Failed to load funds" onRetry={() => window.location.reload()} />

  const funds = fundsData?.funds
  const dailyPnl = dailyPnlData?.pnl ?? null
  const cumPnl = cumPnlData?.pnl ?? null
  const broker = dailyPnlData?.broker ?? cumPnlData?.broker ?? null
  const hasBroker = funds && (funds.total_margin > 0 || funds.available_margin > 0 || broker)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1 style={{ fontFamily: 'var(--font-sans)', fontWeight: 700, fontSize: 22, margin: 0, color: 'var(--text)' }}>Funds</h1>
          <p style={{ color: 'var(--text-sub)', fontSize: 14, margin: '2px 0 0' }}>
            Available capital and margin {broker ? `· ${broker}` : ''}
          </p>
        </div>
        <Link href="/brokers" className="t-btn t-btn-sm" style={{ textDecoration: 'none', fontSize: 12 }}>
          Manage Brokers
        </Link>
      </div>

      {!hasBroker && (
        <div className="t-panel" style={{ padding: 24, textAlign: 'center' }}>
          <div style={{ fontSize: 17, fontWeight: 700, color: 'var(--text)', marginBottom: 6 }}>No broker connected</div>
          <p style={{ fontSize: 14, color: 'var(--text-faint)', margin: '0 0 16px' }}>
            Connect a broker to see your live funds, margin and buying power.
          </p>
          <Link href="/brokers" className="t-btn t-btn-primary t-btn-sm" style={{ textDecoration: 'none', fontSize: 13 }}>
            Connect Broker
          </Link>
        </div>
      )}

      {hasBroker && funds && (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 10 }}>
            {[
              { label: 'Total Margin', value: funds.total_margin || 0, color: 'var(--cyan)' },
              { label: 'Used Margin', value: funds.used_margin || 0, color: 'var(--amber)' },
              { label: 'Available Margin', value: funds.available_margin || 0, color: 'var(--green)' },
            ].map(m => (
              <div key={m.label} className="t-panel" style={{ padding: 12 }}>
                <div style={{ fontSize: 12, color: 'var(--text-faint)', fontWeight: 700, marginBottom: 4 }}>{m.label}</div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 19, fontWeight: 700, color: 'var(--text)', marginBottom: 6 }}>
                  ₹{m.value.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                </div>
                <div className="t-progress">
                  <div className="t-progress-fill" style={{ width: `${funds.total_margin ? Math.min((m.value / funds.total_margin) * 100, 100) : 0}%`, background: m.color }} />
                </div>
              </div>
            ))}
          </div>

          <div className="t-panel" style={{ padding: 12 }}>
            <div style={{ fontSize: 12, color: 'var(--text-faint)', fontWeight: 700, marginBottom: 8 }}>Margin Breakdown</div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 8 }}>
              {[
                { label: 'Pay-in', value: funds.payin ?? 0 },
                { label: 'Pay-out', value: funds.payout ?? 0 },
                { label: 'Collateral', value: funds.collateral ?? 0 },
                { label: 'MTM (Unrealized)', value: funds.m2m_unrealised ?? 0 },
              ].map(m => (
                <div key={m.label} style={{ padding: '8px 10px', borderRadius: 6, background: 'var(--violet-dim)' }}>
                  <div style={{ fontSize: 11, color: 'var(--text-faint)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 2 }}>{m.label}</div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 17, fontWeight: 700, fontVariantNumeric: 'tabular-nums', color: m.value >= 0 ? 'var(--text)' : 'var(--text-red)' }}>
                    ₹{m.value.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {(dailyPnl || cumPnl) && (
            <div className="t-panel" style={{ padding: 12 }}>
              <div style={{ fontSize: 12, color: 'var(--text-faint)', fontWeight: 700, marginBottom: 8 }}>P&L</div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 8 }}>
                {/*
                  `value` is `number | null`, and null renders as a dash. The old version
                  used `?? 0`, which turned "this response never carried that field" into a
                  confident ₹0 — indistinguishable from a genuinely flat P&L, and wrong for
                  every tenant holding open positions. `/analytics` already renders '—' for
                  absent values; this page now matches it.
                */}
                {pnlTiles(dailyPnlData, cumPnlData).map(m => (
                  <div key={m.label} style={{ padding: '8px 10px', borderRadius: 6, background: 'var(--violet-dim)' }}>
                    <div style={{ fontSize: 11, color: 'var(--text-faint)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 2 }}>{m.label}</div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 17, fontWeight: 700, fontVariantNumeric: 'tabular-nums', color: m.tone === 'unknown' ? 'var(--text-faint)' : m.tone === 'up' ? 'var(--text-green)' : 'var(--text-red)' }}>
                      {formatPnlTile(m.value)}
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--text-faint)', marginTop: 1 }}>{m.hint}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          <p style={{ fontSize: 12, color: 'var(--text-faint)', margin: 0 }}>
            Funds data is fetched live from your broker. Broker connection and tokens are managed on the Brokers page.
          </p>
        </>
      )}
    </div>
  )
}
