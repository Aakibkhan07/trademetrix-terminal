'use client'

import { useEffect, type CSSProperties, type ReactNode } from 'react'

/**
 * Slide-in drawer — emits the design-system `t-drawer-overlay` / `t-drawer` /
 * `t-drawer-header` / `t-drawer-body` structure (quick-order drawer markup).
 * Escape key closes; overlay click closes; panel click stops propagation.
 */
export function Drawer({ open, onClose, title, subtitle, footer, children }: {
  open: boolean
  onClose: () => void
  title: ReactNode
  subtitle?: ReactNode
  footer?: ReactNode
  children: ReactNode
}) {
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="t-drawer-overlay" onClick={onClose}>
      <div className="t-drawer" onClick={e => e.stopPropagation()}>
        <div className="t-drawer-header">
          <div>
            <div className="t-drawer-title">{title}</div>
            {subtitle && <div className="t-faint" style={{ fontSize: 11, marginTop: 2 }}>{subtitle}</div>}
          </div>
          <button className="t-btn t-btn-sm t-btn-ghost" onClick={onClose}>✕</button>
        </div>
        <div className="t-drawer-body">{children}</div>
        {footer && <div className="t-drawer-header" style={{ borderTop: '1px solid var(--border)', borderBottom: 'none' }}>{footer}</div>}
      </div>
    </div>
  )
}