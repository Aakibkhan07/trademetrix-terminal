'use client'

import { useCallback, useState } from 'react'
import { api } from '@/lib/api'
import { usePolling } from '@/lib/use-polling'
import { KpiCard } from '@/components/ui/kpi-card'
import { Dot } from '@/components/ui/badge'
import { fmtNum } from './types'

const INDICES = ['NSE:NIFTY50-INDEX', 'NSE:NIFTYBANK-INDEX']

interface IndexQuote {
  symbol: string
  last_price: number
  close: number
  broker?: string
}

/**
 * Market Overview header — the live session chip (OPEN / CLOSED with the
 * next open) plus index cards (NIFTY 50 / BANK NIFTY). Quotes come from the
 * existing `/marketdata/quote` path; change% is `(last − close) / close`,
 * guarded by `last_price > 0`. Shows cached values when the market is closed.
 */
export function MarketOverview({ market, marketLoading, isOffline }: {
  market: { is_open: boolean; market: string; close_time: string; next_open: string } | null
  marketLoading: boolean
  isOffline: boolean
}) {
  const [quotes, setQuotes] = useState<Record<string, IndexQuote>>({})
  const [quoteError, setQuoteError] = useState(false)

  const refreshQuotes = useCallback(async () => {
    try {
      const res = await api.marketdata.quote(INDICES)
      const list = Array.isArray(res) ? res : (res ? [res] : [])
      const next: Record<string, IndexQuote> = {}
      for (const q of list) {
        if (q.last_price > 0) next[q.symbol] = q
      }
      setQuotes(next)
      setQuoteError(false)
    } catch {
      setQuoteError(true)
    }
  }, [])

  usePolling(refreshQuotes, 5000, true)

  const open = !!market?.is_open
  const sessionLabel = marketLoading ? 'Checking…' : open ? 'OPEN' : 'CLOSED'

  return (
    <div className="t-panel" style={{ marginBottom: 10 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 12px', borderBottom: '1px solid var(--border)', flexWrap: 'wrap' }}>
        <h3 style={{ margin: 0, fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--text-sub)' }}>
          Market Overview
        </h3>
        <span className="t-badge" style={{ fontSize: 10, display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <Dot variant={open ? 'green' : 'amber'} pulse={open} />
          {sessionLabel}
        </span>
        {market && !marketLoading && (
          <span className="t-faint" style={{ fontSize: 10 }}>
            {open
              ? `Closes ${market.close_time.slice(11, 16)} IST`
              : `Next open ${new Date(market.next_open).toLocaleString('en-IN', { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })} IST`}
          </span>
        )}
        <span className="t-faint" style={{ fontSize: 10, marginLeft: 'auto' }}>
          {isOffline ? 'offline' : quoteError ? 'quotes unavailable' : 'live'}
        </span>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 8, padding: 10 }}>
        {INDICES.map(sym => {
          const q = quotes[sym]
          const chg = q && q.last_price > 0 && q.close > 0 ? ((q.last_price - q.close) / q.close) * 100 : 0
          const up = chg >= 0
          return (
            <KpiCard
              key={sym}
              variant="stat"
              label={sym === 'NSE:NIFTY50-INDEX' ? 'NIFTY 50' : 'BANK NIFTY'}
              value={q ? fmtNum(q.last_price, 2) : '—'}
              color={q ? (up ? 'var(--green)' : 'var(--red)') : 'var(--text-sub)'}
              sub={q ? `${up ? '+' : ''}${chg.toFixed(2)}%` : (isOffline ? 'offline' : '—')}
            />
          )
        })}
      </div>
    </div>
  )
}