'use client'

import type { RefObject, CSSProperties } from 'react'
import { colorVar } from './chart-shell'

/** Chart crosshair tooltip div — backtest chart tooltip markup, verbatim. */
export function ChartTooltip({ tooltipRef, width, border }: {
  tooltipRef: RefObject<HTMLDivElement>
  width?: number
  border?: boolean
}) {
  return (
    <div
      ref={tooltipRef}
      style={{
        display: 'none', position: 'absolute', pointerEvents: 'none', zIndex: 5,
        background: colorVar('--bg-secondary', '#1e1e2f'), color: colorVar('--text', '#eee'),
        padding: '3px 6px', borderRadius: 4, fontSize: 10, fontFamily: 'var(--font-mono)',
        ...(width ? { width } : {}),
        ...(border ? { border: '1px solid var(--border)' } : {}),
      } as CSSProperties}
    />
  )
}
