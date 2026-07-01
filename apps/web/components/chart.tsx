'use client'

import { useEffect, useRef, useState, useCallback } from 'react'
import { createChart, ColorType, CandlestickSeries, HistogramSeries, type IChartApi, type ISeriesApi, type CandlestickData, type Time } from 'lightweight-charts'
import { api } from '@/lib/api'

interface ChartProps {
  symbol: string
  height?: number
}

type Interval = '5m' | '15m' | '1h' | '1d'

const INTERVALS: Interval[] = ['5m', '15m', '1h', '1d']

export default function Chart({ symbol, height = 400 }: ChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null)
  const [interval, setInterval_] = useState<Interval>('15m')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const loadData = useCallback(async () => {
    if (!chartRef.current) return
    setLoading(true)
    setError('')
    try {
      const rawSymbol = symbol.replace(/^NSE:/, '')
      const data = await api.marketdata.historical(rawSymbol, interval, interval === '1d' ? 90 : 7)
      const candles = (data as any).candles || []
      if (!candles.length) {
        setError('No data available')
        setLoading(false)
        return
      }
      const cd: CandlestickData[] = []
      const vd: { time: Time; value: number; color: string }[] = []
      for (const c of candles) {
        const t = (new Date(c.timestamp).getTime() / 1000) as Time
        cd.push({ time: t, open: c.open, high: c.high, low: c.low, close: c.close })
        vd.push({
          time: t,
          value: c.volume,
          color: c.close >= c.open ? 'rgba(52,211,153,0.3)' : 'rgba(248,113,113,0.3)',
        })
      }
      candleSeriesRef.current?.setData(cd)
      volumeSeriesRef.current?.setData(vd)
      chartRef.current?.timeScale().fitContent()
    } catch {
      setError('Failed to load chart data')
    }
    setLoading(false)
  }, [symbol, interval])

  useEffect(() => {
    if (!containerRef.current) return
    const chart = createChart(containerRef.current, {
      height,
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: '#6b6e78',
        fontSize: 10,
        fontFamily: "'DM Sans', system-ui, sans-serif",
      },
      grid: {
        vertLines: { color: 'rgba(139,92,246,0.06)' },
        horzLines: { color: 'rgba(139,92,246,0.06)' },
      },
      crosshair: {
        vertLine: { color: 'rgba(139,92,246,0.3)', width: 1, style: 2, labelBackgroundColor: '#0c0e12' },
        horzLine: { color: 'rgba(139,92,246,0.3)', width: 1, style: 2, labelBackgroundColor: '#0c0e12' },
      },
      timeScale: {
        borderColor: 'rgba(255,255,255,0.06)',
        timeVisible: true,
        secondsVisible: false,
      },
      rightPriceScale: { borderColor: 'rgba(255,255,255,0.06)' },
    })

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#34d399',
      downColor: '#f87171',
      borderUpColor: '#34d399',
      borderDownColor: '#f87171',
      wickUpColor: '#34d399',
      wickDownColor: '#f87171',
    })

    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
    })

    chart.priceScale('volume').applyOptions({
      scaleMargins: { top: 0.85, bottom: 0 },
    })

    chartRef.current = chart
    candleSeriesRef.current = candleSeries
    volumeSeriesRef.current = volumeSeries

    return () => {
      chart.remove()
      chartRef.current = null
      candleSeriesRef.current = null
      volumeSeriesRef.current = null
    }
  }, [height])

  useEffect(() => {
    if (chartRef.current) loadData()
  }, [loadData])

  return (
    <div className="chart-container" style={{ marginBottom: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <div className="chart-controls">
          {INTERVALS.map(i => (
            <button
              key={i}
              className={`chart-btn ${interval === i ? 'active' : ''}`}
              onClick={() => setInterval_(i)}
            >
              {i}
            </button>
          ))}
        </div>
        {loading && <span style={{ fontSize: 11, color: 'var(--text-faint)' }}>Loading...</span>}
      </div>
      {error && (
        <p style={{ color: 'var(--red)', fontSize: 12, margin: '0 0 8px' }}>{error}</p>
      )}
      <div ref={containerRef} />
    </div>
  )
}
