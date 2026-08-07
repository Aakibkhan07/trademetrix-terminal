'use client'

import { Suspense, useState, useEffect, useMemo, useCallback, useRef } from 'react'
import { useSearchParams } from 'next/navigation'
import { api, backtestExportUrl } from '@/lib/api'
import { KpiCard } from '@/components/ui/kpi-card'
import { colorVar, mix, chartOptions } from '@/components/ui/chart-shell'
import { INDEXES, indexMeta, groupExpiries, MONEYNESS_OPTIONS } from '@/lib/options-contracts'
import type { IndexKey, Moneyness } from '@/lib/options-contracts'
import {
  createChart, ColorType, LineSeries, AreaSeries, CandlestickSeries, CrosshairMode, createSeriesMarkers, LineStyle,
  type IChartApi, type ISeriesApi, type Time, type UTCTimestamp,
  type SeriesMarker, type LineData, type MouseEventParams, type IPriceLine,
} from 'lightweight-charts'

const BUILTIN_STRATEGIES = [
  { id: 'trend_rider', name: 'Trend Rider' },
  { id: 'orb_pro', name: 'ORB Pro' },
  { id: 'smc_sniper', name: 'SMC Sniper' },
  { id: 'expiry_hunter', name: 'Expiry Hunter' },
  { id: 'rsi_mean_reversion', name: 'RSI Mean Reversion' },
  { id: 'bollinger_bandit', name: 'Bollinger Bandit' },
  { id: 'macd_cross', name: 'MACD Cross' },
  { id: 'vwap_band', name: 'VWAP Band' },
]

const INTERVALS = [
  { id: '5m', label: '5 min' },
  { id: '15m', label: '15 min' },
  { id: '1h', label: '1 hour' },
  { id: '1d', label: 'Daily' },
]

const WEEKDAYS = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN']

interface BTTrade {
  symbol: string; side: string; entry_price: number; exit_price: number
  quantity: number; pnl: number; entry_time: string; exit_time: string
  duration_minutes?: number; entry_reason?: string; exit_reason?: string
  slippage?: number; charges?: number; taxes?: number; cost_total?: number
  risk_amount?: number; rr?: number
}

interface BTCandle {
  timestamp: string; open: number; high: number; low: number; close: number; volume: number
}

interface TradeView {
  index: number; sub: number; total: number
  symbol: string; side: string
  entryPrice: number; exitPrice: number; quantity: number
  pnl: number; rr: number; riskAmount: number
  sl: number | null; target: number | null
  entryReason: string; exitReason: string
  charges: number; taxes: number; slippage: number; costTotal: number; durationMinutes: number
  entryTime: string; exitTime: string
  riskText: string; drawdownAtEntry: number | null; capitalAtEntry: number | null
  entryIdx: number; exitIdx: number; pnlText: string
}

interface BTResult {
  run_id: string; status: string; strategy_id: string
  config: {
    strategy_type: string; symbol: string; interval: string; days: number; initial_capital: number
    strategy_id?: string; exchange?: string; data_source?: string; risk_enabled?: boolean
    close_positions_on_end?: boolean; slippage_pct?: number; latency_candles?: number
    partial_fill_probability?: number; speed?: string
  }
  summary: {
    total_trades: number; winning_trades: number; losing_trades: number; win_rate: number
    net_pnl: number; profit_factor: number; max_drawdown_pct: number; sharpe_ratio: number
    sortino_ratio: number; calmar_ratio: number; return_pct: number; expectancy: number
    expectancy_per_r: number; avg_risk_reward_ratio: number; median_risk_reward_ratio: number
    alpha: number; beta: number; benchmark_return_pct: number; excess_return_pct: number
    candles_analyzed: number; start_equity: number; end_equity: number
  }
  trades: BTTrade[]
  equity_curve: { index?: number; equity: number; timestamp?: string; drawdown?: number; drawdown_pct?: number }[]
  weekday_distribution: Record<string, number>
  hour_distribution: Record<string, number>
  month_distribution: Record<string, number>
  duration_seconds: number
  risk_analytics?: BTRiskAnalytics
  error?: string
}

interface BTRiskRejection {
  timestamp: string; symbol: string; side: string; quantity: number; price: number
  rule: string; reason: string; capital_remaining: number; risk_remaining: number
  drawdown: number; exposure: number
}

interface BTRiskTimelinePoint {
  index: number; timestamp: string; equity: number; exposure: number
  drawdown_pct: number; capital_remaining: number; risk_remaining: number; status?: string
}

interface BTRiskAnalytics {
  enabled: boolean; accepted_trades: number; rejected_trades: number; halt_count: number
  rejection_reasons: Record<string, number>
  timeline: BTRiskTimelinePoint[]
  capital_curve: { index: number; timestamp: string; value: number }[]
  exposure_curve: { index: number; timestamp: string; value: number }[]
  rejections?: BTRiskRejection[]
  rejections_truncated?: boolean
}

interface OptimizeResult {
  run_id: string; status: string; method: string; strategy_type: string; symbol: string
  combos_total: number; combos_completed: number
  results: { params: Record<string, string | number>; metrics: Record<string, number>; error?: string }[]
  best: Record<string, unknown>
  distribution: Record<string, number>
  error?: string
}

interface BuilderStrategyItem { id: string; name: string; status: string }

function fmt(x: number | null | undefined, digits = 2): string {
  if (x === null || x === undefined || Number.isNaN(x)) return '—'
  return Number(x).toFixed(digits)
}

function fmtMoney(x: number | null | undefined): string {
  if (x === null || x === undefined || Number.isNaN(x)) return '—'
  const sign = x >= 0 ? '+' : ''
  return `${sign}₹${Math.round(x).toLocaleString('en-IN')}`
}

function candleTime(ts: string, fallback: number): Time {
  const t = new Date(ts).getTime() / 1000
  return (Number.isFinite(t) ? t : fallback) as Time
}

function nearestCandleIdx(candles: BTCandle[], ts: string): number {
  if (!candles.length) return 0
  if (!ts) return 0
  const target = new Date(ts).getTime()
  let best = 0
  let bestDiff = Infinity
  for (let i = 0; i < candles.length; i++) {
    const diff = Math.abs(new Date(candles[i].timestamp).getTime() - target)
    if (diff < bestDiff) { bestDiff = diff; best = i }
  }
  return best
}

function BacktestChart({ points, height = 170, color = '#34d399', mode = 'equity', trades = [], onSelectTrade }: {
  points: { time: Time; value: number }[]
  height?: number
  color?: string
  mode?: 'equity' | 'drawdown'
  trades?: BTTrade[]
  onSelectTrade?: (idx: number) => void
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const tooltipRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const container = containerRef.current
    if (!container || points.length < 2) return

    const isEquity = mode === 'equity'
    const chart: IChartApi = createChart(container, {
      ...chartOptions({ height, crosshairMode: CrosshairMode.Normal, rightScaleMargins: { top: 0.1, bottom: 0.15 } }),
    })

    const series: ISeriesApi<'Line'> = chart.addSeries(LineSeries, {
      color,
      lineWidth: 2,
      priceLineVisible: true,
      lastValueVisible: true,
      priceFormat: {
        type: 'custom',
        formatter: (p: number) => isEquity
          ? `₹${Math.round(p).toLocaleString('en-IN')}`
          : `${p.toFixed(2)}%`,
      },
    })
    series.setData(points)

    const times = points.map(p => p.time as number)
    const snap = (ts: string | undefined) => {
      if (!ts) return undefined
      const t = new Date(ts).getTime() / 1000
      for (let i = times.length - 1; i >= 0; i--) {
        if (times[i] <= t) return times[i]
      }
      return undefined
    }

    let markersPlugin: ReturnType<typeof createSeriesMarkers<Time>> | null = null
    if (isEquity && trades.length) {
      const markers: SeriesMarker<Time>[] = []
      for (const tr of trades) {
        const entryT = snap(tr.entry_time)
        if (entryT !== undefined) markers.push({ time: entryT as UTCTimestamp, position: 'belowBar', shape: 'arrowUp', color: colorVar('--green', '#34d399'), text: 'E' })
        const exitT = snap(tr.exit_time)
        if (exitT !== undefined) markers.push({ time: exitT as UTCTimestamp, position: 'aboveBar', shape: 'arrowDown', color: colorVar('--red', '#f87171'), text: 'X' })
      }
      if (markers.length) markersPlugin = createSeriesMarkers(series, markers)
    }

    const tooltip = tooltipRef.current
    const onCrosshairMove = (param: MouseEventParams) => {
      if (!tooltip) return
      if (!param.time || !param.point) { tooltip.style.display = 'none'; return }
      const data = param.seriesData.get(series) as LineData | undefined
      if (!data) { tooltip.style.display = 'none'; return }
      const label = isEquity
        ? `₹${Math.round(data.value).toLocaleString('en-IN')}`
        : `${data.value.toFixed(2)}%`
      tooltip.textContent = `${new Date((data.time as number) * 1000).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })} · ${label}`
      tooltip.style.display = 'block'
      const rect = container.getBoundingClientRect()
      tooltip.style.left = `${Math.min(param.point.x + 12, rect.width - 110)}px`
      tooltip.style.top = `${Math.max(param.point.y - 26, 2)}px`
    }
    chart.subscribeCrosshairMove(onCrosshairMove)

    let unsubClick: (() => void) | null = null
    if (isEquity && onSelectTrade && trades.length) {
      const clickTimes = trades.map(t => {
        const entry = snap(t.entry_time)
        const exit = snap(t.exit_time)
        return { entry, exit, pnl: t.pnl }
      }).filter(x => x.entry !== undefined)
      const onClick = (param: MouseEventParams) => {
        if (!param.time || !clickTimes.length) return
        const t = param.time as number
        let bestIdx = -1
        let bestDiff = Infinity
        clickTimes.forEach((c, i) => {
          if (c.entry !== undefined && t >= c.entry && (c.exit === undefined || t <= c.exit)) { bestIdx = i; return }
          const d = Math.min(Math.abs((c.entry as number) - t), c.exit !== undefined ? Math.abs(c.exit - t) : Infinity)
          if (d < bestDiff) { bestDiff = d; bestIdx = i }
        })
        if (bestIdx >= 0) onSelectTrade(bestIdx)
      }
      chart.subscribeClick(onClick)
      unsubClick = () => chart.unsubscribeClick(onClick)
    }

    const ro = new ResizeObserver(() => chart.applyOptions({ width: container.clientWidth }))
    ro.observe(container)

    return () => {
      chart.unsubscribeCrosshairMove(onCrosshairMove)
      unsubClick?.()
      markersPlugin?.detach()
      ro.disconnect()
      chart.remove()
    }
  }, [points, height, color, mode, trades, onSelectTrade])

  if (points.length < 2) return null
  return (
    <div style={{ position: 'relative' }}>
      <div ref={containerRef} />
      <div
        ref={tooltipRef}
        style={{
          display: 'none', position: 'absolute', pointerEvents: 'none', zIndex: 5,
          background: colorVar('--bg-secondary', '#1e1e2f'), color: colorVar('--text', '#eee'),
          padding: '3px 6px', borderRadius: 4, fontSize: 10, fontFamily: 'var(--font-mono)',
        }}
      />
    </div>
  )
}

