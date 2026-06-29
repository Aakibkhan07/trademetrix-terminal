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
    <header className="header">
      <Link href="/dashboard" className="header-brand" style={{ textDecoration: 'none' }}>
        Trade Metrix
      </Link>

      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        {nifty && (
          <span style={{ fontSize: 11, color: '#8888a0' }}>
            NIFTY <span style={{ color: '#f0f0f5', fontWeight: 600 }}>{nifty.last_price.toFixed(1)}</span>
            <span style={{ marginLeft: 3, color: (nifty.change_pct ?? 0) >= 0 ? '#22c55e' : '#ef4444' }}>
              {(nifty.change_pct ?? 0) >= 0 ? '+' : ''}{(nifty.change_pct ?? 0).toFixed(2)}%
            </span>
          </span>
        )}
        <span className={`badge ${connected ? 'badge-green' : 'badge-red'}`} style={{ fontSize: 10 }}>
          <span className={`status-dot ${connected ? 'active' : ''}`} style={{ marginRight: 3 }} />
          {connected ? 'Live' : 'Offline'}
        </span>
      </div>
    </header>
  )
}
