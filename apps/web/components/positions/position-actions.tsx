'use client'

import { useState } from 'react'
import type { PositionRow, OrderRow } from '@/components/trade/types'

export type ActionKind = 'exit' | 'partial' | 'add' | 'reverse' | 'trail' | 'modify'

export interface TrailState {
  symbol: string
  orderId: string
  side: 'BUY' | 'SELL'
  trigger: number
  distance: number
  lastBest: number
}

/**
 * Inline position action tray — every action uses existing engine APIs:
 *  - exit / partial / add / reverse → engine.trade (MARKET, opposite or same side)
 *  - trail SL → place SL-M trigger order, then re-issue via engine modifyOrder
 *    as the tick improves (client-side trail; deterministic stop in paper)
 *  - modify → engine modifyOrder on the position's resting OPEN order (if any)
 */
export function PositionActions({ position, ltp, openOrder, trail, onAct, onToggleTrail, busy }: {
  position: PositionRow
  ltp: number | null
  openOrder: OrderRow | null
  trail: TrailState | null
  onAct: (kind: ActionKind, qty: number, extra?: { price?: number; triggerPrice?: number; distance?: number }) => void
  onToggleTrail: (action: 'start' | 'stop', distance?: number) => void
  busy: boolean
}) {
  const [qty, setQty] = useState('')
  const [price, setPrice] = useState('')
  const [trigger, setTrigger] = useState('')
  const [distance, setDistance] = useState('')

  const absQty = Math.abs(position.quantity || 0)
  const long = (position.quantity || 0) > 0
  const closeSide: 'BUY' | 'SELL' = long ? 'SELL' : 'BUY'
  const addSide: 'BUY' | 'SELL' = long ? 'BUY' : 'SELL'
  const trailSide: 'BUY' | 'SELL' = long ? 'SELL' : 'BUY'
  const hint = `(${absQty} × ${ltp ? ltp.toFixed(1) : '—'})`

  const input = {
    background: 'var(--bg)', border: '1px solid color-mix(in srgb, var(--text-inverse) 15%, transparent)',
    borderRadius: 6, color: 'var(--text)', padding: '3px 6px', width: 84, fontSize: 11, fontFamily: 'var(--font-mono)',
  } as const

  return (
    <div style={{ display: 'grid', gap: 8, padding: '8px 12px', background: 'color-mix(in srgb, var(--text-inverse) 2%, transparent)' }}>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        <button className="t-btn t-btn-sm t-btn-ghost" disabled={busy} onClick={() => onAct('exit', absQty)}>
          Exit {hint}
        </button>
        <button className="t-btn t-btn-sm t-btn-ghost" disabled={busy} onClick={() => onAct('partial', Number(qty) || 0)}>
          Partial Exit {qty && <span style={{ marginLeft: 4 }}>{closeSide} {qty}</span>}
        </button>
        <button className="t-btn t-btn-sm t-btn-ghost" disabled={busy} onClick={() => onAct('add', Number(qty) || 0)}>
          Add {qty && <span style={{ marginLeft: 4 }}>{addSide} {qty}</span>}
        </button>
        <button className="t-btn t-btn-sm t-btn-ghost" disabled={busy} onClick={() => onAct('reverse', absQty * 2)}>
          Reverse ({closeSide} {absQty * 2})
        </button>
        <button
          className={`t-btn t-btn-sm ${trail ? 't-btn-danger' : 't-btn-ghost'}`}
          disabled={busy}
          onClick={() => onToggleTrail(trail ? 'stop' : 'start', Number(distance) || 0)}
        >
          {trail ? 'Stop Trail' : 'Trail SL'}
          {trail && <span style={{ marginLeft: 4 }}>@{trail.trigger.toFixed(1)}</span>}
        </button>
        <button className="t-btn t-btn-sm t-btn-ghost" disabled={busy} onClick={() => onAct('modify', 0, { price: Number(price) || undefined, triggerPrice: Number(trigger) || undefined })}>
          Modify
        </button>
      </div>

      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
        <label style={{ fontSize: 10, color: 'var(--text-faint)', display: 'flex', alignItems: 'center', gap: 4 }}>
          Qty <input style={input} inputMode="numeric" placeholder={`≤ ${absQty}`} value={qty} onChange={e => setQty(e.target.value)} />
        </label>
        <label style={{ fontSize: 10, color: 'var(--text-faint)', display: 'flex', alignItems: 'center', gap: 4 }}>
          Trail dist <input style={input} inputMode="numeric" placeholder={ltp ? `from ${ltp.toFixed(1)}` : '₹'} value={distance} onChange={e => setDistance(e.target.value)} />
        </label>
        <label style={{ fontSize: 10, color: 'var(--text-faint)', display: 'flex', alignItems: 'center', gap: 4 }}>
          Price <input style={input} inputMode="decimal" value={price} onChange={e => setPrice(e.target.value)} />
        </label>
        <label style={{ fontSize: 10, color: 'var(--text-faint)', display: 'flex', alignItems: 'center', gap: 4 }}>
          Trigger <input style={input} inputMode="decimal" value={trigger} onChange={e => setTrigger(e.target.value)} />
        </label>
        {!openOrder && (
          <span style={{ fontSize: 9, color: 'var(--text-faint)' }}>
            Modify needs a resting OPEN order for {position.symbol}. Trail SL places one for you.
          </span>
        )}
      </div>
    </div>
  )
}