function TradeChart({ candles, view, replaying, onReplayEnd }: {
  candles: BTCandle[]
  view: TradeView
  replaying: boolean
  onReplayEnd?: () => void
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const tooltipRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const pluginRef = useRef<ReturnType<typeof createSeriesMarkers<Time>> | null>(null)
  const priceLinesRef = useRef<IPriceLine[]>([])
  const dataRef = useRef<{ time: Time; open: number; high: number; low: number; close: number }[]>([])
  const viewRef = useRef<TradeView>(view)
  const currentIdxRef = useRef<number | null>(null)
  const [currentIdx, setCurrentIdx] = useState<number | null>(null)

  useEffect(() => { viewRef.current = view }, [view])

  useEffect(() => {
    const container = containerRef.current
    if (!container || candles.length < 2) return

    const chart: IChartApi = createChart(container, {
      height: 280,
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: colorVar('--text-sub', '#8888a0'),
        fontSize: 10,
        fontFamily: 'var(--font-mono)',
      },
      grid: { vertLines: { color: mix(colorVar('--violet'), 6) }, horzLines: { color: mix(colorVar('--violet'), 6) } },
      crosshair: { mode: CrosshairMode.Normal },
      timeScale: { borderColor: mix(colorVar('--text-inverse'), 6), timeVisible: true, secondsVisible: false },
      rightPriceScale: { borderColor: mix(colorVar('--text-inverse'), 6), scaleMargins: { top: 0.12, bottom: 0.18 } },
    })

    const series: ISeriesApi<'Candlestick'> = chart.addSeries(CandlestickSeries, {
      upColor: colorVar('--green', '#34d399'),
      downColor: colorVar('--red', '#ef4444'),
      borderUpColor: colorVar('--green', '#34d399'),
      borderDownColor: colorVar('--red', '#ef4444'),
      wickUpColor: colorVar('--green', '#34d399'),
      wickDownColor: colorVar('--red', '#ef4444'),
      priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
    })

    const data = candles.map((c, i) => ({
      time: candleTime(c.timestamp, i), open: c.open, high: c.high, low: c.low, close: c.close,
    }))
    dataRef.current = data
    series.setData(data)

    const plugin = createSeriesMarkers(series, [])
    pluginRef.current = plugin
    chartRef.current = chart
    seriesRef.current = series

    const tooltip = tooltipRef.current
    const onCrosshairMove = (param: MouseEventParams) => {
      if (!tooltip) return
      const candle = param.seriesData.get(series) as { open: number; high: number; low: number; close: number } | undefined
      if (!param.time || !param.point || !candle) { tooltip.style.display = 'none'; return }
      const v = viewRef.current
      tooltip.innerHTML =
        `<div style="font-weight:700;margin-bottom:2px">${new Date((param.time as number) * 1000).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}</div>` +
        `<div style="opacity:.85">O ${candle.open.toFixed(2)} · H ${candle.high.toFixed(2)} · L ${candle.low.toFixed(2)} · C ${candle.close.toFixed(2)}</div>` +
        `<div style="opacity:.85">${v.symbol} ${v.side} ${v.quantity} @ ${v.entryPrice.toFixed(2)} → ${v.exitPrice.toFixed(2)}</div>` +
        `<div style="margin-top:2px"><strong>P&L ${v.pnlText}</strong> · RR ${v.rr ? v.rr.toFixed(2) : '—'} · risk ₹${Math.round(v.riskAmount).toLocaleString('en-IN')}</div>` +
        `<div style="opacity:.85">${v.entryReason} → ${v.exitReason}</div>` +
        `<div style="opacity:.85">${v.riskText}</div>` +
        `<div style="opacity:.85">charges ${fmtMoney(v.charges)} · taxes ${fmtMoney(v.taxes)} · slippage ${fmtMoney(v.slippage)} · cost ${fmtMoney(v.costTotal)}</div>`
      tooltip.style.display = 'block'
      const rect = container.getBoundingClientRect()
      tooltip.style.left = `${Math.min(param.point.x + 14, Math.max(0, rect.width - 260))}px`
      tooltip.style.top = `${Math.min(param.point.y + 14, Math.max(0, rect.height - 150))}px`
    }
    chart.subscribeCrosshairMove(onCrosshairMove)

    const ro = new ResizeObserver(() => chart.applyOptions({ width: container.clientWidth }))
    ro.observe(container)

    return () => {
      ro.disconnect()
      chart.unsubscribeCrosshairMove(onCrosshairMove)
      plugin.detach()
      chart.remove()
      chartRef.current = null
      seriesRef.current = null
      pluginRef.current = null
      priceLinesRef.current = []
    }
  }, [candles])

  useEffect(() => {
    const chart = chartRef.current
    const series = seriesRef.current
    const plugin = pluginRef.current
    if (!chart || !series || !plugin) return
    const data = dataRef.current

    priceLinesRef.current.forEach(l => series.removePriceLine(l))
    priceLinesRef.current = []
    if (view.sl != null) {
      priceLinesRef.current.push(series.createPriceLine({ price: view.sl, color: '#f59e0b', lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: 'SL' }))
    }
    if (view.target != null) {
      priceLinesRef.current.push(series.createPriceLine({ price: view.target, color: '#22d3ee', lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: 'TGT' }))
    }

    const markers: SeriesMarker<Time>[] = []
    if (view.entryIdx >= 0 && data[view.entryIdx]) {
      markers.push({ time: data[view.entryIdx].time, position: 'belowBar', color: colorVar('--green', '#34d399'), shape: 'arrowUp', text: `E ${view.side}`, size: 1 })
    }
    if (view.exitIdx >= 0 && data[view.exitIdx]) {
      markers.push({ time: data[view.exitIdx].time, position: 'aboveBar', color: view.pnl >= 0 ? colorVar('--green', '#34d399') : colorVar('--red', '#ef4444'), shape: 'arrowDown', text: `X ${view.pnlText}`, size: 1 })
    }
    if (currentIdx != null && data[currentIdx]) {
      markers.push({ time: data[currentIdx].time, position: 'inBar', color: '#22d3ee', shape: 'circle', text: '▶', size: 1 })
    }
    plugin.setMarkers(markers)
  }, [view, currentIdx])

  useEffect(() => {
    const chart = chartRef.current
    const data = dataRef.current
    if (!chart || !data.length) return
    if (view.entryIdx >= 0) {
      const from = Math.max(0, view.entryIdx - 8)
      const to = Math.min(data.length - 1, Math.max(view.entryIdx + 12, view.exitIdx + 12))
      chart.timeScale().setVisibleLogicalRange({ from, to })
    }
  }, [view])

  useEffect(() => {
    if (!replaying) { setCurrentIdx(null); return }
    currentIdxRef.current = view.entryIdx
    setCurrentIdx(view.entryIdx)
    const id = window.setInterval(() => {
      setCurrentIdx(prev => {
        const n = Math.min(prev == null ? view.entryIdx : prev + 1, view.exitIdx)
        currentIdxRef.current = n
        return n
      })
    }, 380)
    return () => window.clearInterval(id)
  }, [replaying, view])

  useEffect(() => {
    if (replaying && currentIdx != null && currentIdx >= view.exitIdx) {
      onReplayEnd?.()
    }
  }, [currentIdx, replaying, view, onReplayEnd])

  if (candles.length < 2) return null
  return (
    <div style={{ position: 'relative' }}>
      <div ref={containerRef} />
      <div
        ref={tooltipRef}
        style={{
          display: 'none', position: 'absolute', pointerEvents: 'none', zIndex: 5,
          background: colorVar('--bg-secondary', '#1e1e2f'), color: colorVar('--text', '#eee'),
          border: '1px solid var(--border)', padding: '6px 8px', borderRadius: 6,
          fontSize: 10, fontFamily: 'var(--font-mono)', width: 250, lineHeight: 1.5,
        }}
      />
    </div>
  )
}

function RiskChart({ timeline, height = 190 }: { timeline: BTRiskTimelinePoint[]; height?: number }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const tooltipRef = useRef<HTMLDivElement>(null)

  const series = useMemo(() => {
    const toSec = (ts: string, i: number) => {
      const t = new Date(ts).getTime() / 1000
      return (Number.isFinite(t) && t > 0) ? t : i
    }
    return {
      capital: timeline.map((p, i) => ({ time: toSec(p.timestamp, i) as Time, value: p.capital_remaining })),
      exposure: timeline.map((p, i) => ({ time: toSec(p.timestamp, i) as Time, value: p.exposure })),
      drawdown: timeline.map((p, i) => ({ time: toSec(p.timestamp, i) as Time, value: p.drawdown_pct ?? 0 })),
    }
  }, [timeline])

  useEffect(() => {
    const container = containerRef.current
    if (!container || timeline.length < 2) return

    const chart: IChartApi = createChart(container, {
      height,
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: colorVar('--text-sub', '#8888a0'),
        fontSize: 10,
        fontFamily: 'var(--font-body)',
      },
      grid: {
        vertLines: { color: mix(colorVar('--violet'), 6) },
        horzLines: { color: mix(colorVar('--violet'), 6) },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
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
        scaleMargins: { top: 0.1, bottom: 0.15 },
      },
    })

    const capitalSeries: ISeriesApi<'Line'> = chart.addSeries(LineSeries, {
      color: colorVar('--green', '#34d399'),
      lineWidth: 2,
      priceLineVisible: false,
      priceFormat: {
        type: 'custom',
        formatter: (p: number) => `₹${Math.round(p).toLocaleString('en-IN')}`,
      },
    })
    capitalSeries.setData(series.capital)

    const exposureSeries: ISeriesApi<'Area'> = chart.addSeries(AreaSeries, {
      lineColor: colorVar('--cyan', '#22d3ee'),
      topColor: mix(colorVar('--cyan', '#22d3ee'), 18),
      bottomColor: mix(colorVar('--cyan', '#22d3ee'), 0),
      lineWidth: 1,
      priceLineVisible: false,
      priceFormat: {
        type: 'custom',
        formatter: (p: number) => `₹${Math.round(p).toLocaleString('en-IN')} exp`,
      },
    })
    exposureSeries.setData(series.exposure)

    const ddSeries: ISeriesApi<'Line'> = chart.addSeries(LineSeries, {
      color: colorVar('--red', '#ef4444'),
      lineWidth: 1,
      priceLineVisible: false,
      priceFormat: {
        type: 'custom',
        formatter: (p: number) => `${p.toFixed(2)}% dd`,
      },
    })
    ddSeries.setData(series.drawdown)

    const tooltip = tooltipRef.current
    const onCrosshairMove = (param: MouseEventParams) => {
      if (!tooltip) return
      if (!param.time || !param.point) { tooltip.style.display = 'none'; return }
      const cap = param.seriesData.get(capitalSeries) as LineData | undefined
      const exp = param.seriesData.get(exposureSeries) as LineData | undefined
      const dd = param.seriesData.get(ddSeries) as LineData | undefined
      if (!cap && !exp && !dd) { tooltip.style.display = 'none'; return }
      const when = new Date(((cap?.time ?? exp?.time ?? dd?.time) as number) * 1000).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
      tooltip.textContent = [
        when,
        `cap ₹${Math.round(cap?.value ?? 0).toLocaleString('en-IN')}`,
        `exp ₹${Math.round(exp?.value ?? 0).toLocaleString('en-IN')}`,
        `${(dd?.value ?? 0).toFixed(2)}% dd`,
      ].join(' · ')
      tooltip.style.display = 'block'
      const rect = container.getBoundingClientRect()
      tooltip.style.left = `${Math.min(param.point.x + 12, rect.width - 130)}px`
      tooltip.style.top = `${Math.max(param.point.y - 26, 2)}px`
    }
    chart.subscribeCrosshairMove(onCrosshairMove)

    const ro = new ResizeObserver(() => chart.applyOptions({ width: container.clientWidth }))
    ro.observe(container)
    chart.timeScale().fitContent()

    return () => {
      chart.unsubscribeCrosshairMove(onCrosshairMove)
      ro.disconnect()
      chart.remove()
    }
  }, [timeline, height, series])

  if (timeline.length < 2) return null
  return (
    <div style={{ position: 'relative' }}>
      <div ref={containerRef} />
      <div
        ref={tooltipRef}
        style={{
          display: 'none', position: 'absolute', pointerEvents: 'none', zIndex: 5,
          background: colorVar('--bg-secondary', '#1e1e2f'), color: colorVar('--text', '#eee'),
          padding: '3px 6px', borderRadius: 4, fontSize: 10, fontFamily: 'var(--font-mono)',
        }}
      />
    </div>
  )
}

