'use client'

interface EquityCurveProps {
  points: number[]
  height?: number
}

export default function EquityCurve({ points, height = 200 }: EquityCurveProps) {
  if (points.length < 2) return null

  const min = Math.min(...points)
  const max = Math.max(...points)
  const range = max - min || 1
  const width = 600
  const padding = { top: 20, right: 20, bottom: 30, left: 60 }
  const chartW = width - padding.left - padding.right
  const chartH = height - padding.top - padding.bottom

  const start = points[0]
  const end = points[points.length - 1]
  const isPositive = end >= start
  const lineColor = isPositive ? '#22c55e' : '#ef4444'
  const fillColor = isPositive ? 'rgba(34,197,94,0.08)' : 'rgba(239,68,68,0.08)'

  const xScale = (i: number) => padding.left + (i / (points.length - 1)) * chartW
  const yScale = (v: number) => padding.top + chartH - ((v - min) / range) * chartH

  const linePath = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${xScale(i)},${yScale(p)}`).join('')
  const areaPath = `${linePath}L${xScale(points.length - 1)},${padding.top + chartH}L${xScale(0)},${padding.top + chartH}Z`

  const yTicks = 5
  const yStep = range / yTicks

  return (
    <svg viewBox={`0 0 ${width} ${height}`} style={{ width: '100%', height: 'auto' }}>
      <defs>
        <linearGradient id="equity-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={lineColor} stopOpacity="0.2" />
          <stop offset="100%" stopColor={lineColor} stopOpacity="0.02" />
        </linearGradient>
      </defs>

      {Array.from({ length: yTicks + 1 }).map((_, i) => {
        const y = padding.top + (i / yTicks) * chartH
        return (
          <g key={i}>
            <line x1={padding.left} y1={y} x2={width - padding.right} y2={y} stroke="rgba(139,92,246,0.08)" strokeWidth={1} />
              <text x={padding.left - 8} y={y + 4} textAnchor="end" fill="#555570" fontSize={10} fontFamily="'Inter', sans-serif">
              {Math.round(min + yStep * (yTicks - i)).toLocaleString()}
            </text>
          </g>
        )
      })}

      <path d={areaPath} fill="url(#equity-fill)" />
      <path d={linePath} fill="none" stroke={lineColor} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />

      <text x={padding.left} y={padding.top - 8} fill={lineColor} fontSize={11} fontFamily="'Inter', sans-serif" fontWeight={600}>
        {isPositive ? '+' : ''}{(end - start).toLocaleString()} ({isPositive ? '+' : ''}{((end - start) / start * 100).toFixed(1)}%)
      </text>
    </svg>
  )
}
