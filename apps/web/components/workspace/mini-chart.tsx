'use client'

import { useMemo } from 'react'

interface MiniChartProps {
  values: number[]
  width?: number
  height?: number
}

export default function MiniChart({ values, width = 72, height = 26 }: MiniChartProps) {
  const d = useMemo(() => {
    const clean = values.filter(v => Number.isFinite(v))
    if (clean.length < 2) return null
    const min = Math.min(...clean)
    const max = Math.max(...clean)
    const range = max - min || 1
    const pts = clean.map((v, i) => {
      const x = (i / (clean.length - 1)) * width
      const y = height - 3 - ((v - min) / range) * (height - 6)
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    return { path: `M${pts.join('L')}`, color: clean[clean.length - 1] >= clean[0] ? 'var(--green)' : 'var(--red)' }
  }, [values, width, height])

  if (!d) return <span className="t-faint" style={{ fontSize: 9 }}>—</span>

  return (
    <svg width={width} height={height} style={{ display: 'block' }}>
      <path d={d.path} fill="none" stroke={d.color} strokeWidth={1.3} strokeLinejoin="round" strokeLinecap="round" opacity={0.9} />
    </svg>
  )
}
