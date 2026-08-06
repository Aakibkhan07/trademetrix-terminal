'use client'

/**
 * KPI / stat card. Variants reproduce the four pre-existing local implementations
 * byte-for-byte (backtest `kpiCard`, admin/beta `KpiCard`, strategies `MetricCard`,
 * pnl-dashboard `StatCard`, backtest trade-intelligence `tiCard`).
 */
export function KpiCard({ label, value, sub, color, variant = 'panel', prefix = '₹' }: {
  label: string
  value: string | number
  sub?: string
  color?: string
  variant?: 'panel' | 'beta' | 'metric' | 'stat' | 'ti'
  prefix?: string
}) {
  if (variant === 'beta') {
    return (
      <div className="t-panel" style={{ padding: '14px 16px', minWidth: 140 }}>
        <div style={{ fontSize: 10, color: 'var(--text-faint)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' }}>{label}</div>
        <div style={{ fontSize: 22, fontWeight: 700, fontFamily: 'Outfit', marginTop: 6 }}>{value}</div>
        {sub && <div style={{ fontSize: 10, color: 'var(--text-faint)', marginTop: 4 }}>{sub}</div>}
      </div>
    )
  }

  if (variant === 'metric') {
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

  if (variant === 'stat') {
    const numeric = typeof value === 'number'
    const val = numeric ? `${prefix}${Math.abs(value).toLocaleString()}` : String(value)
    return (
      <div className="t-panel" style={{ padding: '14px 16px', borderLeft: `3px solid ${color}` }}>
        <div className="t-faint" style={{ fontSize: 9, fontWeight: 600, letterSpacing: '0.04em' }}>{label}</div>
        <div style={{ fontSize: 18, fontWeight: 700, fontFamily: 'var(--font-mono)', color: numeric && value < 0 ? 'var(--red)' : 'var(--text)' }}>
          {numeric && value < 0 ? '-' : ''}{val}
        </div>
      </div>
    )
  }

  if (variant === 'ti') {
    return (
      <div style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', padding: '6px 8px' }}>
        <div style={{ fontSize: 9, color: 'var(--text-faint)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em' }}>{label}</div>
        <div style={{ fontSize: 12, fontWeight: 700, fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums', color: color || 'var(--text)', marginTop: 1 }}>{value}</div>
      </div>
    )
  }

  return (
    <div className="t-panel" style={{ padding: 12 }}>
      <div style={{ fontSize: 10, color: 'var(--text-faint)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 2 }}>{label}</div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 19, fontWeight: 700, fontVariantNumeric: 'tabular-nums', color: color || 'var(--text)', marginBottom: 1 }}>{value}</div>
      {sub && <div style={{ fontSize: 10, color: 'var(--text-faint)' }}>{sub}</div>}
    </div>
  )
}
