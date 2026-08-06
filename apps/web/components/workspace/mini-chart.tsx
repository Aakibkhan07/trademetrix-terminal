'use client'

import { Sparkline } from '@/components/ui/sparkline'

interface MiniChartProps {
  values: number[]
  width?: number
  height?: number
}

export default function MiniChart({ values, width = 72, height = 26 }: MiniChartProps) {
  return <Sparkline values={values} width={width} height={height} strokeWidth={1.3} padding={3} />
}