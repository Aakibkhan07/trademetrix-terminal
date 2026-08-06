'use client'

import { useCallback, useState } from 'react'
import { api } from '@/lib/api'
import { useLiveData } from './use-live-data'
import { WidgetFrame } from './widget-frame'
import { Table, SectionDivider, SectionLabel } from './table'
import { fmtInr, fmtNum, type LivePosition } from './types'

/**
 * Live Positions widget — Live broker / Paper tabs. Both read the canonical
 * position surfaces (`/engine/positions`, `/paper/positions`); LTP + change%
 * enrich the open rows from `/marketdata/quote` (zero-price guarded, so a
 * broken quote source can never zero out broker P&L).
 */
export function PositionsPanel({ offline, marketClosed }: { offline: boolean; marketClosed: boolean }) {
  const [tab, setTab] = useState<'live' | 'paper'>('live')

  const engine = useLiveData<{ positions: LivePosition[] }>(useCallback(async () => (await api.engine.positions()) as { positions: LivePosition[] }, []), { enabled: !offline })
  const paper = useLiveData<{ positions: LivePosition[] }>(useCallback(async () => (await api.paper.positions()) as { positions: LivePosition[] }, []), { enabled: !offline })
  const isPaper = tab === 'paper'

  const positions = isPaper ? (paper.data?.positions || []) : (engine.data?.positions || [])
  const loading = isPaper ? paper.loading : engine.loading
  const error = (isPaper ? paper.error : engine.error) || null

  const openSymbols = positions.filter(p => p.quantity !== 0).map(p => p.symbol).filter(Boolean)
  const { data: quoteMap } = useLiveData<Record<string, { last_price: number; close: number }>>(
    useCallback(async () => {
      if (openSymbols.length === 0) return {}
      const res = await api.marketdata.quote(openSymbols)
      const list = Array.isArray(res) ? res : (res ? [res] : [])
      const next: Record<string, { last_price: number; close: number }> = {}
      for (const q of list) {
        if (q.last_price > 0) next[q.symbol] = q
      }
      return next
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [openSymbols.join('|')]),
    { intervalMs: 5000, enabled: !offline && openSymbols.length > 0 },
  )
  const quotes = quoteMap || {}

  const openPositions = positions.filter(p => p.quantity !== 0)
  const closedPositions = positions.filter(p => p.quantity === 0)
  const totalUnrealised = openPositions.reduce((s, p) => s + (p.unrealised_pnl || 0), 0)
  const totalRealised = positions.reduce((s, p) => s + (p.realised_pnl || 0), 0)

  const subtitle = `${openPositions.length} open · ${totalUnrealised >= 0 ? '+' : ''}${fmtInr(totalUnrealised)} unreal`

  return (
    <WidgetFrame
      title={`Positions · ${isPaper ? 'Paper' : 'Live'}`}
      subtitle={subtitle}
      offline={offline}
      marketClosed={marketClosed}
      loading={loading}
      error={error}
      empty={positions.length === 0}
      emptyMessage={isPaper ? 'No paper positions yet' : 'No positions yet'}
      actions={
        <div className="t-seg" style={{ gap: 0 }}>
          <button type="button" className={`t-seg-btn ${tab === 'live' ? 'active' : ''}`} onClick={() => setTab('live')} style={{ fontSize: 11 }}>Live</button>
          <button type="button" className={`t-seg-btn ${tab === 'paper' ? 'active' : ''}`} onClick={() => setTab('paper')} style={{ fontSize: 11 }}>Paper</button>
        </div>
      }
    >
      {openPositions.length > 0 && (
        <SectionLabel label="Open Positions" value={`${totalUnrealised >= 0 ? '+' : ''}${fmtInr(totalUnrealised)}`} up={totalUnrealised >= 0} />
      )}
      <Table head={['Symbol', 'Qty', 'Buy', 'LTP', 'Chg%', 'Unrealised P&L']}>
        {openPositions.map(p => {
          const q = quotes[p.symbol]
          const ltp = q?.last_price || 0
          const chg = q && q.last_price > 0 && q.close > 0 ? ((q.last_price - q.close) / q.close) * 100 : undefined
          const pnl = ltp > 0 && p.average_buy_price ? (p.quantity * (ltp - p.average_buy_price)) : (p.unrealised_pnl || 0)
          return (
            <tr key={p.symbol}>
              <td style={{ fontWeight: 600, fontSize: 12 }}>{p.symbol?.split(':').pop()}</td>
              <td className="t-num">{p.quantity}</td>
              <td className="t-num">{(p.average_buy_price || 0).toFixed(1)}</td>
              <td className="t-num">{fmtNum(ltp || undefined)}</td>
              <td className={`t-num ${chg !== undefined ? (chg >= 0 ? 't-up' : 't-down') : ''}`}>{chg !== undefined ? `${chg >= 0 ? '+' : ''}${chg.toFixed(2)}%` : '—'}</td>
              <td className={`t-num ${pnl >= 0 ? 't-up' : 't-down'}`} style={{ fontWeight: 700 }}>{pnl >= 0 ? '+' : ''}{fmtInr(pnl)}</td>
            </tr>
          )
        })}
      </Table>

      {closedPositions.length > 0 && (
        <>
          <SectionDivider />
          <SectionLabel label="Closed Today" value={`${totalRealised >= 0 ? '+' : ''}${fmtInr(totalRealised)}`} up={totalRealised >= 0} />
          <Table head={['Symbol', 'Qty', 'Avg Buy', 'Avg Sell', 'Realised P&L']}>
            {closedPositions.map(p => (
              <tr key={p.symbol}>
                <td style={{ fontWeight: 600, fontSize: 12 }}>{p.symbol?.split(':').pop()}</td>
                <td className="t-num">{p.buy_quantity || p.sell_quantity || 0}</td>
                <td className="t-num">{(p.average_buy_price || 0).toFixed(1)}</td>
                <td className="t-num">{(p.average_sell_price || 0).toFixed(1)}</td>
                <td className={`t-num ${(p.realised_pnl || 0) >= 0 ? 't-up' : 't-down'}`} style={{ fontWeight: 700 }}>
                  {(p.realised_pnl || 0) >= 0 ? '+' : ''}{fmtInr(p.realised_pnl || 0)}
                </td>
              </tr>
            ))}
          </Table>
        </>
      )}
    </WidgetFrame>
  )
}