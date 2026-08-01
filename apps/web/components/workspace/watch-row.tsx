'use client'

import { memo } from 'react'
import type { TickData } from '@/lib/use-market-data'
import MiniChart from './mini-chart'

export interface WatchItem { symbol: string; name: string; type: string }

interface WatchRowProps {
  item: WatchItem
  tick?: TickData
  active: boolean
  pinned: boolean
  spark?: number[]
  onSelect: (symbol: string, name: string) => void
  onBuy: (symbol: string, name: string) => void
  onSell: (symbol: string, name: string) => void
  onAnalyze: (symbol: string, name: string) => void
  onToggleFav: (symbol: string) => void
  onAlert: (item: WatchItem) => void
}

function short(s: string) { return s.split(':').pop() || s }

const WatchRow = memo(function WatchRow({
  item, tick, active, pinned, spark, onSelect, onBuy, onSell, onAnalyze, onToggleFav, onAlert,
}: WatchRowProps) {
  const pct = tick?.change_pct
  const trend = pct === undefined ? '' : pct > 0 ? '↑' : pct < 0 ? '↓' : '→'
  return (
    <tr
      onClick={() => onSelect(item.symbol, item.name)}
      onDoubleClick={() => onBuy(item.symbol, item.name)}
      style={{ cursor: 'pointer', background: active ? 'color-mix(in srgb, var(--cyan) 6%, transparent)' : undefined }}
    >
      <td style={{ whiteSpace: 'nowrap' }}>
        <span style={{ fontSize: 11, fontWeight: 700 }}>{short(item.symbol)}</span>
        <span className="t-faint" style={{ fontSize: 9, marginLeft: 4 }}>{item.type.slice(0, 3)}</span>
      </td>
      <td><span className="t-num" style={{ fontSize: 11 }}>{tick?.last_price?.toFixed(1) ?? '—'}</span></td>
      <td>
        <span className={`t-num ${pct !== undefined && pct >= 0 ? 't-up' : 't-down'}`} style={{ fontSize: 10 }}>
          {pct !== undefined ? `${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%` : '—'}
        </span>
      </td>
      <td><span className="t-num t-faint" style={{ fontSize: 10 }}>{tick?.oi ? (tick.oi / 100000).toFixed(1) + 'L' : '—'}</span></td>
      <td><span className="t-num t-faint" style={{ fontSize: 10 }}>{tick?.volume ? (tick.volume / 1000).toFixed(0) + 'K' : '—'}</span></td>
      <td><span className={pct !== undefined && pct >= 0 ? 't-up' : 't-down'} style={{ fontSize: 11, fontWeight: 700 }}>{trend}</span></td>
      <td><MiniChart values={spark || []} /></td>
      <td style={{ whiteSpace: 'nowrap' }}>
        <button className="t-btn t-btn-xs" style={{ color: 'var(--green)', padding: '1px 6px' }} onClick={e => { e.stopPropagation(); onBuy(item.symbol, item.name) }}>B</button>
        <button className="t-btn t-btn-xs" style={{ color: 'var(--red)', padding: '1px 6px' }} onClick={e => { e.stopPropagation(); onSell(item.symbol, item.name) }}>S</button>
        <button className="t-btn t-btn-xs t-btn-ghost" title="Analyzer" style={{ padding: '1px 5px' }} onClick={e => { e.stopPropagation(); onAnalyze(item.symbol, item.name) }}>🔬</button>
        <button className="t-btn t-btn-xs t-btn-ghost" title="Price alert" style={{ padding: '1px 5px' }} onClick={e => { e.stopPropagation(); onAlert(item) }}>🔔</button>
        <button className="t-btn t-btn-xs t-btn-ghost" title={pinned ? 'Unpin' : 'Pin'} style={{ padding: '1px 5px', color: pinned ? 'var(--amber)' : undefined }} onClick={e => { e.stopPropagation(); onToggleFav(item.symbol) }}>★</button>
      </td>
    </tr>
  )
})

export default WatchRow
