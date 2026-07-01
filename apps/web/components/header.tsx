'use client'

import { usePathname } from 'next/navigation'
import { useMarketData } from '@/lib/use-market-data'
import { useAuth } from '@/lib/auth-context'
import { useTheme } from '@/lib/use-theme'

const PAGE_TABS: Record<string, { label: string; tabs: { key: string; label: string }[] }> = {
  '/dashboard': { label: 'Dashboard', tabs: [] },
  '/terminal': { label: 'Terminal', tabs: [{ key: 'overview', label: 'Overview' }, { key: 'positions', label: 'Positions' }, { key: 'orders', label: 'Orders' }] },
  '/trade': { label: 'Trade', tabs: [{ key: 'options', label: 'Options' }, { key: 'futures', label: 'Futures' }] },
  '/positions': { label: 'Positions', tabs: [{ key: 'positions', label: 'Positions' }, { key: 'orders', label: 'Orders' }, { key: 'holdings', label: 'Holdings' }] },
  '/marketdata': { label: 'Market Data', tabs: [{ key: 'watch', label: 'Watch' }, { key: 'chain', label: 'Chain' }] },
  '/strategies': { label: 'Strategies', tabs: [] },
  '/brokers': { label: 'Brokers', tabs: [] },
  '/backtest': { label: 'Backtest', tabs: [] },
  '/journal': { label: 'Journal', tabs: [] },
  '/account': { label: 'Account', tabs: [] },
  '/risk': { label: 'Risk', tabs: [] },
  '/ai': { label: 'AI Desk', tabs: [] },
  '/transparency': { label: 'Reports', tabs: [] },
}

export default function Header() {
  const pathname = usePathname()
  const { connected, ticks } = useMarketData()
  const { user } = useAuth()
  const { theme, toggleTheme } = useTheme()

  if (pathname === '/auth') return null

  const nifty = ticks['NSE:NIFTY50-INDEX']
  const base = '/' + pathname.split('/')[1]
  const pageInfo = PAGE_TABS[base] || PAGE_TABS['/dashboard']

  return (
    <header className="t-header">
      <div className="t-header-left">
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ fontFamily: 'var(--font-display)', fontSize: 13, fontWeight: 600, color: 'var(--text)' }}>
            {pageInfo?.label || 'Dashboard'}
          </span>
          <span style={{ fontSize: 9, color: 'var(--text-faint)', fontFamily: 'var(--font-mono)', padding: '1px 6px', background: 'var(--panel-2)', borderRadius: 4 }}>
            v0.1
          </span>
        </div>
      </div>

      <div className="t-header-center">
        {pageInfo?.tabs && pageInfo.tabs.length > 0 && (
          <div className="t-header-nav">
            {pageInfo.tabs.map((tab) => (
              <button key={tab.key} className="t-header-nav-item active">
                {tab.label}
              </button>
            ))}
          </div>
        )}

        <div className="t-header-search">
          <span className="t-header-search-icon">Q</span>
          <input placeholder="Search symbols, strategies..." />
        </div>
      </div>

      <div className="t-header-right">
        <button className="t-btn t-btn-xs t-btn-ghost" onClick={toggleTheme}
          title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
          style={{ fontSize: 13, padding: '2px 6px' }}>
          {theme === 'dark' ? 'Light' : 'Dark'}
        </button>

        {nifty && (
          <span style={{ fontSize: 10, fontFamily: 'var(--font-mono)', display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={{ color: 'var(--text-faint)' }}>NIFTY</span>
            <span style={{ color: 'var(--text)', fontWeight: 600 }}>{nifty.last_price.toFixed(1)}</span>
            <span style={{ color: (nifty.change_pct ?? 0) >= 0 ? 'var(--text-green)' : 'var(--text-red)' }}>
              {(nifty.change_pct ?? 0) >= 0 ? '+' : ''}{(nifty.change_pct ?? 0).toFixed(2)}%
            </span>
          </span>
        )}

        <span className={`t-badge ${connected ? 't-badge-green' : 't-badge-red'}`}>
          <span className={`t-dot ${connected ? 't-dot-green t-dot-pulse' : 't-dot-red'}`} style={{ marginRight: 4 }} />
          {connected ? 'LIVE' : 'OFF'}
        </span>

        <div className="t-header-user">
          <div className="t-header-avatar">
            {user?.full_name?.[0] || user?.email?.[0] || 'U'}
          </div>
          <span style={{ fontSize: 10, color: 'var(--text-sub)', maxWidth: 80, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {user?.full_name || user?.email?.split('@')[0] || 'User'}
          </span>
        </div>
      </div>
    </header>
  )
}
