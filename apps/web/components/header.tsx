'use client'

import { usePathname } from 'next/navigation'
import Link from 'next/link'
import { useMarketData } from '@/lib/use-market-data'

export default function Header() {
  const pathname = usePathname()
  const { connected, ticks } = useMarketData()

  if (pathname === '/auth') return null

  const nifty = ticks['NSE:NIFTY50-INDEX']

  return (
    <header className="t-header">
      <div className="t-header-left">
        <Link href="/dashboard" className="t-header-brand" style={{ textDecoration: 'none' }}>
          TM
        </Link>
        <span style={{ width: 1, height: 18, background: 'var(--border)' }} />
        <span style={{ fontSize: 10, color: 'var(--text-faint)', fontFamily: 'var(--font-mono)' }}>
          v0.1
        </span>
      </div>

      <div className="t-header-center">
        {nifty && (
          <span style={{ fontSize: 11, fontFamily: 'var(--font-mono)', display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ color: 'var(--text-faint)', fontWeight: 500 }}>NIFTY</span>
            <span style={{ color: 'var(--text)', fontWeight: 600 }}>{nifty.last_price.toFixed(1)}</span>
            <span style={{ color: (nifty.change_pct ?? 0) >= 0 ? 'var(--text-green)' : 'var(--text-red)' }}>
              {(nifty.change_pct ?? 0) >= 0 ? '+' : ''}{(nifty.change_pct ?? 0).toFixed(2)}%
            </span>
          </span>
        )}
      </div>

      <div className="t-header-right">
        <span className={`t-badge ${connected ? 't-badge-green' : 't-badge-red'}`}>
          <span className={`t-dot ${connected ? 't-dot-green t-dot-pulse' : 't-dot-red'}`} style={{ marginRight: 4 }} />
          {connected ? 'LIVE' : 'OFF'}
        </span>
      </div>
    </header>
  )
}
