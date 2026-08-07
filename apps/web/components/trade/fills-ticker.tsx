'use client'

import { useEffect, useRef, useState } from 'react'

export interface Fill {
  trade_id?: string
  symbol: string
  side: string
  quantity: number
  price: number
  is_paper?: boolean
  traded_at?: string
}

/** Last fills ticker — polls the existing paper trades endpoint (no new API). */
export function FillsTicker({ load, intervalMs = 5000 }: {
  load: (limit: number) => Promise<Fill[]>
  intervalMs?: number
}) {
  const [fills, setFills] = useState<Fill[]>([])
  const [error, setError] = useState(false)
  const timer = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    let alive = true
    const tick = async () => {
      try {
        const next = await load(6)
        if (alive && next.length) setFills(next)
        if (alive) setError(false)
      } catch {
        if (alive) setError(true)
      }
    }
    tick()
    timer.current = setInterval(tick, intervalMs)
    return () => { alive = false; if (timer.current) clearInterval(timer.current) }
  }, [load, intervalMs])

  if (error && !fills.length) {
    return (
      <div className="t-panel" style={{ padding: '8px 12px' }}>
        <span className="t-faint" style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.08em' }}>FILLS</span>
        <span className="t-faint" style={{ fontSize: 10, marginLeft: 8 }}>Unavailable — feed offline</span>
      </div>
    )
  }

  return (
    <div className="t-panel" style={{ padding: '8px 12px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span className="t-faint" style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.08em' }}>FILLS</span>
        {error && <span className="t-faint" style={{ fontSize: 9 }}>stale</span>}
        <span style={{ flex: 1 }} />
        <span className="t-faint" style={{ fontSize: 9 }}>last {fills.length}</span>
      </div>
      {fills.length === 0 ? (
        <div className="t-faint" style={{ fontSize: 10, padding: '6px 0' }}>No fills yet</div>
      ) : (
        <div style={{ display: 'flex', gap: 8, overflowX: 'auto', padding: '6px 0' }}>
          {fills.map(f => (
            <div key={f.trade_id ?? `${f.symbol}${f.traded_at}`} style={{
              flex: '0 0 auto',
              display: 'grid',
              gap: 2,
              padding: '6px 10px',
              borderRadius: 8,
              background: 'color-mix(in srgb, var(--text-inverse) 3%, transparent)',
              minWidth: 140,
            }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: (f.side || '').toUpperCase() === 'BUY' ? 'var(--green)' : 'var(--red)' }}>
                {(f.side || '').toUpperCase()} {f.quantity}
              </div>
              <div style={{ fontSize: 9, fontFamily: 'var(--font-mono)' }}>{f.symbol}</div>
              <div style={{ fontSize: 9, color: 'var(--text-faint)' }}>
                @ {f.price > 0 ? f.price.toLocaleString('en-IN', { maximumFractionDigits: 2 }) : '—'}
                {f.is_paper ? ' · paper' : ''}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}