'use client'

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

export function SkeletonCard() {
  return (
    <div className="t-panel" style={{ padding: 16 }}>
      <div style={{ width: '30%', height: 10, borderRadius: 4, background: 'var(--border)', animation: 'pulse 1.5s infinite', marginBottom: 8 }} />
      <div style={{ width: '60%', height: 14, borderRadius: 4, background: 'var(--border)', animation: 'pulse 1.5s infinite' }} />
    </div>
  )
}

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
