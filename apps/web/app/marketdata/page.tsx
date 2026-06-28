'use client'

import { useEffect, useRef, useState, useCallback } from 'react'
import { api } from '@/lib/api'

interface TickData {
  symbol: string
  last_price: number
  bid: number
  ask: number
  volume: number
  oi: number
  change: number
  change_pct: number
  timestamp: string
}

const WS_BASE = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000/api/v1/marketdata/ws'

const WATCHLIST = ['NIFTY', 'BANKNIFTY', 'RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'ICICIBANK', 'SBIN', 'BHARTIARTL', 'KOTAKBANK']

const DEMO_TICKS: TickData[] = [
  { symbol: 'NIFTY', last_price: 24582.30, bid: 24581.50, ask: 24583.10, volume: 1254300, oi: 0, change: 291.35, change_pct: 1.20, timestamp: new Date().toISOString() },
  { symbol: 'BANKNIFTY', last_price: 52148.75, bid: 52147.00, ask: 52150.50, volume: 892100, oi: 0, change: -156.45, change_pct: -0.30, timestamp: new Date().toISOString() },
  { symbol: 'RELIANCE', last_price: 2856.40, bid: 2856.00, ask: 2856.80, volume: 345200, oi: 52100, change: 42.60, change_pct: 1.51, timestamp: new Date().toISOString() },
  { symbol: 'TCS', last_price: 4123.75, bid: 4123.00, ask: 4124.50, volume: 187600, oi: 31200, change: -18.25, change_pct: -0.44, timestamp: new Date().toISOString() },
  { symbol: 'HDFCBANK', last_price: 1682.30, bid: 1682.00, ask: 1682.60, volume: 423100, oi: 78400, change: 23.50, change_pct: 1.42, timestamp: new Date().toISOString() },
  { symbol: 'INFY', last_price: 1567.85, bid: 1567.50, ask: 1568.20, volume: 234500, oi: 45600, change: -8.90, change_pct: -0.56, timestamp: new Date().toISOString() },
  { symbol: 'ICICIBANK', last_price: 1234.50, bid: 1234.20, ask: 1234.80, volume: 312400, oi: 62300, change: 15.30, change_pct: 1.25, timestamp: new Date().toISOString() },
  { symbol: 'SBIN', last_price: 845.60, bid: 845.30, ask: 845.90, volume: 567800, oi: 89100, change: 5.20, change_pct: 0.62, timestamp: new Date().toISOString() },
  { symbol: 'BHARTIARTL', last_price: 1456.20, bid: 1455.90, ask: 1456.50, volume: 178900, oi: 23400, change: -12.40, change_pct: -0.84, timestamp: new Date().toISOString() },
  { symbol: 'KOTAKBANK', last_price: 1892.40, bid: 1892.00, ask: 1892.80, volume: 156700, oi: 34500, change: 28.60, change_pct: 1.53, timestamp: new Date().toISOString() },
]

export default function MarketDataPage() {
  const [ticks, setTicks] = useState<Map<string, TickData>>(new Map())
  const [connected, setConnected] = useState(false)
  const [simRunning, setSimRunning] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    const map = new Map<string, TickData>()
    DEMO_TICKS.forEach(t => map.set(t.symbol, t))
    setTicks(map)
  }, [])

  const getWsUrl = () => {
    const token = localStorage.getItem('trademetrix_token')
    return token ? `${WS_BASE}?access_token=${token}` : WS_BASE
  }

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return
    const ws = new WebSocket(getWsUrl())
    wsRef.current = ws

    ws.onopen = () => {
      setConnected(true)
      ws.send(JSON.stringify({ action: 'subscribe', symbols: WATCHLIST }))
    }

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data)
      if (msg.type === 'tick') {
        const prev = ticks.get(msg.symbol)
        const change = msg.last_price - (prev?.last_price || msg.last_price)
        const changePct = prev?.last_price ? (change / prev.last_price) * 100 : 0
        setTicks((prevMap) => {
          const next = new Map(prevMap)
          next.set(msg.symbol, { ...msg, change, change_pct: changePct })
          return next
        })
      }
    }

    ws.onclose = () => {
      setConnected(false)
      wsRef.current = null
    }

    ws.onerror = () => setConnected(false)
  }, [])

  const disconnect = useCallback(() => {
    wsRef.current?.close()
    wsRef.current = null
    setConnected(false)
  }, [])

  useEffect(() => {
    return () => disconnect()
  }, [disconnect])

  const startSim = async () => {
    try {
      await api.post('/marketdata/simulator/start')
      setSimRunning(true)
    } catch { /* ignore */ }
  }

  const stopSim = async () => {
    try {
      await api.post('/marketdata/simulator/stop')
      setSimRunning(false)
    } catch { /* ignore */ }
  }

  const tickList = Array.from(ticks.values()).sort((a, b) => a.symbol.localeCompare(b.symbol))

  const gainers = [...tickList].sort((a, b) => b.change_pct - a.change_pct).slice(0, 3)
  const losers = [...tickList].sort((a, b) => a.change_pct - b.change_pct).slice(0, 3)

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24, flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h1 style={{ fontFamily: 'Outfit', fontSize: 24, margin: 0 }}>Market Data</h1>
          <p style={{ color: '#8888a0', fontSize: 14, margin: '4px 0 0' }}>
            Real-time and simulated market data feed
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12, color: connected ? '#22c55e' : '#8888a0' }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: connected ? '#22c55e' : '#8888a0', boxShadow: connected ? '0 0 6px #22c55e' : 'none' }} />
            {connected ? 'Live' : 'Demo'}
          </span>
          {connected ? (
            <button className="btn btn-sm btn-danger" onClick={disconnect}>Disconnect</button>
          ) : (
            <button className="btn btn-sm btn-cyan" onClick={connect}>Connect Live</button>
          )}
          <button className={`btn btn-sm ${simRunning ? 'btn-danger' : 'btn-secondary'}`} onClick={simRunning ? stopSim : startSim}>
            {simRunning ? 'Stop Sim' : 'Start Sim'}
          </button>
        </div>
      </div>

      <div className="grid-3" style={{ marginBottom: 20 }}>
        <div className="glass-card" style={{ padding: '14px' }}>
          <p style={{ color: '#555570', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.08em', margin: '0 0 8px', fontWeight: 600 }}>Top Gainers</p>
          {gainers.map((t) => (
            <div key={t.symbol} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', fontSize: 12 }}>
              <span style={{ fontWeight: 600 }}>{t.symbol}</span>
              <span style={{ color: '#22c55e' }}>+{t.change_pct.toFixed(2)}%</span>
            </div>
          ))}
        </div>
        <div className="glass-card" style={{ padding: '14px' }}>
          <p style={{ color: '#555570', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.08em', margin: '0 0 8px', fontWeight: 600 }}>Top Losers</p>
          {losers.map((t) => (
            <div key={t.symbol} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', fontSize: 12 }}>
              <span style={{ fontWeight: 600 }}>{t.symbol}</span>
              <span style={{ color: '#ef4444' }}>{t.change_pct.toFixed(2)}%</span>
            </div>
          ))}
        </div>
        <div className="glass-card" style={{ padding: '14px' }}>
          <p style={{ color: '#555570', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.08em', margin: '0 0 8px', fontWeight: 600 }}>Market Summary</p>
          <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', fontSize: 12 }}>
            <span style={{ color: '#555570' }}>Advancers</span>
            <span style={{ color: '#22c55e', fontWeight: 600 }}>6</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', fontSize: 12 }}>
            <span style={{ color: '#555570' }}>Decliners</span>
            <span style={{ color: '#ef4444', fontWeight: 600 }}>4</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', fontSize: 12 }}>
            <span style={{ color: '#555570' }}>Unchanged</span>
            <span style={{ fontWeight: 600 }}>0</span>
          </div>
        </div>
      </div>

      <div className="panel" style={{ padding: 0 }}>
        <div style={{ borderBottom: '1px solid rgba(139,92,246,0.06)', padding: '14px 18px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3 className="panel-title" style={{ fontSize: 14, margin: 0 }}>Live Ticker</h3>
          <span style={{ fontSize: 11, color: '#555570' }}>{tickList.length} symbols</span>
        </div>
        <div style={{ overflowX: 'auto' }}>
          <table className="data-table">
            <thead>
              <tr>
                <th style={{ padding: '10px 14px' }}>Symbol</th>
                <th style={{ padding: '10px 14px' }}>LTP</th>
                <th style={{ padding: '10px 14px' }}>Change</th>
                <th style={{ padding: '10px 14px' }}>Change %</th>
                <th style={{ padding: '10px 14px' }}>Bid</th>
                <th style={{ padding: '10px 14px' }}>Ask</th>
                <th style={{ padding: '10px 14px' }}>Volume</th>
                <th style={{ padding: '10px 14px' }}>OI</th>
              </tr>
            </thead>
            <tbody>
              {tickList.map((t) => (
                <tr key={t.symbol}>
                  <td style={{ fontWeight: 600, padding: '10px 14px' }}>{t.symbol}</td>
                  <td className="numeric" style={{ fontWeight: 600, padding: '10px 14px' }}>{t.last_price.toFixed(2)}</td>
                  <td className="numeric" style={{ color: t.change >= 0 ? '#22c55e' : '#ef4444', padding: '10px 14px' }}>
                    {t.change >= 0 ? '+' : ''}{t.change.toFixed(2)}
                  </td>
                  <td className="numeric" style={{ color: t.change_pct >= 0 ? '#22c55e' : '#ef4444', padding: '10px 14px' }}>
                    {t.change_pct >= 0 ? '+' : ''}{t.change_pct.toFixed(2)}%
                  </td>
                  <td className="numeric" style={{ padding: '10px 14px' }}>{t.bid.toFixed(2)}</td>
                  <td className="numeric" style={{ padding: '10px 14px' }}>{t.ask.toFixed(2)}</td>
                  <td className="numeric" style={{ padding: '10px 14px' }}>{t.volume.toLocaleString()}</td>
                  <td className="numeric" style={{ padding: '10px 14px' }}>{t.oi.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div style={{ marginTop: 16 }}>
        <div className="glass-card" style={{ padding: '14px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ color: '#555570', fontSize: 12 }}>Watchlist</span>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {WATCHLIST.map((s) => {
                const tick = ticks.get(s)
                return (
                  <span key={s} className={`badge ${tick && tick.change >= 0 ? 'badge-green' : 'badge-red'}`} style={{ fontSize: 10, padding: '3px 8px', cursor: 'pointer' }}>
                    {s} {tick ? tick.last_price.toFixed(0) : ''}
                  </span>
                )
              })}
            </div>
          </div>
          <span style={{ fontSize: 10, color: '#555570' }}>
            {connected ? 'Live feed' : 'Demo data'} · {tickList.filter(t => t.change >= 0).length}↑ {tickList.filter(t => t.change < 0).length}↓
          </span>
        </div>
      </div>
    </div>
  )
}