function BarChart({ data, height = 120, unit = '' }: { data: { label: string; value: number }[]; height?: number; unit?: string }) {
  if (data.length === 0) return null
  const maxVal = Math.max(...data.map(d => Math.abs(d.value)), 1)
  const w = 600
  const barW = Math.max(7, (w - 60) / data.length - 3)
  return (
    <svg viewBox={`0 0 ${w} ${height}`} style={{ width: '100%', height: 'auto' }}>
      <line x1={40} y1={height - 20} x2={w - 10} y2={height - 20} stroke="color-mix(in srgb, var(--text-inverse) 6%, transparent)" />
      <line x1={40} y1={16} x2={40} y2={height - 20} stroke="color-mix(in srgb, var(--text-inverse) 6%, transparent)" />
      {data.map((d, i) => {
        const xPos = 44 + i * (barW + 3)
        const barH = (Math.abs(d.value) / maxVal) * (height - 40)
        const yPos = d.value >= 0 ? height - 20 - barH : height - 20
        return (
          <g key={d.label}>
            <rect x={xPos} y={yPos} width={barW} height={Math.max(1, barH)} rx={2}
              fill={d.value >= 0 ? 'var(--green)' : 'var(--red)'} opacity={0.7} />
            <text x={xPos + barW / 2} y={height - 6} textAnchor="middle" fill="var(--text-faint)" fontSize={7} fontFamily="var(--font-sans)">
              {d.label.length > 5 ? d.label.slice(0, 5) : d.label}
            </text>
          </g>
        )
      })}
    </svg>
  )
}

function Heatmap({ data, title }: { data: Record<string, number>; title: string }) {
  const hours = Array.from({ length: 24 }, (_, h) => String(h).padStart(2, '0'))
  const flat = Object.values(data)
  const max = Math.max(...flat, 1)
  const min = Math.min(...flat, 0)
  const cell = 22
  return (
    <div>
      <div style={{ fontSize: 10, color: 'var(--text-faint)', marginBottom: 6, fontWeight: 700 }}>{title}</div>
      <div style={{ display: 'grid', gridTemplateColumns: `repeat(${24}, ${cell}px)`, gap: 2, overflowX: 'auto' }}>
        {hours.map(h => (
          <div key={h} style={{ fontSize: 8, color: 'var(--text-faint)', textAlign: 'center' }}>{h}</div>
        ))}
        {WEEKDAYS.map(day => (
          <div key={day}>
            {hours.map(h => {
              const v = data[`${day}-${h}`] ?? data[h] ?? 0
              const t = max > min ? (v - min) / (max - min) : 0
              const alpha = v === 0 ? 0.05 : 0.25 + t * 0.6
              return (
                <div key={`${day}-${h}`} style={{
                  width: cell, height: cell, borderRadius: 3, marginBottom: 2,
                  background: v >= 0 ? `rgba(34,197,94,${alpha})` : `rgba(239,68,68,${alpha})`,
                }} title={`${day} ${h}:00 — ${v}`} />
              )
            })}
          </div>
        ))}
      </div>
      <div style={{ display: 'flex', gap: 4, alignItems: 'center', marginTop: 4, fontSize: 8, color: 'var(--text-faint)' }}>
        <span>Mon</span>
        <div style={{ flex: 1, height: 4, borderRadius: 2, background: 'color-mix(in srgb, var(--text-inverse) 8%, transparent)' }} />
        <span>Fri</span>
      </div>
    </div>
  )
}

const kpiCard = (label: string, value: string, sub?: string, color?: string) => (
  <KpiCard label={label} value={value} sub={sub} color={color} />
)

const tiCard = (label: string, value: string, color?: string) => (
  <KpiCard label={label} value={value} color={color} variant="ti" />
)

/** Options quick-config: pick INDEX → EXPIRY → STRIKE in trader terms; loads the
 *  underlying index symbol into the backtest form. Candles are INDEX candles only —
 *  this is never presented as simulated option premiums. */
