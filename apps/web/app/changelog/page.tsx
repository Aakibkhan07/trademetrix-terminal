'use client'

import { useState } from 'react'
import { useToast } from '@/lib/use-toast'
import { EmptyState } from '@/components/empty-state'
import { ErrorMessage } from '@/components/error-message'
import { SkeletonGrid } from '@/components/skeleton'

interface ChangeEntry {
  text: string
}

interface VersionEntry {
  version: string
  date: string
  isCurrent?: boolean
  new: ChangeEntry[]
  improved: ChangeEntry[]
  fixed: ChangeEntry[]
}

const VERSIONS: VersionEntry[] = [
  {
    version: '1.0.0-beta',
    date: 'June 2026',
    isCurrent: true,
    new: [
      { text: 'Real-time order transparency dashboard with full lifecycle tracking' },
      { text: 'AI-powered strategy assistant with natural language commands' },
      { text: 'Kill switch with one-click panic close across all brokers' },
      { text: 'Multi-broker order routing with automatic failover' },
      { text: 'Paper trading mode with realistic market simulation' },
      { text: 'Advanced backtesting engine with slippage & latency modeling' },
      { text: 'Role-based access control for team accounts' },
    ],
    improved: [
      { text: 'Reduced order latency by 40% with connection pooling' },
      { text: 'Redesigned terminal UI with improved chart interactions' },
      { text: 'Faster strategy deployment with parallel compilation' },
      { text: 'Enhanced error messages with actionable guidance' },
    ],
    fixed: [
      { text: 'Edge case where orders duplicated under high frequency' },
      { text: 'WebSocket reconnection not restoring subscription state' },
      { text: 'Incorrect P&L calculation on split-adjusted symbols' },
      { text: 'Session expiry not redirecting to login gracefully' },
    ],
  },
  {
    version: '0.9.0',
    date: 'April 2026',
    new: [
      { text: 'Strategy catalog with one-click deployment' },
      { text: 'RiskGuard pre-trade risk checks' },
      { text: 'Portfolio-level exposure tracking' },
      { text: 'Email and webhook alert system' },
    ],
    improved: [
      { text: 'Dashboard performance with virtualized tables' },
      { text: 'Broker connection wizard with OAuth improvements' },
      { text: 'API rate limiting with clearer error responses' },
    ],
    fixed: [
      { text: 'Memory leak in WebSocket message handler' },
      { text: 'Strategy scheduler not respecting timezone offsets' },
      { text: 'Account page crashing on null position data' },
    ],
  },
  {
    version: '0.8.0',
    date: 'February 2026',
    new: [
      { text: 'Initial real-time market data streaming' },
      { text: 'Basic order entry and position management' },
      { text: 'Single broker connection (Alpaca)' },
      { text: 'Core strategy execution engine' },
      { text: 'User authentication and account management' },
    ],
    improved: [
      { text: 'Responsive layout for mobile and tablet' },
      { text: 'Dark mode with customizable theme' },
    ],
    fixed: [
      { text: 'Various UI rendering bugs on initial load' },
    ],
  },
]

export default function ChangelogPage() {
  const { toast } = useToast()

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24, maxWidth: 720 }}>
      <div className="t-page-header">
        <div>
          <h1 className="t-page-title">Changelog</h1>
          <p className="t-page-subtitle">Release notes and version history</p>
        </div>
      </div>

      {VERSIONS.map((ver, i) => (
        <div key={ver.version} className="t-panel" style={{ padding: 0, position: 'relative' }}>
          {/* Timeline line */}
          {i < VERSIONS.length - 1 && (
            <div style={{
              position: 'absolute', left: 28, top: 60, bottom: -12,
              width: 2, background: 'var(--border)', zIndex: 0,
            }} />
          )}

          {/* Version header with dot */}
          <div className="t-panel-header" style={{ gap: 12 }}>
            <div style={{
              width: 12, height: 12, borderRadius: '50%',
              background: ver.isCurrent ? 'var(--green)' : 'var(--faint)',
              flexShrink: 0, zIndex: 1,
            }} />
            <div style={{ flex: 1 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <h3 className="t-panel-title" style={{ margin: 0 }}>
                  v{ver.version}
                </h3>
                {ver.isCurrent && (
                  <span className="t-badge t-badge-green">Latest</span>
                )}
              </div>
              <div className="t-faint" style={{ fontSize: 11 }}>{ver.date}</div>
            </div>
          </div>

          <div className="t-panel-body" style={{ paddingTop: 0 }}>
            {ver.new.length > 0 && (
              <div style={{ marginBottom: 14 }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--green)', textTransform: 'uppercase', marginBottom: 6 }}>New</div>
                <ul style={{ margin: 0, paddingLeft: 16, fontSize: 12, lineHeight: 1.8 }}>
                  {ver.new.map(item => (
                    <li key={item.text} style={{ color: 'var(--fg)' }}>{item.text}</li>
                  ))}
                </ul>
              </div>
            )}
            {ver.improved.length > 0 && (
              <div style={{ marginBottom: 14 }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--cyan)', textTransform: 'uppercase', marginBottom: 6 }}>Improved</div>
                <ul style={{ margin: 0, paddingLeft: 16, fontSize: 12, lineHeight: 1.8 }}>
                  {ver.improved.map(item => (
                    <li key={item.text} style={{ color: 'var(--fg)' }}>{item.text}</li>
                  ))}
                </ul>
              </div>
            )}
            {ver.fixed.length > 0 && (
              <div>
                <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--amber)', textTransform: 'uppercase', marginBottom: 6 }}>Fixed</div>
                <ul style={{ margin: 0, paddingLeft: 16, fontSize: 12, lineHeight: 1.8 }}>
                  {ver.fixed.map(item => (
                    <li key={item.text} style={{ color: 'var(--fg)' }}>{item.text}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}
