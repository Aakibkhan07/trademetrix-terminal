'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { useUIStore } from '@/lib/stores/ui-store'
import { useMarketData } from '@/lib/use-market-data'

interface Hit {
  kind: string
  label: string
  sub: string
  icon: string
  run: () => void
}

export default function CommandPalette({ onOpenAlert }: { onOpenAlert: (symbol: string, name: string) => void }) {
  const { setActiveSymbol, pushRecent, recentSymbols } = useUIStore()
  const { subscribe } = useMarketData()
  const qc = useQueryClient()
  const [query, setQuery] = useState('')
  const [idx, setIdx] = useState(0)
  const [focused, setFocused] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const [catalog, setCatalog] = useState<{ symbol: string; name: string; instrument_type: string }[]>([])
  const [strategies, setStrategies] = useState<{ key?: string; id?: string; name: string }[]>([])
  const [alerts, setAlerts] = useState<{ id: string; symbol: string; target_price: number; note?: string }[]>([])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        inputRef.current?.focus()
      }
      if (e.key === 'Escape' && document.activeElement === inputRef.current) {
        (document.activeElement as HTMLElement).blur()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (inputRef.current && !inputRef.current.contains(e.target as Node)) {
        inputRef.current.blur()
      }
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [])

  const prime = useCallback(() => {
    const positions = (qc.getQueryData(['positions']) as { positions?: { symbol: string; quantity: number }[] } | undefined)?.positions || []
    const orders = (qc.getQueryData(['orders']) as { orders?: { symbol: string }[] } | undefined)?.orders || []
    return { positions, orders }
  }, [qc])

  useEffect(() => {
    api.get<{ results: { symbol: string; name: string; instrument_type: string }[] }>('/market/instruments?query=NIFTY&limit=25')
      .then(d => setCatalog(d.results || [])).catch(() => {})
    api.marketdata.watchlist()
      .then((d: unknown) => {
        const data = d as { indices?: { symbol: string; name: string }[]; stocks?: { symbol: string; name: string }[] }
        const items = [...(data.indices || []), ...(data.stocks || [])]
        setCatalog(prev => {
          const seen = new Set(prev.map(c => c.symbol))
          return [...prev, ...items.filter(i => i.symbol && !seen.has(i.symbol)).map(i => ({ symbol: i.symbol, name: i.name, instrument_type: i.symbol.includes('INDEX') ? 'index' : 'stock' }))]
        })
      }).catch(() => {})
    api.strategies.list().then(d => {
      const arr = (d as { strategies?: { key?: string; id?: string; name: string }[] })?.strategies || []
      setStrategies(arr.map(s => ({ key: s.key || s.id, name: s.name })))
    }).catch(() => {})
    api.alerts.list().then(d => setAlerts((d as { alerts?: any[] }).alerts || [])).catch(() => {})
  }, [])

  const buildHits = useCallback(() => {
    const { positions, orders } = prime()
    const q = query.trim().toLowerCase()
    const out: Hit[] = []
    const seen = new Set<string>()

    const pushSym = (symbol: string, name: string, kind: string) => {
      const full = symbol.includes(':') ? symbol : `NSE:${symbol}`
      const key = full.toLowerCase()
      if (!q || key.includes(q) || name.toLowerCase().includes(q)) {
        if (seen.has(key)) return
        seen.add(key)
        out.push({
          kind, label: name, sub: full,
          icon: '📈',
          run: () => {
            setActiveSymbol(full, name)
            pushRecent(full, name)
            subscribe([full])
            setQuery('')
          },
        })
      }
    }

    const pushThing = (key: string, kind: string, label: string, sub: string, icon: string, run: () => void) => {
      const k = key.toLowerCase()
      if (!q || label.toLowerCase().includes(q) || sub.toLowerCase().includes(q)) {
        if (seen.has(k)) return
        seen.add(k)
        out.push({ kind, label, sub, icon, run })
      }
    }

    recentSymbols.slice(0, 6).forEach(r => pushSym(r.symbol, r.name, 'RECENT'))
    catalog.slice(0, 20).forEach(c => pushSym(c.symbol, c.name, 'SYMBOL'))
    positions.slice(0, 10).forEach(p => pushSym(p.symbol, p.symbol, 'POSITION'))
    orders.slice(0, 10).forEach(o => pushSym(o.symbol, o.symbol, 'ORDER'))
    alerts.slice(0, 10).forEach(a => pushThing(`al-${a.id}`, 'ALERT', a.note || a.symbol, `${a.symbol} · ${a.target_price}`, '🔔', () => {
      const name = a.note || a.symbol
      setActiveSymbol(a.symbol, name)
      pushRecent(a.symbol, name)
      onOpenAlert(a.symbol, name)
      setQuery('')
    }))
    strategies.slice(0, 8).forEach(s => pushThing(`st-${s.key || s.id}`, 'STRATEGY', s.name, 'strategy', '🤖', () => {
      window.location.assign(`/strategies/${s.key || s.id}`)
    }))
    pushThing('act-watchlist', 'ACTION', 'Open watchlist', 'workspace', '📋', () => setQuery(''))
    return out
  }, [query, prime, catalog, recentSymbols, alerts, strategies, setActiveSymbol, pushRecent, subscribe, onOpenAlert])

  const hits = useMemo(() => buildHits(), [buildHits])

  useEffect(() => {
    setIdx(0)
  }, [query])

  const grouped = useMemo(() => {
    const order = ['RECENT', 'SYMBOL', 'POSITION', 'ORDER', 'ALERT', 'STRATEGY', 'ACTION']
    return order.map(k => ({ kind: k, items: hits.filter(h => h.kind === k) })).filter(g => g.items.length)
  }, [hits])

  const flat = useMemo(() => grouped.flatMap(g => g.items), [grouped])
  const selected = flat[Math.min(idx, flat.length - 1)]

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setIdx(i => Math.min(flat.length - 1, i + 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setIdx(i => Math.max(0, i - 1)) }
    else if (e.key === 'Enter' && selected) { selected.run(); inputRef.current?.blur() }
    else if (e.key === 'Escape') { inputRef.current?.blur() }
  }

  return (
    <div style={{ position: 'relative', flex: 1, maxWidth: 340 }}>
      <button
        className="t-input"
        onClick={() => inputRef.current?.focus()}
        style={{ textAlign: 'left', color: 'var(--text-faint)', cursor: 'text', display: 'flex', alignItems: 'center', gap: 8, height: 28, width: '100%', paddingLeft: 9 }}
      >
        <span style={{ fontSize: 12 }}>🔍</span>
        <span style={{ fontSize: 11 }}>Search symbols, strategies, orders…</span>
        <span className="t-chip" style={{ marginLeft: 'auto', fontSize: 9, padding: '0 6px' }}>⌘K</span>
      </button>
      <input
        ref={inputRef}
        value={query}
        onChange={e => setQuery(e.target.value)}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        onKeyDown={onKeyDown}
        placeholder=""
        style={{ position: 'absolute', inset: 0, opacity: 0, width: '100%', height: '100%', border: 'none', background: 'transparent', outline: 'none', cursor: 'text' }}
        aria-label="Universal search"
      />
      {focused && flat.length > 0 && (
        <div onMouseDown={e => e.preventDefault()} style={{
          position: 'absolute', top: 34, left: 0, right: 0, zIndex: 95,
          background: 'var(--panel)', border: '1px solid var(--border-hi)', borderRadius: 10,
          boxShadow: '0 10px 36px rgba(0,0,0,.5)', padding: 6, maxHeight: 380, overflowY: 'auto',
        }}>
          {grouped.map(g => (
            <div key={g.kind}>
              <div className="t-stat-label" style={{ fontSize: 8, padding: '6px 8px 2px' }}>{g.kind}</div>
              {g.items.map((h, i) => {
                const gi = flat.indexOf(h)
                return (
                  <div
                    key={`${g.kind}-${h.sub}-${i}`}
                    onMouseEnter={() => setIdx(gi)}
                    onClick={() => { h.run(); inputRef.current?.blur() }}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 8, padding: '6px 10px', borderRadius: 7, cursor: 'pointer', fontSize: 12,
                      background: gi === idx ? 'rgba(139,92,246,.16)' : 'transparent',
                    }}
                  >
                    <span>{h.icon}</span>
                    <span style={{ fontWeight: 600 }}>{h.label}</span>
                    <span className="t-faint" style={{ fontSize: 10, marginLeft: 'auto', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 140 }}>{h.sub}</span>
                  </div>
                )
              })}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
