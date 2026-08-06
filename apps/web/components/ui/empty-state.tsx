'use client'

import type { CSSProperties, ReactNode } from 'react'

/**
 * Empty state. `panel` mirrors the original shared EmptyState markup exactly
 * (`icon` remains accepted-but-unrendered for byte parity — pre-existing behavior).
 * `text` = the repeated `t-faint` inline empty paragraph pattern.
 * `row` = `<tr><td colSpan>…` empty-table-cell pattern.
 */
export function EmptyState({ title, description, icon, variant = 'panel', style }: {
  title?: string
  description?: string
  icon?: string
  variant?: 'panel' | 'text'
  style?: CSSProperties
}) {
  if (variant === 'text') {
    return (
      <p style={{ margin: 0, fontSize: 12, color: 'var(--text-faint)', ...style }}>
        {icon ? `${icon} ` : ''}{title || 'No data'}
        {description ? ` — ${description}` : ''}
      </p>
    )
  }
  return (
    <div style={{ textAlign: 'center', padding: 40, ...style }}>
      <p style={{ color: 'var(--text-faint)', fontSize: 13 }}>{title || 'No data available'}</p>
      {description && <p style={{ color: 'var(--text-sub)', fontSize: 11 }}>{description}</p>}
    </div>
  )
}

/** Empty table row: `<tr><td colSpan={n} style text-align center><span class="t-faint">…</span></td></tr>`. */
export function TableEmptyRow({ colSpan, message = 'No data', style }: {
  colSpan: number
  message?: string
  style?: CSSProperties
}) {
  return (
    <tr>
      <td colSpan={colSpan} style={{ textAlign: 'center', ...style }}>
        <span className="t-faint">{message}</span>
      </td>
    </tr>
  )
}

/** Empty panel — dashboard tab "Loading..."/'No X' t-panel pattern. */
export function EmptyPanel({ message, children }: { message: string; children?: ReactNode }) {
  return (
    <div className="t-panel" style={{ padding: 16, textAlign: 'center' }}>
      <p style={{ fontSize: 12, color: 'var(--text-faint)' }}>{message}</p>
      {children}
    </div>
  )
}

/** One-line faint note (beta-dashboard `fontSize:11 var(--text-faint)` pattern). */
export function EmptyNote({ children, style }: { children: ReactNode; style?: CSSProperties }) {
  return <div style={{ fontSize: 11, color: 'var(--text-faint)', ...style }}>{children}</div>
}
