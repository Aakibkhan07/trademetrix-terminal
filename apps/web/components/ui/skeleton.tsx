'use client'

import type { CSSProperties } from 'react'

/** Single skeleton bar — emits the local `SkeletonLine` markup verbatim (no animation by default). */
export function SkeletonBar({ w, h = 12, background, pulse, style }: {
  w: string
  h?: number
  background?: string
  pulse?: boolean
  style?: CSSProperties
}) {
  return (
    <div style={{
      width: w, height: h,
      background: background || 'var(--border)',
      borderRadius: 4,
      ...(pulse ? { animation: 'pulse 1.5s infinite' as const } : {}),
      ...style,
    }} />
  )
}

/** Card skeleton with pulsing bars (`components/skeleton.tsx` markup, verbatim). */
export function SkeletonCard() {
  return (
    <div className="t-panel" style={{ padding: 16 }}>
      <div style={{ width: '30%', height: 10, borderRadius: 4, background: 'var(--border)', animation: 'pulse 1.5s infinite', marginBottom: 8 }} />
      <div style={{ width: '60%', height: 14, borderRadius: 4, background: 'var(--border)', animation: 'pulse 1.5s infinite' }} />
    </div>
  )
}

/** Grid of card skeletons. */
export function SkeletonGrid({ count }: { count: number }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: `repeat(${Math.min(count, 4)}, 1fr)`, gap: 10 }}>
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="t-panel" style={{ height: 80, padding: 16 }}>
          <div style={{ width: '40%', height: 10, borderRadius: 4, background: 'var(--border)', animation: 'pulse 1.5s infinite' }} />
          <div style={{ width: '60%', height: 18, borderRadius: 4, background: 'var(--border)', marginTop: 10, animation: 'pulse 1.5s infinite' }} />
        </div>
      ))}
    </div>
  )
}

/** Table-shaped skeleton. */
export function SkeletonTable({ rows }: { rows: number }) {
  return (
    <div className="t-panel" style={{ padding: 16 }}>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} style={{ display: 'flex', gap: 16, padding: '8px 0', borderBottom: i < rows - 1 ? '1px solid var(--border)' : 'none' }}>
          <div style={{ flex: 2, height: 12, borderRadius: 4, background: 'var(--border)', animation: 'pulse 1.5s infinite' }} />
          <div style={{ flex: 1, height: 12, borderRadius: 4, background: 'var(--border)', animation: 'pulse 1.5s infinite' }} />
          <div style={{ flex: 1, height: 12, borderRadius: 4, background: 'var(--border)', animation: 'pulse 1.5s infinite' }} />
        </div>
      ))}
    </div>
  )
}

/** Panel skeleton with violet-tinted lines (admin `LoadState` markup, verbatim). */
export function SkeletonPanel() {
  return (
    <div className="t-panel" style={{ padding: 20 }}>
      <div style={{ height: 12, width: '40%', background: 'rgba(139,92,246,0.08)', borderRadius: 4, marginBottom: 8 }} />
      <div style={{ height: 12, width: '65%', background: 'rgba(139,92,246,0.08)', borderRadius: 4 }} />
    </div>
  )
}
