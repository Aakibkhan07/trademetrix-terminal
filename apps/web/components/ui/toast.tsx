'use client'

import type { CSSProperties } from 'react'
import { colorVar } from './chart-shell'

/** Toast view — emitted by the toast store (`lib/use-toast.tsx`); markup verbatim. */
export function ToastItem({ type, message, onRemove, style }: {
  type: 'success' | 'error' | 'info' | 'warning'
  message: string
  onRemove: () => void
  style?: CSSProperties
}) {
  const icon = {
    success: '✓',
    error: '✕',
    info: 'i',
    warning: '!',
  }[type]

  return (
    <div
      className={`t-toast t-toast-${type}`}
      onClick={onRemove}
      role="alert"
      style={style}
    >
      <span className="t-toast-icon">{icon}</span>
      <span className="t-toast-message">{message}</span>
    </div>
  )
}