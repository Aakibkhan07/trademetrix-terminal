'use client'

import { INDEXES, indexMeta } from '@/lib/options-contracts'
import type { IndexKey } from '@/lib/options-contracts'

/** Index selector + live spot strip (WS ticks, quote fallback). */
export function IndexStrip({ index, onIndexChange, spot, changePct, connected }: {
  index: IndexKey
  onIndexChange: (i: IndexKey) => void
  spot: number | null
  changePct: number | null
  connected: boolean
}) {
  const meta = indexMeta(index)
  return (
    <div className="t-panel" style={{ padding: '8px 12px', display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
      <span className="t-faint" style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.08em', marginRight: 2 }}>INDEX</span>
      {INDEXES.map(i => (
        <button
          key={i.key}
          data-kb={`index-${i.key}`}
          className={`t-chip ${index === i.key ? 'active' : ''}`}
          style={{ fontSize: 11, fontWeight: index === i.key ? 700 : 500 }}
          onClick={() => onIndexChange(i.key)}
        >
          {i.name}
        </button>
      ))}
      <span style={{ flex: 1 }} />
      <span className={`t-dot ${connected ? 't-dot-green t-dot-pulse' : 't-dot-sub'}`} />
      <span className="t-faint" style={{ fontSize: 10 }}>{connected ? 'LIVE' : 'SYNCING'}</span>
      <div style={{ textAlign: 'right', lineHeight: 1.15 }}>
        <div className="t-faint" style={{ fontSize: 9 }}>{meta.spotSymbol}</div>
        <div style={{ fontSize: 18, fontWeight: 800, fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums' }}>
          {spot !== null && isFinite(spot) ? spot.toLocaleString('en-IN', { maximumFractionDigits: 2 }) : '—'}
        </div>
        <div style={{ fontSize: 10, fontWeight: 600, color: changePct !== null && changePct > 0 ? 'var(--green)' : changePct !== null && changePct < 0 ? 'var(--red)' : 'var(--text-faint)' }}>
          {changePct !== null ? `${changePct > 0 ? '+' : ''}${changePct.toFixed(2)}%` : '—'}
        </div>
      </div>
    </div>
  )
}