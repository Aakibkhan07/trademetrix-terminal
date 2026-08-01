'use client'

import { useEffect, useRef, useState } from 'react'
import { useOrders, usePositions, useRuns } from '@/lib/queries/orders'
import { useBrokerCredentials } from '@/lib/queries/misc'
import { useMarketData } from '@/lib/use-market-data'

export interface WSEvent {
  id: string
  kind: string
  text: string
  at: number
  tone?: 'up' | 'down' | 'warn'
  seen?: boolean
}

const EVENTS_KEY = 'tm_ws_events'
const MAX_EVENTS = 60

function loadEvents(): WSEvent[] {
  try { return JSON.parse(localStorage.getItem(EVENTS_KEY) || '[]') } catch { return [] }
}

const ICONS: Record<string, string> = {
  order: '📦', alert: '🔔', broker: '🔌', market: '🕐', risk: '🛡️', strategy: '🤖', position: '📊',
}

export default function NotificationsPopover() {
  const { data: ordersData } = useOrders()
  const { data: positionsData } = usePositions()
  const { data: credsData } = useBrokerCredentials()
  const { data: runsData } = useRuns()
  const { connected } = useMarketData()
  const [events, setEvents] = useState<WSEvent[]>([])
  const [open, setOpen] = useState(false)
  const eventsRef = useRef<WSEvent[]>([])
  const boxRef = useRef<HTMLDivElement>(null)
  const marketStateRef = useRef<string>('')
  const brokerStateRef = useRef<string>('')
  const posRef = useRef<Record<string, number>>({})
  const runRef = useRef<Record<string, string>>({})

  useEffect(() => {
    const loaded = loadEvents()
    eventsRef.current = loaded
    setEvents(loaded)
  }, [])

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [])

  const push = (e: Omit<WSEvent, 'at'>) => {
    const current = eventsRef.current
    if (current.some(p => p.id === e.id)) return
    const next = [{ ...e, at: Date.now(), seen: false }, ...current].slice(0, MAX_EVENTS)
    eventsRef.current = next
    localStorage.setItem(EVENTS_KEY, JSON.stringify(next))
    setEvents(next)
  }

  const orders = (ordersData as { orders?: any[] } | undefined)?.orders || []
  useEffect(() => {
    const seen = new Set(loadEvents().map(e => e.id))
    for (const o of orders) {
      if (o.status === 'FILLED' && !seen.has(`of-${o.id}`)) {
        push({ id: `of-${o.id}`, kind: 'order', text: `${o.side} ${o.quantity} ${o.symbol} filled${o.is_paper ? ' (paper)' : ''}`, tone: 'up' })
      }
      if (o.status === 'REJECTED' && !seen.has(`or-${o.id}`)) {
        push({ id: `or-${o.id}`, kind: 'order', text: `${o.side} ${o.symbol} rejected${o.reason ? `: ${o.reason}` : ''}`, tone: 'down' })
      }
    }
  }, [orders]) // eslint-disable-line

  const positions = (positionsData as { positions?: { symbol: string; quantity: number }[] } | undefined)?.positions || []
  useEffect(() => {
    const now = Object.fromEntries(positions.map(p => [p.symbol, p.quantity]))
    for (const [sym, qty] of Object.entries(posRef.current)) {
      if (qty !== 0 && (now[sym] === undefined || now[sym] === 0)) {
        push({ id: `pc-${sym}-${Date.now()}`, kind: 'position', text: `Position closed: ${sym}`, tone: 'warn' })
      }
    }
    posRef.current = now
  }, [positions]) // eslint-disable-line

  const credentials = (credsData as { credentials?: { broker: string; is_active: boolean; token_status: string }[] } | undefined)?.credentials || []
  const activeCred = credentials.find(c => c.is_active)
  useEffect(() => {
    const st = activeCred ? `${activeCred.broker}:${activeCred.token_status}` : 'none'
    if (brokerStateRef.current && brokerStateRef.current.includes('valid') && st.includes('invalid')) {
      push({ id: 'br-conn', kind: 'broker', text: `Broker disconnected — ${activeCred?.broker} token invalid, re-auth needed`, tone: 'down' })
    }
    if (brokerStateRef.current && st === 'none' && brokerStateRef.current !== 'none') {
      push({ id: 'br-none', kind: 'broker', text: 'Broker credentials removed', tone: 'warn' })
    }
    brokerStateRef.current = st
  }, [activeCred]) // eslint-disable-line

  useEffect(() => {
    if (!connected && !marketStateRef.current.includes('offline')) {
      marketStateRef.current = 'offline'
      push({ id: 'mk-offline', kind: 'market', text: 'Market feed disconnected', tone: 'down' })
    } else if (connected && marketStateRef.current.includes('offline')) {
      marketStateRef.current = 'online'
      push({ id: 'mk-online', kind: 'market', text: 'Market feed reconnected', tone: 'up' })
    }
  }, [connected]) // eslint-disable-line

  const runs = (runsData as { runs?: { run_id?: string; strategy?: string; status?: string }[] } | undefined)?.runs || []
  useEffect(() => {
    for (const r of runs) {
      const key = r.run_id || `${r.strategy || ''}-${r.status || ''}`
      const st = `${key}:${r.status}`
      if (runRef.current[key] && runRef.current[key] !== r.status) {
        if (r.status === 'running' || r.status === 'active') {
          push({ id: `rs-${key}-run`, kind: 'strategy', text: `Strategy started: ${r.strategy || key}`, tone: 'up' })
        } else if (r.status === 'stopped' || r.status === 'error' || r.status === 'completed') {
          push({ id: `rs-${key}-stop`, kind: 'strategy', text: `Strategy ${r.status}: ${r.strategy || key}`, tone: 'warn' })
        }
      }
      runRef.current[key] = r.status || 'unknown'
    }
  }, [runs]) // eslint-disable-line

  const unread = events.filter(e => !e.seen).length

  const markAll = () => {
    const next = loadEvents().map(e => ({ ...e, seen: true }))
    localStorage.setItem(EVENTS_KEY, JSON.stringify(next))
    eventsRef.current = next
    setEvents(next)
  }

  return (
    <div ref={boxRef} style={{ position: 'relative' }}>
      <button
        className="t-btn t-btn-sm t-btn-ghost"
        title="Notifications"
        style={{ position: 'relative', fontSize: 15 }}
        onClick={() => setOpen(o => !o)}
      >
        🔔
        {unread > 0 && (
          <span style={{
            position: 'absolute', top: -2, right: -2, background: 'var(--red)', color: '#fff',
            fontSize: 9, fontWeight: 800, borderRadius: 10, minWidth: 16, height: 16,
            display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '0 3px',
          }}>{unread > 9 ? '9+' : unread}</span>
        )}
      </button>
      {open && (
        <div style={{
          position: 'absolute', top: 36, right: 0, width: 340, zIndex: 96,
          background: 'var(--panel)', border: '1px solid var(--border-hi)', borderRadius: 12,
          boxShadow: '0 12px 40px rgba(0,0,0,.55)', padding: 8, maxHeight: 420, overflowY: 'auto',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '4px 6px 8px' }}>
            <span className="t-stat-label" style={{ fontSize: 9 }}>NOTIFICATIONS</span>
            <button className="t-btn t-btn-xs t-btn-ghost" onClick={markAll}>Mark all read</button>
          </div>
          {events.length === 0 && <span className="t-faint" style={{ fontSize: 11, padding: 8 }}>No events yet.</span>}
          {events.slice(0, 30).map(e => (
            <div key={`${e.id}-${e.at}`} style={{
              display: 'flex', gap: 8, padding: '7px 8px', borderRadius: 8, fontSize: 11, alignItems: 'flex-start',
              opacity: e.seen ? .55 : 1, background: e.seen ? 'transparent' : 'rgba(139,92,246,.07)',
            }}>
              <span style={{ fontSize: 13 }}>{ICONS[e.kind] || '•'}</span>
              <div style={{ minWidth: 0 }}>
                <div style={{ lineHeight: 1.4, color: e.tone === 'down' ? 'var(--red)' : e.tone === 'up' ? 'var(--green)' : 'var(--text)' }}>{e.text}</div>
                <div className="t-faint" style={{ fontSize: 9, marginTop: 2 }}>{new Date(e.at).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })}</div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