function OptionsQuickStrip({ onApply }: { onApply: (symbol: string, strikeLabel: string) => void }) {
  const [index, setIndex] = useState<IndexKey>('NIFTY')
  const [expiries, setExpiries] = useState<string[]>([])
  const [expiry, setExpiry] = useState('')
  const [spot, setSpot] = useState<number | null>(null)
  const [moneyness, setMoneyness] = useState<Moneyness>('ATM')
  const [loading, setLoading] = useState(false)
  const meta = indexMeta(index)

  useEffect(() => {
    let alive = true
    setLoading(true)
    api.marketdata.optionChain(index).then(d => {
      if (!alive) return
      const chain = (d as { optionChain?: { strike: number; call: { ltp: number }; put: { ltp: number } }[]; expiries?: string[] })
      const exps = chain.expiries || []
      setExpiries(exps)
      if (exps.length && !exps.includes(expiry)) setExpiry(exps[0])
      const spotRow = chain.optionChain?.length
        ? chain.optionChain.reduce((a, b) => a.call.ltp + a.put.ltp > 0 && (a.call.ltp + a.put.ltp) <= (b.call.ltp + b.put.ltp) && b.call.ltp + b.put.ltp > 0 ? a : b, chain.optionChain[0])
        : undefined
      setSpot(spotRow && (spotRow.call.ltp + spotRow.put.ltp) > 0 ? spotRow.strike : null)
    }).catch(() => { /* chain may be offline; fall back to index-only */ }).finally(() => {
      if (alive) setLoading(false)
    })
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [index])

  const step = MONEYNESS_OPTIONS.find(o => o.key === moneyness)?.offsetSteps ?? 0
  const strike = spot !== null ? spot + step * meta.strikeInterval : null

  return (
    <div style={{ background: 'color-mix(in srgb, var(--violet) 5%, transparent)', border: '1px solid color-mix(in srgb, var(--violet) 15%, transparent)', borderRadius: 'var(--radius-md)', padding: 12, marginBottom: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-sub)', letterSpacing: '0.08em' }}>OPTIONS QUICK-CONFIG</span>
        <span style={{ flex: 1 }} />
        <span style={{ fontSize: 9, color: 'var(--text-faint)' }}>{loading ? 'loading chain…' : `${meta.key} · ${expiries.length} expiries`}</span>
      </div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
        {INDEXES.map(i => (
          <button key={i.key} className={`t-chip ${index === i.key ? 'active' : ''}`} style={{ fontSize: 10 }} onClick={() => setIndex(i.key)}>{i.name}</button>
        ))}
        <span style={{ width: 1, height: 18, background: 'color-mix(in srgb, var(--text-inverse) 12%, transparent)' }} />
        {expiries.length > 0 && (
          <>
            {groupExpiries(expiries).all.map(e => (
              <button key={e} className={`t-chip ${expiry === e ? 'active' : ''}`} style={{ fontSize: 10 }} onClick={() => setExpiry(e)}>{e}</button>
            ))}
          </>
        )}
        <span style={{ width: 1, height: 18, background: 'color-mix(in srgb, var(--text-inverse) 12%, transparent)' }} />
        {MONEYNESS_OPTIONS.map(o => (
          <button key={o.key} className={`t-chip ${moneyness === o.key ? 'active' : ''}`} style={{ fontSize: 10 }} onClick={() => setMoneyness(o.key)}>{o.label}</button>
        ))}
        <span style={{ width: 1, height: 18, background: 'color-mix(in srgb, var(--text-inverse) 12%, transparent)' }} />
        <span style={{ fontSize: 11, fontWeight: 700, fontFamily: 'var(--font-mono)' }}>
          {strike !== null ? `${index}${expiry}${strike} CE/PE` : 'spot unavailable — using index only'}
        </span>
        <button
          className="t-btn t-btn-sm"
          style={{ marginLeft: 'auto' }}
          onClick={() => onApply(index, strike !== null ? `${index} ${expiry} ${strike}` : `${index} ${expiry}`)}
        >
          Load as Symbol
        </button>
      </div>
      <div style={{ marginTop: 8, fontSize: 9, color: 'var(--text-faint)' }}>
        Options backtests run on the UNDERLYING index candles — the engine prices {indexMeta(index).name} spot, not option premiums. Contract above is the reference strike only.
      </div>
    </div>
  )
}

export default function BacktestPage() {
  return (
    <Suspense fallback={null}>
      <BacktestContent />
    </Suspense>
  )
}

function BacktestContent() {
  const searchParams = useSearchParams()
  const initialStrategy = searchParams.get('strategy') || 'trend_rider'

  const [source, setSource] = useState<'builtin' | 'builder'>(initialStrategy === 'trend_rider' ? 'builtin' : 'builder')
  const [strategy, setStrategy] = useState(initialStrategy)
  const [builderStrategies, setBuilderStrategies] = useState<BuilderStrategyItem[]>([])
  const [symbol, setSymbol] = useState('NIFTY')
  const [interval, setInterval] = useState('15m')
  const [days, setDays] = useState(60)
  const [capital, setCapital] = useState(100000)
  const [slippage, setSlippage] = useState(0.05)
  const [latency, setLatency] = useState(0)
  const [partialFill, setPartialFill] = useState(0)
  const [riskEnabled, setRiskEnabled] = useState(true)

  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<BTResult | null>(null)
  const [error, setError] = useState('')

  const [activeTab, setActiveTab] = useState<'overview' | 'optimizer' | 'compare' | 'trades' | 'risk' | 'report'>('overview')

  const [optMethod, setOptMethod] = useState('grid')
  const [optMetric, setOptMetric] = useState('sharpe_ratio')
  const [optParamsText, setOptParamsText] = useState('fast_period=5,9,14,21\nslow_period=13,26')
  const [optRunning, setOptRunning] = useState(false)
  const [optResult, setOptResult] = useState<OptimizeResult | null>(null)
  const [optError, setOptError] = useState('')

  const [compareIdsText, setCompareIdsText] = useState('')
  const [compareRunning, setCompareRunning] = useState(false)
  const [comparison, setComparison] = useState<Record<string, Record<string, unknown>> | null>(null)
  const [compareError, setCompareError] = useState('')

  const [sharing, setSharing] = useState(false)
  const [shareLink, setShareLink] = useState('')
  const [shareErr, setShareErr] = useState('')

  const [exporting, setExporting] = useState<string | null>(null)
  const [deploying, setDeploying] = useState(false)
  const [deployMsg, setDeployMsg] = useState('')

  const [selectedIdx, setSelectedIdx] = useState<number | null>(null)
  const [candles, setCandles] = useState<BTCandle[] | null>(null)
  const [candlesErr, setCandlesErr] = useState('')
  const [replaying, setReplaying] = useState(false)

  useEffect(() => {
    api.builder.list().then(res => {
      const items = Array.isArray(res) ? res : (res as { strategies?: BuilderStrategyItem[] }).strategies || []
      setBuilderStrategies(items.filter(s => s.status !== 'ARCHIVED' && s.status !== 'STOPPED'))
    }).catch(() => { /* skip */ })
  }, [])

  useEffect(() => {
    if (!result) return
    setSelectedIdx(null)
    setReplaying(false)
    setCandlesErr('')
    let cancelled = false
    setCandles(null)
    api.backtest.candles(result.config.symbol, result.config.interval, result.config.days || 60)
      .then((d) => {
        if (cancelled) return
        const data = d as { candles?: BTCandle[] } | undefined
        setCandles(Array.isArray(data?.candles) ? data.candles : null)
        if (!Array.isArray(data?.candles)) setCandlesErr('Candle data unavailable for this window')
      })
      .catch(() => {
        if (!cancelled) { setCandles(null); setCandlesErr('Candle data unavailable for this window') }
      })
    return () => { cancelled = true }
  }, [result])

  useEffect(() => { setReplaying(false) }, [selectedIdx])

  const handleRun = useCallback(async () => {
    setRunning(true); setError(''); setResult(null); setActiveTab('overview')
    try {
      let data: BTResult
      if (source === 'builder') {
        if (!strategy) throw new Error('Select a builder strategy')
        data = await api.backtest.runV3({
          strategy_id: strategy, symbol, interval, days,
          initial_capital: capital, risk_enabled: riskEnabled,
          slippage_pct: slippage, latency_candles: latency,
          partial_fill_probability: partialFill,
        })
      } else {
        data = await api.backtest.run({
          strategy_type: strategy, symbol, interval, days,
          initial_capital: capital, config: {},
          slippage_pct: slippage,
        })
      }
      setResult(data)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Backtest failed')
    } finally { setRunning(false) }
  }, [source, strategy, symbol, interval, days, capital, slippage, latency, partialFill, riskEnabled])

  const handleRunOptimize = useCallback(async () => {
    setOptRunning(true); setOptError(''); setOptResult(null)
    const paramRanges: Record<string, (string | number)[]> = {}
    for (const line of optParamsText.split('\n')) {
      const eq = line.indexOf('=')
      if (eq <= 0) continue
      const key = line.slice(0, eq).trim()
      const values = line.slice(eq + 1).split(',').map(v => {
        const n = Number(v.trim())
        return Number.isNaN(n) ? v.trim() : n
      }).filter(v => v !== '')
      if (key && values.length) paramRanges[key] = values
    }
    if (Object.keys(paramRanges).length === 0) {
      setOptError('Enter at least one parameter range (e.g. fast_period=5,9,14)')
      setOptRunning(false)
      return
    }
    try {
      const data = await api.backtest.optimize({
        strategy_type: strategy,
        method: optMethod,
        param_ranges: paramRanges,
        metric: optMetric,
        symbol, interval, days,
      })
      setOptResult(data as OptimizeResult)
    } catch (err: unknown) {
      setOptError(err instanceof Error ? err.message : 'Optimization failed')
    } finally { setOptRunning(false) }
  }, [strategy, optMethod, optMetric, optParamsText, symbol, interval, days])

  const handleCompare = useCallback(async () => {
    setCompareRunning(true); setCompareError(''); setComparison(null)
    const ids = compareIdsText.split(',').map(s => s.trim()).filter(Boolean)
    if (ids.length < 2) {
      setCompareError('Enter at least 2 run IDs (comma-separated)')
      setCompareRunning(false)
      return
    }
    try {
      const data = await api.backtest.compare<{ comparison: Record<string, Record<string, unknown>> }>(ids)
      setComparison(data.comparison)
    } catch (err: unknown) {
      setCompareError(err instanceof Error ? err.message : 'Compare failed')
    } finally { setCompareRunning(false) }
  }, [compareIdsText])

  const handleExport = useCallback(async (format: 'json' | 'csv' | 'pdf') => {
    if (!result) return
    setExporting(format)
    try {
      const url = backtestExportUrl(result.run_id, format)
      const res = await fetch(url, { credentials: 'include' })
      if (!res.ok) {
        const t = await res.text()
        try { const j = JSON.parse(t); throw new Error(j.detail || `Export failed: ${res.status}`) } catch (e) { throw e }
      }
      const blob = await res.blob()
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = `backtest-${result.run_id}.${format}`
      a.click()
      URL.revokeObjectURL(a.href)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Export failed')
    } finally { setExporting(null) }
  }, [result])

  const mintShare = useCallback(async (): Promise<string> => {
    if (!result) throw new Error('No backtest result')
    const data = await api.backtest.shareToken(result.run_id)
    return data.url
  }, [result])

  const handleShare = useCallback(async () => {
    setSharing(true); setShareErr('')
    try {
      const url = await mintShare()
      setShareLink(url)
      await navigator.clipboard?.writeText(url)
    } catch (err: unknown) {
      setShareLink('')
      setShareErr(err instanceof Error ? err.message : 'Could not create share link')
    } finally { setSharing(false) }
  }, [mintShare])

  const handleOpenReport = useCallback(async () => {
    setShareErr('')
    try {
      const url = await mintShare()
      window.open(url, '_blank', 'noopener,noreferrer')
    } catch (err: unknown) {
      setShareErr(err instanceof Error ? err.message : 'Could not open interactive report')
    }
  }, [mintShare])

  const handleDeployToPaper = useCallback(async () => {
    if (!result) return
    setDeploying(true); setDeployMsg('')
    try {
      const data = await api.backtest.deployToPaper(result.run_id)
      setDeployMsg(`Deployed to paper — ${data.status} (${data.strategy_id})`)
    } catch (err: unknown) {
      setDeployMsg(err instanceof Error ? err.message : 'Deploy failed')
    } finally { setDeploying(false) }
  }, [result])

  const s = result?.summary
  const risk = result?.risk_analytics
  const execSummary = useMemo(() => {
    if (!result || !s) return null
    const cfg = result.config
    const parts = [
      `This backtest of the ${cfg.strategy_type || 'strategy'} on ${cfg.symbol || 'NIFTY'} ${cfg.interval} over ${cfg.days} trading days (${s.candles_analyzed} candles analyzed, initial capital ${fmtMoney(s.start_equity)}) closed ${s.total_trades} trades with a net P&L of ${fmtMoney(s.net_pnl)} (${s.return_pct >= 0 ? '+' : ''}${fmt(s.return_pct)}% return), a win rate of ${fmt(s.win_rate, 1)}% and a profit factor of ${fmt(s.profit_factor)}.`,
      `The equity curve peaked at ${fmtMoney(s.end_equity - (s.start_equity * s.max_drawdown_pct / 100))} and gave back at most ${fmt(s.max_drawdown_pct)}% at the deepest drawdown, with a Sharpe of ${fmt(s.sharpe_ratio)}, Sortino of ${fmt(s.sortino_ratio)} and Calmar of ${fmt(s.calmar_ratio)}. Expectancy was ${fmtMoney(s.expectancy)} per trade at an average risk/reward of ${fmt(s.avg_risk_reward_ratio)}.`,
    ]
    if (s.benchmark_return_pct) {
      parts.push(`Against the benchmark (${s.benchmark_return_pct >= 0 ? '+' : ''}${fmt(s.benchmark_return_pct)}% return) the strategy produced ${s.alpha >= 0 ? '+' : ''}${fmt(s.alpha)}% alpha at a beta of ${fmt(s.beta)} (${s.excess_return_pct >= 0 ? '+' : ''}${fmt(s.excess_return_pct)}% excess return).`)
    }
    const profitable = s.net_pnl > 0
    const consistent = s.win_rate >= 50
    const verdict = profitable && consistent ? 'profitable and consistent (PASS)'
      : profitable ? 'profitable but inconsistent (CAUTION)' : 'not profitable in this window (FAIL)'
    const color = profitable && consistent ? 'var(--text-green)' : profitable ? 'var(--amber)' : 'var(--text-red)'
    return { parts, verdict, color }
  }, [result, s])

  const factSheet = useMemo(() => {
    if (!result || !s) return []
    const cfg = result.config
    return [
      ['Strategy', cfg.strategy_type || '—'],
      ['Strategy ID', cfg.strategy_id || '—'],
      ['Symbol / Exchange', `${cfg.symbol || 'NIFTY'} / ${cfg.exchange || 'NSE'}`],
      ['Interval / Window', `${cfg.interval} / ${cfg.days} days`],
      ['Initial Capital', fmtMoney(s.start_equity)],
      ['Data Source', cfg.data_source || 'auto'],
      ['Risk Checks', cfg.risk_enabled ? 'Enabled' : 'Disabled'],
      ['Close On End', cfg.close_positions_on_end ? 'Yes' : 'No'],
      ['Slippage', `${fmt(cfg.slippage_pct ?? 0)}%`],
      ['Latency', `${cfg.latency_candles ?? 0} candles`],
      ['Partial Fills', `${fmt((cfg.partial_fill_probability ?? 0) * 100)}%`],
      ['Speed', cfg.speed || '—'],
      ['Start Equity', fmtMoney(s.start_equity)],
      ['End Equity', fmtMoney(s.end_equity)],
      ['Candles Analyzed', String(s.candles_analyzed)],
      ['Run Duration', `${fmt(result.duration_seconds)}s`],
      ['Run ID', result.run_id],
    ] as [string, string][]
  }, [result, s])
  const riskReasons = useMemo(() => Object.entries(risk?.rejection_reasons || {})
    .map(([label, value]) => ({ label, value }))
    .filter(d => d.value !== 0), [risk])
  const equityPoints = useMemo(() => (result?.equity_curve || []).map((p, i) => {
    const t = p.timestamp ? new Date(p.timestamp).getTime() / 1000 : i
    return { time: (Number.isFinite(t) ? t : i) as Time, value: p.equity }
  }), [result])

  const drawdownSeries = useMemo(() => {
    let peak = -Infinity
    return (result?.equity_curve || []).map((p, i) => {
      if (p.equity > peak) peak = p.equity
      const t = p.timestamp ? new Date(p.timestamp).getTime() / 1000 : i
      return {
        time: (Number.isFinite(t) ? t : i) as Time,
        value: peak > 0 ? ((peak - p.equity) / peak) * 100 : 0,
      }
    })
  }, [result])

  const jumpTargets = useMemo(() => {
    const trades = result?.trades || []
    const eq = result?.equity_curve || []
    let bestIdx = -1
    let worstIdx = -1
    let best = -Infinity
    let worst = Infinity
    trades.forEach((t, i) => {
      if (t.pnl > best) { best = t.pnl; bestIdx = i }
      if (t.pnl < worst) { worst = t.pnl; worstIdx = i }
    })
    let ddIdx = -1
    if (eq.length && trades.length) {
      let ddT = -Infinity
      let ddTime = ''
      for (const p of eq) {
        const d = Number(p.drawdown_pct ?? 0)
        if (d > ddT) { ddT = d; ddTime = p.timestamp || '' }
      }
      if (ddTime) {
        const t = new Date(ddTime).getTime()
        let nearest = -1
        let nearestDiff = Infinity
        for (let i = 0; i < trades.length; i++) {
          const et = new Date(trades[i].entry_time).getTime()
          const xt = new Date(trades[i].exit_time).getTime()
          if (ddIdx < 0 && et <= t && t <= xt) { ddIdx = i }
          const diff = Math.min(Math.abs(et - t), Math.abs(xt - t))
          if (diff < nearestDiff) { nearestDiff = diff; nearest = i }
        }
        if (ddIdx < 0) ddIdx = nearest
      }
    }
    return { bestIdx, worstIdx, ddIdx }
  }, [result])

  const selection: TradeView | null = useMemo(() => {
    if (selectedIdx == null || !result || !result.trades[selectedIdx]) return null
    const t = result.trades[selectedIdx]
    const cl = candles || []
    const riskEn = risk?.enabled
    const riskAmt = t.risk_amount ?? 0
    const sl = riskAmt > 0 && t.quantity > 0
      ? (t.side === 'SELL' ? t.entry_price + riskAmt / t.quantity : t.entry_price - riskAmt / t.quantity)
      : null
    const target = t.exit_reason === 'target' ? t.exit_price : null

    const entryIdx = nearestCandleIdx(cl, t.entry_time)
    const exitIdx = nearestCandleIdx(cl, t.exit_time)

    let ddAtEntry: number | null = null
    let capAtEntry: number | null = null
    if (result.equity_curve.length) {
      const tt = new Date(t.entry_time).getTime()
      let near = result.equity_curve[0]
      for (const p of result.equity_curve) {
        const pt = new Date(p.timestamp || '').getTime()
        if (Number.isFinite(pt) && pt <= tt) near = p
      }
      const dd = Number(near?.drawdown_pct ?? 0)
      if (dd > 0 || Number.isFinite(dd)) ddAtEntry = dd
    }
    if (riskEn && risk?.timeline?.length) {
      const tt = new Date(t.entry_time).getTime()
      let near = risk.timeline[0]
      for (const p of risk.timeline) {
        const pt = new Date(p.timestamp).getTime()
        if (Number.isFinite(pt) && pt <= tt) near = p
      }
      const cap = Number(near?.capital_remaining ?? 0)
      if (cap > 0) capAtEntry = cap
    }
    const riskText = riskEn
      ? `Risk ON${ddAtEntry != null ? ` · DD at entry ${fmt(ddAtEntry)}%` : ''}${capAtEntry != null ? ` · capital ₹${Math.round(capAtEntry).toLocaleString('en-IN')}` : ''}`
      : 'Risk OFF (no simulated checks)'

    return {
      index: selectedIdx,
      sub: selectedIdx + 1,
      total: result.trades.length,
      symbol: t.symbol,
      side: t.side,
      entryPrice: t.entry_price,
      exitPrice: t.exit_price,
      quantity: t.quantity,
      pnl: t.pnl,
      rr: t.rr ?? 0,
      riskAmount: riskAmt,
      sl,
      target,
      entryReason: t.entry_reason || 'signal',
      exitReason: t.exit_reason || 'signal',
      charges: t.charges ?? 0,
      taxes: t.taxes ?? 0,
      slippage: t.slippage ?? 0,
      costTotal: t.cost_total ?? 0,
      durationMinutes: t.duration_minutes ?? 0,
      entryTime: t.entry_time,
      exitTime: t.exit_time,
      riskText,
      drawdownAtEntry: ddAtEntry,
      capitalAtEntry: capAtEntry,
      entryIdx,
      exitIdx,
      pnlText: `${t.pnl >= 0 ? '+' : ''}${Math.round(t.pnl).toLocaleString('en-IN')}`,
    }
  }, [selectedIdx, result, candles, risk])

  const weekdayBars = useMemo(() => WEEKDAYS
    .map(d => ({ label: d, value: result?.weekday_distribution?.[d] || 0 }))
    .filter(d => d.value !== 0), [result])

  const hourBars = useMemo(() => Array.from({ length: 24 }, (_, h) => {
    const key = String(h).padStart(2, '0')
    return { label: key, value: result?.hour_distribution?.[key] || 0 }
  }).filter(d => d.value !== 0), [result])

  const monthBars = useMemo(() => Object.entries(result?.month_distribution || {})
    .map(([k, v]) => ({ label: k.slice(5, 7) || k, value: v })), [result])

  const bestCombo = useMemo(() => {
    if (!optResult?.results?.length) return null
    const key = optMetric
    return [...optResult.results].sort((a, b) => (b.metrics?.[key] ?? -Infinity) - (a.metrics?.[key] ?? -Infinity))[0]
  }, [optResult, optMetric])

  const selectedBuilderName = builderStrategies.find(b => b.id === strategy)?.name || strategy

  const tabs = ['overview', 'optimizer', 'compare', 'trades', ...(risk?.enabled ? (['risk'] as const) : []), 'report'] as Array<'overview' | 'optimizer' | 'compare' | 'trades' | 'risk' | 'report'>

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1 style={{ fontFamily: 'var(--font-body)', fontWeight: 700, fontSize: 18, margin: 0, color: 'var(--text)' }}>Backtest Engine</h1>
          <p style={{ color: 'var(--text-sub)', fontSize: 12, margin: '2px 0 0' }}>Institutional-grade backtesting for Indian markets — costs, corporate actions, continuous futures</p>
        </div>
        {result?.run_id && (
          <div style={{ fontSize: 10, color: 'var(--text-faint)', fontFamily: 'var(--font-mono)' }}>
            run {result.run_id} · {(result.duration_seconds || 0).toFixed(1)}s
          </div>
        )}
      </div>

      {/* Options quick-config (underlying index candles only) */}
      <OptionsQuickStrip onApply={(sym) => { setSymbol(sym); setSource('builtin') }} />

      {/* Run Form */}
      <div style={{ background: 'var(--panel)', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', padding: 12 }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: 8 }}>
          <div>
            <label style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-sub)', display: 'block', marginBottom: 3 }}>Source</label>
            <select className="t-select" value={source} onChange={e => {
              setSource(e.target.value as 'builtin' | 'builder')
              if (e.target.value === 'builder') setStrategy(builderStrategies[0]?.id || '')
            }}>
              <option value="builtin">Built-in</option>
              <option value="builder">Builder (DSL)</option>
            </select>
          </div>
          <div>
            <label style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-sub)', display: 'block', marginBottom: 3 }}>Strategy</label>
            {source === 'builtin' ? (
              <select className="t-select" value={strategy} onChange={e => setStrategy(e.target.value)}>
                {BUILTIN_STRATEGIES.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            ) : (
              <select className="t-select" value={strategy} onChange={e => setStrategy(e.target.value)}>
                {builderStrategies.length === 0 && <option value="">No builder strategies</option>}
                {builderStrategies.map(s => <option key={s.id} value={s.id}>{s.name} ({s.status.toLowerCase()})</option>)}
              </select>
            )}
          </div>
          <div>
            <label style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-sub)', display: 'block', marginBottom: 3 }}>Symbol</label>
            <input className="t-input" value={symbol} onChange={e => setSymbol(e.target.value.toUpperCase())} />
          </div>
          <div>
            <label style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-sub)', display: 'block', marginBottom: 3 }}>Interval</label>
            <select className="t-select" value={interval} onChange={e => setInterval(e.target.value)}>
              {INTERVALS.map(i => <option key={i.id} value={i.id}>{i.label}</option>)}
            </select>
          </div>
          <div>
            <label style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-sub)', display: 'block', marginBottom: 3 }}>Days</label>
            <input className="t-input" type="number" value={days} onChange={e => setDays(Number(e.target.value))} min={1} max={730} />
          </div>
          <div>
            <label style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-sub)', display: 'block', marginBottom: 3 }}>Capital</label>
            <input className="t-input" type="number" value={capital} onChange={e => setCapital(Number(e.target.value))} min={1000} />
          </div>
          <div>
            <label style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-sub)', display: 'block', marginBottom: 3 }}>Slippage %</label>
            <input className="t-input" type="number" value={slippage} onChange={e => setSlippage(Number(e.target.value))} min={0} step={0.01} />
          </div>
          <div>
            <label style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-sub)', display: 'block', marginBottom: 3 }}>Latency (candles)</label>
            <input className="t-input" type="number" value={latency} onChange={e => setLatency(Number(e.target.value))} min={0} max={5} />
          </div>
          <div>
            <label style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-sub)', display: 'block', marginBottom: 3 }}>Partial fill %</label>
            <input className="t-input" type="number" value={partialFill} onChange={e => setPartialFill(Number(e.target.value))} min={0} max={100} />
          </div>
          <div>
            <label style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-sub)', display: 'block', marginBottom: 3 }}>Risk checks</label>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, height: 28 }}>
              <button className={`t-chip ${riskEnabled ? 'active' : ''}`} onClick={() => setRiskEnabled(!riskEnabled)} style={{ fontSize: 10 }}>
                {riskEnabled ? 'ON' : 'OFF'}
              </button>
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'flex-end' }}>
            <button className="t-btn t-btn-primary" onClick={handleRun} disabled={running} style={{ width: '100%', height: 28 }}>
              {running ? 'Running…' : 'Run Backtest'}
            </button>
          </div>
        </div>
        <div style={{ marginTop: 8, fontSize: 10, color: 'var(--text-faint)' }}>
          {source === 'builder' ? `Running DSL strategy "${selectedBuilderName}" via the GraphStrategy runtime — same code path as paper/live deployment.` : 'Built-in strategy path. Use Builder source to backtest DSL strategies and deploy them to paper with one click.'}
        </div>
      </div>

      {error && (
        <div style={{ background: 'color-mix(in srgb, var(--red) 8%, transparent)', border: '1px solid color-mix(in srgb, var(--red) 15%, transparent)', borderRadius: 'var(--radius-md)', padding: '8px 12px', color: 'var(--text-red)', fontSize: 12 }}>{error}</div>
      )}

      {s && (
        <>
          <div className="t-tabs">
            {tabs.map(tab => (
              <button key={tab} className={`t-tab ${activeTab === tab ? 'active' : ''}`} onClick={() => setActiveTab(tab)}>
                {tab === 'overview' ? 'Overview'
                  : tab === 'optimizer' ? 'Optimizer'
                  : tab === 'compare' ? 'Compare Runs'
                  : tab === 'report' ? 'Report'
                  : tab === 'risk' ? `Risk (${risk?.rejected_trades ?? 0})`
                  : `Trades (${s.total_trades})`}
              </button>
            ))}
          </div>

          {activeTab === 'overview' && (
            <>
              {/* KPI grid */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: 8 }}>
                {kpiCard('Net P&L (after costs)', fmtMoney(s.net_pnl), `${s.total_trades} trades`, s.net_pnl >= 0 ? 'var(--text-green)' : 'var(--text-red)')}
                {kpiCard('Return', `${s.return_pct >= 0 ? '+' : ''}${fmt(s.return_pct)}%`, `from ₹${Math.round(s.start_equity).toLocaleString('en-IN')}`)}
                {kpiCard('Win Rate', `${fmt(s.win_rate, 1)}%`, `${s.winning_trades}W / ${s.losing_trades}L`, s.win_rate >= 50 ? 'var(--text-green)' : 'var(--text-red)')}
                {kpiCard('Profit Factor', fmt(s.profit_factor), s.profit_factor >= 1.5 ? 'Healthy' : s.profit_factor >= 1 ? 'Positive' : 'Below 1', s.profit_factor >= 1 ? 'var(--text-green)' : 'var(--text-red)')}
                {kpiCard('Expectancy', fmtMoney(s.expectancy), `${fmt(s.expectancy_per_r)}R per trade`, s.expectancy >= 0 ? 'var(--text-green)' : 'var(--text-red)')}
                {kpiCard('Sharpe', fmt(s.sharpe_ratio), s.sharpe_ratio >= 1 ? 'Good' : 'Below threshold', s.sharpe_ratio >= 1 ? 'var(--text-green)' : 'var(--amber)')}
                {kpiCard('Sortino', fmt(s.sortino_ratio), 'downside-adjusted')}
                {kpiCard('Calmar', fmt(s.calmar_ratio), 'return / max DD')}
                {kpiCard('Max Drawdown', `-${fmt(s.max_drawdown_pct)}%`, `peak-to-trough`, 'var(--text-red)')}
                {kpiCard('Alpha (252d)', `${s.alpha >= 0 ? '+' : ''}${fmt(s.alpha)}%`, `vs ${s.benchmark_return_pct >= 0 ? '+' : ''}${fmt(s.benchmark_return_pct)}% benchmark`, s.alpha >= 0 ? 'var(--text-green)' : 'var(--text-red)')}
                {kpiCard('Beta (252d)', fmt(s.beta), s.beta <= 1 ? 'Lower vol than market' : 'Higher vol than market')}
                {kpiCard('Avg / Med RR', `${fmt(s.avg_risk_reward_ratio)} / ${fmt(s.median_risk_reward_ratio)}`, 'risk-reward per trade')}
                {kpiCard('Candles', (s.candles_analyzed || 0).toLocaleString(), `${result!.config.symbol} ${result!.config.interval}`)}
                {kpiCard('Final Equity', fmtMoney(s.end_equity), `+${fmt(s.return_pct)}%`) }
              </div>

              {/* Equity + Drawdown */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                <div className="t-panel" style={{ padding: 12 }}>
                  <div style={{ fontSize: 10, color: 'var(--text-faint)', marginBottom: 4, fontWeight: 700 }}>Equity Curve</div>
                  <BacktestChart points={equityPoints} height={170} color={s.net_pnl >= 0 ? colorVar('--green') : colorVar('--red')} trades={result.trades} onSelectTrade={(idx) => { setSelectedIdx(idx); setActiveTab('trades') }} />
                  <div style={{ fontSize: 9, color: 'var(--text-faint)', marginTop: 4 }}>Click an E/X marker to inspect that trade</div>
                </div>
                <div className="t-panel" style={{ padding: 12 }}>
                  <div style={{ fontSize: 10, color: 'var(--text-faint)', marginBottom: 4, fontWeight: 700 }}>Drawdown %</div>
                  <BacktestChart points={drawdownSeries} height={170} color={colorVar('--red')} mode="drawdown" />
                </div>
              </div>

              {/* Distributions */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                <div className="t-panel" style={{ padding: 12 }}>
                  <div style={{ fontSize: 10, color: 'var(--text-faint)', marginBottom: 4, fontWeight: 700 }}>By Weekday</div>
                  <BarChart data={weekdayBars} height={110} />
                </div>
                <div className="t-panel" style={{ padding: 12 }}>
                  <div style={{ fontSize: 10, color: 'var(--text-faint)', marginBottom: 4, fontWeight: 700 }}>By Hour (IST)</div>
                  <BarChart data={hourBars} height={110} />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                <div className="t-panel" style={{ padding: 12 }}>
                  <div style={{ fontSize: 10, color: 'var(--text-faint)', marginBottom: 4, fontWeight: 700 }}>P&L by Month (₹)</div>
                  <BarChart data={monthBars} height={110} />
                </div>
                <div className="t-panel" style={{ padding: 12 }}>
                  <Heatmap data={result?.weekday_distribution || {}} title="Weekday × Hour P&L Heatmap" />
                </div>
              </div>

              {/* Export + Deploy */}
              <div className="t-panel" style={{ padding: 12, display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                <span style={{ fontSize: 10, color: 'var(--text-faint)', fontWeight: 700 }}>Export run</span>
                <button className="t-btn t-btn-sm" onClick={() => handleExport('json')} disabled={exporting !== null}>{exporting === 'json' ? '…' : 'JSON'}</button>
                <button className="t-btn t-btn-sm" onClick={() => handleExport('csv')} disabled={exporting !== null}>{exporting === 'csv' ? '…' : 'CSV'}</button>
                <button className="t-btn t-btn-sm" onClick={() => handleExport('pdf')} disabled={exporting !== null}>{exporting === 'pdf' ? '…' : 'PDF report'}</button>
                <div style={{ width: 1, height: 20, background: 'var(--border)' }} />
                {result?.strategy_id ? (
                  <>
                    <button className="t-btn t-btn-sm t-btn-primary" onClick={handleDeployToPaper} disabled={deploying}>
                      {deploying ? 'Deploying…' : 'Deploy to Paper'}
                    </button>
                    <span style={{ fontSize: 10, color: deployMsg && !deployMsg.includes('Error') ? 'var(--text-green)' : 'var(--text-red)' }}>
                      {deployMsg}
                    </span>
                  </>
                ) : (
                  <span style={{ fontSize: 10, color: 'var(--text-faint)' }}>Deploy-to-paper available for builder (DSL) runs only</span>
                )}
              </div>
            </>
          )}

          {activeTab === 'optimizer' && (
            <div className="t-panel" style={{ padding: 12 }}>
              <div style={{ marginBottom: 8 }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text)' }}>Parameter Optimizer</div>
                <div style={{ fontSize: 10, color: 'var(--text-faint)', marginTop: 2 }}>
                  Grid (≤512 combos), walk-forward (train prior folds), Monte Carlo (2000 bootstrap paths) and OFAT ±20% sensitivity on the server.
                </div>
              </div>
              <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end', marginBottom: 10, flexWrap: 'wrap' }}>
                <div>
                  <label style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-sub)', display: 'block', marginBottom: 3 }}>Method</label>
                  <select className="t-select" value={optMethod} onChange={e => setOptMethod(e.target.value)} style={{ width: 140 }}>
                    <option value="grid">Grid search</option>
                    <option value="walk_forward">Walk-forward</option>
                    <option value="monte_carlo">Monte Carlo</option>
                    <option value="sensitivity">Sensitivity (OFAT)</option>
                  </select>
                </div>
                <div>
                  <label style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-sub)', display: 'block', marginBottom: 3 }}>Optimize metric</label>
                  <select className="t-select" value={optMetric} onChange={e => setOptMetric(e.target.value)} style={{ width: 150 }}>
                    <option value="sharpe_ratio">Sharpe</option>
                    <option value="net_pnl">Net P&L</option>
                    <option value="return_pct">Return %</option>
                    <option value="win_rate">Win rate</option>
                    <option value="profit_factor">Profit factor</option>
                    <option value="sortino_ratio">Sortino</option>
                    <option value="calmar_ratio">Calmar</option>
                    <option value="max_drawdown_pct">Max DD (min)</option>
                  </select>
                </div>
                <div style={{ flex: 1, minWidth: 220 }}>
                  <label style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-sub)', display: 'block', marginBottom: 3 }}>Param ranges (one per line: param=v1,v2,…)</label>
                  <textarea className="t-input" value={optParamsText} onChange={e => setOptParamsText(e.target.value)}
                    style={{ minHeight: 46, fontFamily: 'var(--font-mono)', fontSize: 11, resize: 'vertical' }} />
                </div>
                <button className="t-btn t-btn-primary" onClick={handleRunOptimize} disabled={optRunning}>
                  {optRunning ? 'Optimizing…' : 'Optimize'}
                </button>
              </div>
              {optError && <div style={{ color: 'var(--text-red)', fontSize: 11, marginBottom: 8 }}>{optError}</div>}

              {optResult && (
                <>
                  <div style={{ display: 'flex', gap: 14, fontSize: 10, color: 'var(--text-faint)', marginBottom: 8, flexWrap: 'wrap' }}>
                    <span>status: <strong>{optResult.status}</strong></span>
                    <span>method: <strong>{optResult.method}</strong></span>
                    <span>combos: <strong>{optResult.combos_completed}/{optResult.combos_total}</strong></span>
                    {bestCombo && (
                      <span style={{ color: 'var(--text-green)' }}>
                        best: {Object.entries(bestCombo.params).map(([k, v]) => `${k}=${v}`).join(', ')}
                      </span>
                    )}
                  </div>
                  {optResult.error && <div style={{ color: 'var(--text-red)', fontSize: 11, marginBottom: 8 }}>{optResult.error}</div>}
                  {optResult.results.length > 0 && (
                    <div style={{ overflowX: 'auto' }}>
                      <table className="t-table">
                        <thead>
                          <tr>
                            <th>Params</th>
                            <th className="num">Net P&L</th>
                            <th className="num">Return %</th>
                            <th className="num">Win %</th>
                            <th className="num">PF</th>
                            <th className="num">Sharpe</th>
                            <th className="num">Sortino</th>
                            <th className="num">Max DD %</th>
                            <th className="num">Trades</th>
                          </tr>
                        </thead>
                        <tbody>
                          {optResult.results.map((c, idx) => {
                            const isBest = bestCombo === c
                            return (
                              <tr key={idx} style={isBest ? { background: 'color-mix(in srgb, var(--cyan) 4%, transparent)' } : {}}>
                                <td style={{ fontWeight: 700, fontSize: 11 }}>
                                  {Object.entries(c.params).map(([k, v]) => `${k}=${v}`).join(' ')}
                                  {isBest && <span style={{ color: 'var(--cyan)' }}> ✓</span>}
                                </td>
                                <td className={`num ${(c.metrics?.net_pnl ?? 0) >= 0 ? 't-up' : 't-down'}`}>{fmtMoney(c.metrics?.net_pnl)}</td>
                                <td className="num">{fmt(c.metrics?.return_pct)}%</td>
                                <td className="num">{fmt(c.metrics?.win_rate, 1)}%</td>
                                <td className="num">{fmt(c.metrics?.profit_factor)}</td>
                                <td className="num" style={{ color: (c.metrics?.sharpe_ratio ?? 0) >= 1 ? 'var(--text-green)' : 'var(--amber)' }}>{fmt(c.metrics?.sharpe_ratio)}</td>
                                <td className="num">{fmt(c.metrics?.sortino_ratio)}</td>
                                <td className="num t-down">-{fmt(c.metrics?.max_drawdown_pct)}%</td>
                                <td className="num">{Math.round(c.metrics?.total_trades ?? 0)}</td>
                              </tr>
                            )
                          })}
                        </tbody>
                      </table>
                    </div>
                  )}
                </>
              )}
            </div>
          )}

          {activeTab === 'compare' && (
            <div className="t-panel" style={{ padding: 12 }}>
              <div style={{ marginBottom: 8 }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text)' }}>Compare Runs</div>
                <div style={{ fontSize: 10, color: 'var(--text-faint)', marginTop: 2 }}>
                  Compare up to 10 saved runs by run ID (comma-separated). The current run is {result.run_id}.
                </div>
              </div>
              <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end', marginBottom: 8, flexWrap: 'wrap' }}>
                <div style={{ flex: 1, minWidth: 220 }}>
                  <label style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-sub)', display: 'block', marginBottom: 3 }}>Run IDs</label>
                  <input className="t-input" value={compareIdsText} onChange={e => setCompareIdsText(e.target.value)}
                    placeholder={`${result.run_id}, <another run id>`} style={{ width: '100%' }} />
                </div>
                <button className="t-btn t-btn-primary" onClick={handleCompare} disabled={compareRunning}>
                  {compareRunning ? 'Comparing…' : 'Compare'}
                </button>
              </div>
              {compareError && <div style={{ color: 'var(--text-red)', fontSize: 11, marginBottom: 8 }}>{compareError}</div>}

              {comparison && Object.keys(comparison).length > 0 && (
                <div style={{ overflowX: 'auto' }}>
                  <table className="t-table">
                    <thead>
                      <tr>
                        <th>Metric</th>
                        {Object.keys(comparison).map(id => <th key={id} style={{ textAlign: 'right', fontFamily: 'var(--font-mono)', fontSize: 10 }}>{id.slice(0, 8)}</th>)}
                      </tr>
                    </thead>
                    <tbody>
                      {([
                        ['total_trades', (v: any) => String(Math.round(v))],
                        ['net_pnl', (v: any) => fmtMoney(v)],
                        ['return_pct', (v: any) => `${v >= 0 ? '+' : ''}${fmt(v)}%`],
                        ['win_rate', (v: any) => `${fmt(v, 1)}%`],
                        ['profit_factor', (v: any) => fmt(v)],
                        ['max_drawdown_pct', (v: any) => `-${fmt(v)}%`],
                        ['sharpe_ratio', (v: any) => fmt(v)],
                        ['sortino_ratio', (v: any) => fmt(v)],
                        ['expectancy', (v: any) => fmtMoney(v)],
                        ['alpha', (v: any) => `${v >= 0 ? '+' : ''}${fmt(v)}%`],
                        ['beta', (v: any) => fmt(v)],
                      ] as [string, (v: any) => string][]).map(([key, render]) => (
                        <tr key={key}>
                          <td style={{ fontWeight: 700, fontSize: 11 }}>{key.replace(/_/g, ' ')}</td>
                          {Object.entries(comparison).map(([id, row]) => {
                            const v = (row as Record<string, unknown>)[key] as number
                            const isPnl = key === 'net_pnl'
                            return (
                              <td key={id} className="t-num" style={{
                                color: isPnl ? (v >= 0 ? 'var(--text-green)' : 'var(--text-red)') : 'var(--text)',
                                fontSize: 11,
                              }}>{render(v)}</td>
                            )
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {comparison && Object.keys(comparison).length === 0 && (
                <p style={{ fontSize: 11, color: 'var(--text-faint)', margin: 0 }}>No matching runs found for the given IDs.</p>
              )}
            </div>
          )}

          {activeTab === 'report' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div className="t-panel" style={{ padding: 10, display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text)' }}>Professional Report</div>
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                  <button className="t-btn t-btn-sm" onClick={() => handleExport('pdf')} disabled={exporting !== null}>{exporting === 'pdf' ? '…' : 'Download PDF'}</button>
                  <button className="t-btn t-btn-sm" onClick={handleOpenReport}>Interactive Report ↗</button>
                  <button className="t-btn t-btn-sm" onClick={handleShare} disabled={sharing}>{sharing ? 'Linking…' : shareLink ? 'Share link copied' : 'Copy Share Link'}</button>
                  <button className="t-btn t-btn-sm" onClick={() => window.print()}>Print</button>
                </div>
              </div>
              {shareErr && (
                <div style={{ background: 'color-mix(in srgb, var(--red) 8%, transparent)', border: '1px solid color-mix(in srgb, var(--red) 15%, transparent)', borderRadius: 'var(--radius-md)', padding: '8px 12px', color: 'var(--text-red)', fontSize: 12 }}>{shareErr}</div>
              )}

              {execSummary && (
                <div className="t-panel" style={{ padding: 12 }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-sub)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 8 }}>Executive Summary</div>
                  <p style={{ fontSize: 12.5, lineHeight: 1.65, color: 'var(--text)', margin: 0 }}>
                    {execSummary.parts.join(' ')}{' '}
                    <span style={{ fontWeight: 700, color: execSummary.color }}>Verdict: the strategy is {execSummary.verdict} over this window.</span>
                  </p>
                </div>
              )}

              {factSheet.length > 0 && (
                <div className="t-panel" style={{ padding: 12 }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-sub)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 8 }}>Strategy Fact Sheet</div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: '4px 18px' }}>
                    {factSheet.map(([label, value]) => (
                      <div key={label} style={{ display: 'flex', justifyContent: 'space-between', gap: 12, padding: '5px 0', borderBottom: '1px dashed var(--border)', fontSize: 12 }}>
                        <span style={{ color: 'var(--text-faint)' }}>{label}</span>
                        <span style={{ fontWeight: 600, color: 'var(--text)', fontFamily: 'var(--font-mono)', fontSize: 11, overflowWrap: 'anywhere', textAlign: 'right' }}>{value}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="t-panel" style={{ padding: 12 }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-sub)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 4 }}>Compare Report</div>
                <div style={{ fontSize: 10, color: 'var(--text-faint)', marginBottom: 8 }}>
                  Side-by-side report against up to 10 saved runs (comma-separated). Current run: {result.run_id}.
                </div>
                <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end', marginBottom: 8, flexWrap: 'wrap' }}>
                  <div style={{ flex: 1, minWidth: 220 }}>
                    <label style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-sub)', display: 'block', marginBottom: 3 }}>Run IDs</label>
                    <input className="t-input" value={compareIdsText} onChange={e => setCompareIdsText(e.target.value)}
                      placeholder={`${result.run_id}, <another run id>`} style={{ width: '100%' }} />
                  </div>
                  <button className="t-btn t-btn-sm t-btn-primary" onClick={handleCompare} disabled={compareRunning}>
                    {compareRunning ? 'Comparing…' : 'Compare'}
                  </button>
                </div>
                {compareError && <div style={{ color: 'var(--text-red)', fontSize: 11, marginBottom: 8 }}>{compareError}</div>}
                {comparison && Object.keys(comparison).length > 0 && (
                  <div style={{ overflowX: 'auto' }}>
                    <table className="t-table">
                      <thead>
                        <tr>
                          <th>Metric</th>
                          {Object.keys(comparison).map(id => <th key={id} style={{ textAlign: 'right', fontFamily: 'var(--font-mono)', fontSize: 10 }}>{id.slice(0, 8)}</th>)}
                        </tr>
                      </thead>
                      <tbody>
                        {([
                          ['total_trades', (v: any) => String(Math.round(v))],
                          ['net_pnl', (v: any) => fmtMoney(v)],
                          ['return_pct', (v: any) => `${v >= 0 ? '+' : ''}${fmt(v)}%`],
                          ['win_rate', (v: any) => `${fmt(v, 1)}%`],
                          ['profit_factor', (v: any) => fmt(v)],
                          ['max_drawdown_pct', (v: any) => `-${fmt(v)}%`],
                          ['sharpe_ratio', (v: any) => fmt(v)],
                          ['sortino_ratio', (v: any) => fmt(v)],
                          ['expectancy', (v: any) => fmtMoney(v)],
                        ] as [string, (v: any) => string][]).map(([key, render]) => (
                          <tr key={key}>
                            <td style={{ fontWeight: 700, fontSize: 11 }}>{key.replace(/_/g, ' ')}</td>
                            {Object.entries(comparison).map(([id, row]) => {
                              const v = (row as Record<string, unknown>)[key] as number
                              const isPnl = key === 'net_pnl'
                              return (
                                <td key={id} className="t-num" style={{
                                  color: isPnl ? (v >= 0 ? 'var(--text-green)' : 'var(--text-red)') : 'var(--text)',
                                  fontSize: 11,
                                }}>{render(v)}</td>
                              )
                            })}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          )}

          {activeTab === 'trades' && s.total_trades > 0 && (
            <div className="t-panel" style={{ padding: 0 }}>
              <div style={{ padding: '8px 12px', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--text)' }}>Trade Log ({s.total_trades} trades)</span>
                <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
                  <span style={{ fontSize: 10, color: 'var(--text-faint)' }}>costs applied</span>
                  <button className="t-btn t-btn-sm" onClick={() => setSelectedIdx(idx => idx == null ? 0 : Math.max(0, idx - 1))}>← Prev</button>
                  <button className="t-btn t-btn-sm" onClick={() => setSelectedIdx(idx => idx == null ? 0 : Math.min(s.total_trades - 1, idx + 1))}>Next →</button>
                  <button className="t-btn t-btn-sm" onClick={() => setSelectedIdx(jumpTargets.ddIdx >= 0 ? jumpTargets.ddIdx : 0)}>Max Drawdown</button>
                  <button className="t-btn t-btn-sm" onClick={() => setSelectedIdx(jumpTargets.bestIdx >= 0 ? jumpTargets.bestIdx : 0)}>Best</button>
                  <button className="t-btn t-btn-sm" onClick={() => setSelectedIdx(jumpTargets.worstIdx >= 0 ? jumpTargets.worstIdx : 0)}>Worst</button>
                </div>
              </div>
              <div style={{ overflowX: 'auto', maxHeight: 300, overflowY: 'auto' }}>
                <table className="t-table">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Symbol</th>
                      <th>Side</th>
                      <th className="num">Entry</th>
                      <th className="num">Exit</th>
                      <th className="num">Qty</th>
                      <th className="num">P&L</th>
                      <th className="num">RR</th>
                      <th>Entry</th>
                      <th>Exit</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result!.trades.map((t, idx) => (
                      <tr key={idx} onClick={() => setSelectedIdx(idx)}
                        style={{ cursor: 'pointer', ...(selectedIdx === idx ? { background: 'color-mix(in srgb, var(--cyan) 8%, transparent)' } : {}) }}>
                        <td className="t-faint">{idx + 1}</td>
                        <td style={{ fontWeight: 600 }}>{t.symbol}</td>
                        <td><span className={t.side === 'BUY' ? 't-up' : 't-down'} style={{ fontWeight: 600 }}>{t.side}</span></td>
                        <td className="t-num">{t.entry_price.toFixed(1)}</td>
                        <td className="t-num">{t.exit_price.toFixed(1)}</td>
                        <td className="t-num">{t.quantity}</td>
                        <td className={`t-num ${t.pnl >= 0 ? 't-up' : 't-down'}`} style={{ fontWeight: 700 }}>{t.pnl >= 0 ? '+' : ''}{t.pnl.toFixed(0)}</td>
                        <td className="t-num">{t.rr != null ? t.rr.toFixed(2) : '—'}</td>
                        <td className="t-faint" style={{ fontSize: 10 }}>{new Date(t.entry_time).toLocaleString()}</td>
                        <td className="t-faint" style={{ fontSize: 10 }}>{new Date(t.exit_time).toLocaleString()}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {activeTab === 'trades' && selection && (
            <div className="t-panel" style={{ padding: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8, flexWrap: 'wrap', gap: 8 }}>
                <div>
                  <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--text)' }}>Trade Intelligence — {selection.sub}/{selection.total}</span>
                  <span style={{ marginLeft: 8, fontSize: 10, color: 'var(--text-faint)' }}>{selection.symbol} · {selection.side} · {selection.quantity} qty</span>
                </div>
                <div style={{ display: 'flex', gap: 6 }}>
                  <button className="t-btn t-btn-sm t-btn-primary" onClick={() => setReplaying(r => !r)}>
                    {replaying ? '■ Stop' : '▶ Replay from entry'}
                  </button>
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(118px, 1fr))', gap: 8, marginBottom: 8 }}>
                {tiCard('Entry', selection.entryPrice.toFixed(2))}
                {tiCard('Exit', selection.exitPrice.toFixed(2))}
                {tiCard('Qty', String(selection.quantity))}
                {tiCard('P&L', selection.pnlText, selection.pnl >= 0 ? 'var(--text-green)' : 'var(--text-red)')}
                {tiCard('RR', selection.rr ? selection.rr.toFixed(2) : '—')}
                {tiCard('Risk ₹', selection.riskAmount > 0 ? fmtMoney(selection.riskAmount) : '—')}
                {tiCard('Duration', selection.durationMinutes > 60 ? `${Math.floor(selection.durationMinutes / 60)}h ${selection.durationMinutes % 60}m` : `${selection.durationMinutes}m`)}
                {tiCard('Charges', fmtMoney(selection.charges))}
                {tiCard('Taxes', fmtMoney(selection.taxes))}
                {tiCard('Slippage', fmtMoney(selection.slippage))}
                {tiCard('Cost total', fmtMoney(selection.costTotal))}
                <div style={{ gridColumn: 'span 2', background: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', padding: '6px 8px' }}>
                  <div style={{ fontSize: 9, color: 'var(--text-faint)', fontWeight: 700 }}>Signals</div>
                  <div style={{ fontSize: 11, color: 'var(--text)', marginTop: 1, lineHeight: 1.4 }}>
                    {selection.entryReason} <span style={{ color: 'var(--text-faint)' }}>→</span> {selection.exitReason}
                  </div>
                </div>
              </div>

              {candles && candles.length >= 2 ? (
                <>
                  <TradeChart candles={candles} view={selection} replaying={replaying} onReplayEnd={() => setReplaying(false)} />
                  <div style={{ display: 'flex', gap: 14, fontSize: 9, color: 'var(--text-faint)', marginTop: 6, flexWrap: 'wrap' }}>
                    <span style={{ color: colorVar('--green', '#34d399') }}>▲ entry</span>
                    <span style={{ color: colorVar('--red', '#ef4444') }}>▼ exit</span>
                    {selection.sl != null && <span style={{ color: '#f59e0b' }}>-- SL {selection.sl.toFixed(2)} (derived from risk amount)</span>}
                    {selection.target != null && <span style={{ color: '#22d3ee' }}>-- Target {selection.target.toFixed(2)} (exit reason: target)</span>}
                    {selection.sl == null && selection.target == null && <span>no SL/Target on this trade</span>}
                    <span>replay starts from entry candle</span>
                  </div>
                </>
              ) : (
                <div style={{ fontSize: 10, color: 'var(--text-faint)', padding: 8 }}>{candlesErr || 'price chart unavailable'}</div>
              )}
            </div>
          )}

          {activeTab === 'trades' && s.total_trades === 0 && (
            <div className="t-panel" style={{ padding: 24, textAlign: 'center' }}>
              <p style={{ color: 'var(--text-faint)', fontSize: 12, margin: 0 }}>No trades were generated</p>
            </div>
          )}

          {activeTab === 'risk' && risk?.enabled && (
            <>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: 8 }}>
                {kpiCard('Accepted Trades', String(risk.accepted_trades), 'passed all simulated rules')}
                {kpiCard('Rejected Trades', String(risk.rejected_trades), `${riskReasons.length} rule(s) fired`, risk.rejected_trades > 0 ? 'var(--amber)' : 'var(--text)')}
                {kpiCard('Circuit Halts', String(risk.halt_count), risk.halt_count > 0 ? 'trading halted after breach' : 'no daily-loss / drawdown breach', risk.halt_count > 0 ? 'var(--text-red)' : 'var(--text-green)')}
                {kpiCard('Rejection Reasons', String(riskReasons.length), 'distinct rules engaged')}
              </div>

              {riskReasons.length > 0 && (
                <div className="t-panel" style={{ padding: 12 }}>
                  <div style={{ fontSize: 10, color: 'var(--text-faint)', marginBottom: 4, fontWeight: 700 }}>Rejections by Rule</div>
                  <BarChart data={riskReasons} height={120} unit="orders" />
                </div>
              )}

              <div className="t-panel" style={{ padding: 12 }}>
                <div style={{ fontSize: 10, color: 'var(--text-faint)', marginBottom: 4, fontWeight: 700 }}>Risk State Over Time</div>
                <div style={{ display: 'flex', gap: 14, fontSize: 10, color: 'var(--text-faint)', marginBottom: 6, flexWrap: 'wrap' }}>
                  <span style={{ color: colorVar('--green', '#34d399') }}>— capital remaining</span>
                  <span style={{ color: colorVar('--cyan', '#22d3ee') }}>— exposure</span>
                  <span style={{ color: colorVar('--red', '#ef4444') }}>— drawdown %</span>
                </div>
                <RiskChart timeline={risk.timeline} />
              </div>

              {(risk.rejections?.length ?? 0) > 0 && (
                <div className="t-panel" style={{ padding: 0 }}>
                  <div style={{ padding: '8px 12px', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--text)' }}>Rejected Orders ({risk.rejected_trades})</span>
                    <span style={{ fontSize: 10, color: 'var(--text-faint)' }}>
                      {risk.rejections_truncated ? `showing first ${risk.rejections!.length}` : 'all shown'} · newest last
                    </span>
                  </div>
                  <div style={{ overflowX: 'auto', maxHeight: 420, overflowY: 'auto' }}>
                    <table className="t-table">
                      <thead>
                        <tr>
                          <th>Time</th>
                          <th>Symbol</th>
                          <th>Side</th>
                          <th className="num">Qty</th>
                          <th className="num">Price</th>
                          <th>Rule</th>
                          <th>Reason</th>
                          <th className="num">Cap. Rem.</th>
                          <th className="num">Risk Rem.</th>
                          <th className="num">DD %</th>
                          <th className="num">Exposure</th>
                        </tr>
                      </thead>
                      <tbody>
                        {risk.rejections!.map((r, idx) => (
                          <tr key={idx}>
                            <td className="t-faint" style={{ fontSize: 10 }}>
                              {new Date(r.timestamp).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}
                            </td>
                            <td style={{ fontWeight: 600 }}>{r.symbol}</td>
                            <td><span className={r.side === 'BUY' ? 't-up' : 't-down'} style={{ fontWeight: 600 }}>{r.side}</span></td>
                            <td className="t-num">{r.quantity}</td>
                            <td className="t-num">{r.price.toFixed(2)}</td>
                            <td><span className="t-chip active" style={{ fontSize: 9 }}>{r.rule}</span></td>
                            <td style={{ fontSize: 11 }}>{r.reason}</td>
                            <td className="t-num">₹{Math.round(r.capital_remaining).toLocaleString('en-IN')}</td>
                            <td className="t-num">{r.risk_remaining < 0 ? '∞' : `₹${Math.round(r.risk_remaining).toLocaleString('en-IN')}`}</td>
                            <td className="t-num t-down">{r.drawdown.toFixed(2)}%</td>
                            <td className="t-num">₹{Math.round(r.exposure).toLocaleString('en-IN')}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </>
          )}
        </>
      )}

      {!s && !running && !error && (
        <div className="t-panel" style={{ padding: 32, textAlign: 'center' }}>
          <p style={{ color: 'var(--text-faint)', fontSize: 13, margin: '0 0 4px' }}>Configure parameters and run a backtest</p>
          <p style={{ color: 'var(--text-faint)', fontSize: 11, margin: 0 }}>Realistic Indian-market costs · corporate actions · continuous futures · deploy to paper</p>
        </div>
      )}
    </div>
  )
}
