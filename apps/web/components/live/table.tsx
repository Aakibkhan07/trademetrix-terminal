'use client'

import type { ReactNode } from 'react'

/** Compact table primitives shared by the Live Dashboard panels. */
export function Table({ head, children, style }: { head: ReactNode[]; children: ReactNode; style?: React.CSSProperties }) {
  return (
    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11, ...style }}>
      <thead>
        <tr>
          {head.map((h, i) => (
            <th key={i} style={{ textAlign: 'left', padding: '6px 6px', borderBottom: '1px solid var(--border)', color: 'var(--text-faint)', fontWeight: 600, textTransform: 'uppercase', fontSize: 9, letterSpacing: '0.04em', whiteSpace: 'nowrap' }}>
              {h}
            </th>
          ))}
        </tr>
      </thead>
      <tbody style={{ fontWeight: 500 }}>{children}</tbody>
    </table>
  )
}

export function SectionLabel({ label, value, up }: { label: string; value: string; up?: boolean }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', margin: '10px 0 4px' }}>
      <span style={{ fontSize: 10, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-sub)' }}>{label}</span>
      <span className={`t-num ${up ? 't-up' : 't-down'}`} style={{ fontSize: 11, fontWeight: 700 }}>{value}</span>
    </div>
  )
}

export function SectionDivider() {
  return <div style={{ height: 1, background: 'var(--border)', margin: '10px 0' }} />
}