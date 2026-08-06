'use client'

import type { CSSProperties, ReactNode } from 'react'
import { Dot } from '@/components/ui/badge'
import { SkeletonBar } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/ui/empty-state'

/**
 * Shared shell for every Live Dashboard widget. Normalises the five widget
 * states a live wall must render without breaking:
 *   - loading      → skeleton body
 *   - error        → inline error + Retry
 *   - offline      → replaces the body (browser offline)
 *   - market closed → amber note bar ABOVE the (still-visible, cached) data
 *   - empty        → EmptyState when the caller has no rows
 */
export function WidgetFrame({
  title,
  subtitle,
  actions,
  loading = false,
  error,
  onRetry,
  offline = false,
  marketClosed = false,
  empty = false,
  emptyMessage = 'No data',
  style,
  children,
}: {
  title: string
  subtitle?: string
  actions?: ReactNode
  loading?: boolean
  error?: string | null
  onRetry?: () => void
  offline?: boolean
  marketClosed?: boolean
  empty?: boolean
  emptyMessage?: string
  style?: CSSProperties
  children: ReactNode
}) {
  return (
    <div className="t-panel" style={{ display: 'flex', flexDirection: 'column', minHeight: 0, ...style }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 12px', borderBottom: '1px solid var(--border)' }}>
        <h3 style={{ margin: 0, fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--text-sub)' }}>
          {title}
        </h3>
        <Dot variant={offline ? 'red' : 'green'} pulse={!offline && !marketClosed} />
        {subtitle && <span className="t-faint" style={{ fontSize: 10 }}>{subtitle}</span>}
        {marketClosed && (
          <span className="t-badge t-badge-yellow" style={{ fontSize: 9, marginLeft: 'auto' }}>
            ☾ Market closed
          </span>
        )}
        {actions && !marketClosed && <span style={{ marginLeft: 'auto' }}>{actions}</span>}
      </div>

      <div style={{ padding: 10, overflow: 'auto', flex: 1, minHeight: 0 }}>
        {offline ? (
          <EmptyState title="You're offline" description="Reconnect to stream live positions, orders and signals." />
        ) : error ? (
          <div style={{ textAlign: 'center', padding: 24 }}>
            <p style={{ margin: '0 0 12px', fontSize: 12, color: 'var(--text-red)' }}>{error}</p>
            {onRetry && <button className="t-btn t-btn-sm" onClick={onRetry} style={{ fontSize: 11 }}>Retry</button>}
          </div>
        ) : loading ? (
          <div style={{ display: 'grid', gap: 8 }}>
            <SkeletonBar w="100%" />
            <SkeletonBar w="80%" />
            <SkeletonBar w="60%" />
          </div>
        ) : empty ? (
          <EmptyState title={emptyMessage} style={{ padding: 24 }} />
        ) : (
          children
        )}
      </div>
    </div>
  )
}