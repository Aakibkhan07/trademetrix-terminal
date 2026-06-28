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

export default function MarketDataPage() {
  const [ticks, setTicks] = useState<Map<string, TickData>>(new Map())
  const [connected, setConnected] = useState(false)
  const [simRunning, setSimRunning] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)

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
        setTicks((prev) => {
          const next = new Map(prev)
          next.set(msg.symbol, { ...msg, change, change_pct: changePct })
          return next
        })
      }
    }

    ws.onclose = () => {
      setConnected(false)
      wsRef.current = null
    }

    ws.onerror = () => {
      setConnected(false)
    }
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

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <div>
          <h1 style={{ fontFamily: 'Outfit', fontSize: 24, margin: 0 }}>Market Data</h1>
          <p style={{ color: '#8888a0', fontSize: 14, margin: '4px 0 0' }}>
            Real-time live ticker feed
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <span style={{
            display: 'inline-flex', alignItems: 'center', gap: 6,
            fontSize: 12, color: connected ? '#22c55e' : '#ef4444',
          }}>
            <span style={{
              width: 8, height: 8, borderRadius: '50%',
              background: connected ? '#22c55e' : '#ef4444',
              boxShadow: connected ? '0 0 6px #22c55e' : '0 0 6px #ef4444',
            }} />
            {connected ? 'Connected' : 'Disconnected'}
          </span>
          {connected ? (
            <button className="btn btn-sm btn-danger" onClick={disconnect}>Disconnect</button>
          ) : (
            <button className="btn btn-sm btn-cyan" onClick={connect}>Connect</button>
          )}
          <button
            className={`btn btn-sm ${simRunning ? 'btn-danger' : 'btn-secondary'}`}
            onClick={simRunning ? stopSim : startSim}
          >
            {simRunning ? 'Stop Simulator' : 'Start Simulator'}
          </button>
        </div>
      </div>

      <div className="panel">
        <div style={{ overflowX: 'auto' }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>LTP</th>
                <th>Change</th>
                <th>Change %</th>
                <th>Bid</th>
                <th>Ask</th>
                <th>Volume</th>
                <th>OI</th>
                <th>Time</th>
              </tr>
            </thead>
            <tbody>
              {tickList.length === 0 ? (
                <tr>
                  <td colSpan={9} style={{ textAlign: 'center', color: '#555570', padding: 32 }}>
                    {connected ? 'Waiting for ticks...' : 'Connect to start receiving live market data'}
                  </td>
                </tr>
              ) : (
                tickList.map((t) => (
                  <tr key={t.symbol}>
                    <td style={{ fontWeight: 600, color: '#8b5cf6' }}>{t.symbol}</td>
                    <td className="numeric neon-cyan">{t.last_price.toFixed(2)}</td>
                    <td className="numeric" style={{ color: t.change >= 0 ? '#22c55e' : '#ef4444' }}>
                      {t.change >= 0 ? '+' : ''}{t.change.toFixed(2)}
                    </td>
                    <td className="numeric" style={{ color: t.change_pct >= 0 ? '#22c55e' : '#ef4444' }}>
                      {t.change_pct >= 0 ? '+' : ''}{t.change_pct.toFixed(2)}%
                    </td>
                    <td className="numeric">{t.bid.toFixed(2)}</td>
                    <td className="numeric">{t.ask.toFixed(2)}</td>
                    <td className="numeric">{t.volume.toLocaleString()}</td>
                    <td className="numeric">{t.oi.toLocaleString()}</td>
                    <td style={{ fontSize: 12, color: '#555570' }}>
                      {new Date(t.timestamp).toLocaleTimeString()}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div style={{ marginTop: 16 }}>
        <div className="glass-card" style={{ padding: 16 }}>
          <p style={{ color: '#8888a0', fontSize: 12, margin: '0 0 8px' }}>Watchlist</p>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {WATCHLIST.map((s) => (
              <span
                key={s}
                className="badge badge-violet"
                style={{ cursor: 'pointer' }}
                onClick={() => {
                  if (connected) {
                    wsRef.current?.send(JSON.stringify({ action: 'subscribe', symbols: [s] }))
                  }
                }}
              >
                {s}
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
