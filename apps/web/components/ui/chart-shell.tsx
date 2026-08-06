'use client'

import { useEffect, useRef, type RefObject } from 'react'
import { ColorType, type DeepPartial, type TimeChartOptions } from 'lightweight-charts'

/** Resolve a CSS variable to its computed value (chart.tsx helper, verbatim). */
export const colorVar = (name: string, fallback = '#8888a0'): string =>
  typeof window !== 'undefined' ? (getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback) : fallback

/** Hex + alpha → rgba string (chart.tsx helper, verbatim). */
export const mix = (hex: string, pct: number): string => {
  const h = hex.replace('#', '')
  const full = h.length === 3 ? h.split('').map(c => c + c).join('') : h
  const alpha = Math.round((pct / 100) * 255).toString(16).padStart(2, '0')
  return `#${full.slice(0, 6)}${alpha}`
}

/** Shared lightweight-charts option base (chart.tsx + backtest charts, verbatim). */
export function chartOptions({ height, rightScaleMargins, crosshairMode, fontFamily }: {
  height: number
  rightScaleMargins?: { top: number; bottom: number }
  crosshairMode?: number
  fontFamily?: string
}): DeepPartial<TimeChartOptions> {
  return {
    height,
    layout: {
      background: { type: ColorType.Solid, color: 'transparent' },
      textColor: colorVar('--text-sub'),
      fontSize: 10,
      fontFamily: fontFamily || 'var(--font-body)',
    },
    grid: {
      vertLines: { color: mix(colorVar('--violet'), 6) },
      horzLines: { color: mix(colorVar('--violet'), 6) },
    },
    crosshair: {
      ...(crosshairMode !== undefined ? { mode: crosshairMode } : {}),
      vertLine: { color: mix(colorVar('--violet'), 30), width: 1, style: 2, labelBackgroundColor: colorVar('--bg-secondary') },
      horzLine: { color: mix(colorVar('--violet'), 30), width: 1, style: 2, labelBackgroundColor: colorVar('--bg-secondary') },
    },
    timeScale: {
      borderColor: mix(colorVar('--text-inverse'), 6),
      timeVisible: true,
      secondsVisible: false,
    },
    rightPriceScale: {
      borderColor: mix(colorVar('--text-inverse'), 6),
      ...(rightScaleMargins ? { scaleMargins: rightScaleMargins } : {}),
    },
  }
}

/** ResizeObserver wiring shared by all chart components. */
export function useChartResize(chartRef: RefObject<{ applyOptions: (o: { width: number }) => void }>, containerRef: RefObject<HTMLElement>) {
  useEffect(() => {
    const container = containerRef.current
    const chart = chartRef.current
    if (!container || !chart) return
    const ro = new ResizeObserver(() => chart.applyOptions({ width: container.clientWidth }))
    ro.observe(container)
    return () => ro.disconnect()
  }, [chartRef, containerRef])
}
