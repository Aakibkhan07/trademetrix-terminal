'use client'

import { memo, useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { useMarketData, type TickData } from '@/lib/use-market-data'
import { useToast } from '@/lib/use-toast'
import { useUIStore } from '@/lib/stores/ui-store'

export interface Position {
  symbol: string
  quantity: number
  average_buy_price: number
  unrealised_pnl: number
  product: string
  instrument_type: string
}

interface PositionCardProps {
  position: Position
  tick?: TickData
  holdingStart?: number
  onModify: (symbol: string, name: string, side: 'BUY' | 'SELL', qty: number) => void
}

function fmt(n: number, d = 2) {
  return Number.isFinite(n) ? n.toLocaleString('en-IN', { minimumFractionDigits: d, maximumFractionDigits: d }) : '—'
}

function holdTime(start: number | undefined): string {
  if (!start) return '—'
  const ms = Date.now() - start
  if (ms < 0) return '—'
  const m = Math.floor(ms / 60000)
  if (m < 60) return `${m}m`
  const h = Math.floor(m / 60)
  return `${h}h ${m % 60}m`
}

const PositionCard = memo(function PositionCard({ position, tick, holdingStart, onModify }: PositionCardProps) {
  const { toast } = useToast()
  const openQuickOrder = useUIStore(s => s.openQuickOrder)
  const paper = useUIStore(s => s.drawerPrefs.paper)
  const qc = useQueryClient()
  const [busy, setBusy] = useState(false)

  const qty = Math.abs(position.quantity)
  const long = position.quantity >= 0
  const side: 'BUY' | 'SELL' = long ? 'BUY' : 'SELL'
  const entry = position.average_buy_price
  const current = tick?.last_price ?? (entry !== 0 ? Math.abs(position.unrealised_pnl) / qty + entry : 0)

  const pnl = useMemo(() => {
    if (tick?.last_price && entry > 0) return (tick.last_price - entry) * position.quantity
    return position.unrealised_pnl || 0
  }, [tick?.last_price, entry, position.quantity, position.unrealised_pnl])

  const pnlPct = entry > 0 ? (pnl / (entry * qty)) * 100 : 0
  const sl = long ? entry * 0.9 : entry * 1.1
  const target = long ? entry * 1.15 : entry * 0.85
  const riskAmt = Math.abs(entry - sl) * qty
  const rewardAmt = Math.abs(target - entry) * qty
  const rr = riskAmt > 0 ? rewardAmt / riskAmt : 0
  const slDist = entry > 0 ? (Math.abs(current - sl) / current) * 100 : 0
  const tgtDist = entry > 0 ? (Math.abs(target - current) / current) * 100 : 0

  const closePos = async (q: number, kind: string, source = 'exit_sl') => {
    if (busy) return
    setBusy(true)
    try {
      const res = await api.engine.trade({
        symbol: position.symbol,
        side: long ? 'SELL' : 'BUY',
        quantity: q,
        price: 0,
        exchange: position.symbol.split(':')[0] || 'NSE',
        order_type: 'MARKET',
        product: 'INTRADAY',
        instrument_type: position.instrument_type === 'OPT' ? 'OPT' : 'EQ',
        is_paper: paper,
        source,
      }) as { result?: { success?: boolean; message?: string; status?: string } }
      const r = res?.result
      if (r?.success) {
        toast('success', `${kind} ${q} × ${position.symbol}${paper ? ' (paper)' : ''}`)
        qc.invalidateQueries({ queryKey: ['orders'] })
        qc.invalidateQueries({ queryKey: ['positions'] })
        qc.invalidateQueries({ queryKey: ['funds'] })
      } else {
        toast('error', r?.message || `${kind} failed`)
      }
    } catch (e) {
      toast('error', String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
        <span className={`t-num ${long ? 't-up' : 't-down'}`} style={{ fontSize: 15, fontWeight: 800 }}>
          {long ? 'LONG' : 'SHORT'} {qty}
        </span>
        <span className="t-num" style={{ fontSize: 18, fontWeight: 800 }}>₹{fmt(pnl)}</span>
        <span className={`t-num ${pnl >= 0 ? 't-up' : 't-down'}`} style={{ fontSize: 12 }}>({pnlPct >= 0 ? '+' : ''}{fmt(pnlPct)}%)</span>
        <span className="t-faint" style={{ fontSize: 10, marginLeft: 'auto' }}>⏱ {holdTime(holdingStart)}</span>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(82px, 1fr))', gap: 6 }}>
        {[
          ['ENTRY', fmt(entry)], ['CURRENT', fmt(current)],
          ['SL', `${fmt(sl)} (−${fmt(slDist)}%)`], ['TARGET', `${fmt(target)} (+${fmt(tgtDist)}%)`],
          ['RISK', `₹${fmt(riskAmt)}`], ['REWARD', `₹${fmt(rewardAmt)}`],
          ['RR', `${fmt(rr, 2)}:1`], ['PRODUCT', position.product],
        ].map(([k, v]) => (
          <div key={k} style={{ background: 'var(--bg-secondary)', borderRadius: 8, padding: '7px 9px', minWidth: 0 }}>
            <div className="t-stat-label" style={{ fontSize: 8 }}>{k}</div>
            <div className="t-num" style={{ fontSize: 11, fontWeight: 700, marginTop: 2 }}>{v}</div>
          </div>
        ))}
      </div>

      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        <button className="t-btn t-btn-sm" disabled={busy} onClick={() => onModify(position.symbol, position.symbol, side, qty)}>Modify</button>
        <button className="t-btn t-btn-sm t-btn-danger" disabled={busy} onClick={() => closePos(qty, 'Exited')}>Exit</button>
        <button className="t-btn t-btn-sm" disabled={busy} onClick={() => closePos(qty * 2, 'Reversed')}>Reverse</button>
        <button className="t-btn t-btn-sm t-btn-success" disabled={busy} onClick={() => openQuickOrder(position.symbol, position.symbol, side)}>Scale In</button>
        <button className="t-btn t-btn-sm t-btn-ghost" disabled={busy} onClick={() => closePos(Math.ceil(qty / 2), 'Scaled out')}>Scale Out</button>
      </div>
      <div className="t-faint" style={{ fontSize: 9 }}>
        Exits reuse OMS exit path (no cascading brackets). SL/Target = auto-bracket defaults (−10%/+15% from entry).
      </div>
    </div>
  )
})

export default PositionCard
