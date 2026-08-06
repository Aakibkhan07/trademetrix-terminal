'use client'

import { useMemo } from 'react'

/**
 * Sparkline — inline line chart. Consolidates `workspace/mini-chart.tsx` (MiniChart)
 * and the analytics-page inline EquityMiniChart; both produced this exact markup.
 */
export function Sparkline({ values, width = 72, height = 26, strokeWidth = 1.3, padding = 3, dashed, style }: {
  values: number[]
  width?: number
  height?: number
  strokeWidth?: number
  padding?: number
  dashed?: boolean
  style?: React.CSSProperties
}) {
  const d = useMemo(() => {
    const clean = values.filter(v => Number.isFinite(v))
    if (clean.length < 2) return null
    const min = Math.min(...clean)
    const max = Math.max(...clean)
    const range = max - min || 1
    const pts = clean.map((v, i) => {
      const x = (i / (clean.length - 1)) * width
      const y = height - padding - ((v - min) / range) * (height - padding * 2)
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    return { path: `M${pts.join('L')}`, color: clean[clean.length - 1] >= clean[0] ? 'var(--green)' : 'var(--red)' }
  }, [values, width, height, padding])

  if (!d) return <span className="t-faint" style={{ fontSize: 9 }}>—</span>

  return (
    <svg width={width} height={height} style={{ display: 'block', ...style }}>
      {dashed && <line x1={0} y1={height / 2} x2={width} y2={height / 2} stroke="var(--border)" strokeWidth={0.5} strokeDasharray="2 2" />}
      <path d={d.path} fill="none" stroke={d.color} strokeWidth={strokeWidth} strokeLinejoin="round" strokeLinecap="round" opacity={0.9} />
    </svg>
  )
}
