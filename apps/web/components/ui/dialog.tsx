'use client'

import type { CSSProperties, ReactNode } from 'react'

/**
 * Modal shell — emits the design-system `t-modal-overlay` / `t-modal` structure used by
 * every existing dialog. `maxWidth`/`padding` mirror the per-instance overrides.
 */
export function Dialog({ onClose, open, maxWidth, padding, title, overlayStyle, style, className, children }: {
  onClose: () => void
  open?: boolean
  maxWidth?: number | string
  padding?: number | string
  title?: ReactNode
  titleClassName?: string
  overlayStyle?: CSSProperties
  style?: CSSProperties
  className?: string
  children: ReactNode
}) {
  if (open === false) return null
  return (
    <div className="t-modal-overlay" onClick={onClose} style={overlayStyle}>
      <div
        className={className || 't-modal'}
        onClick={(e) => e.stopPropagation()}
        style={{ ...(maxWidth !== undefined ? { maxWidth } : {}), ...(padding !== undefined ? { padding } : {}), ...style }}
      >
        {title}
        {children}
      </div>
    </div>
  )
}