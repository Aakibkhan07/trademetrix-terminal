'use client'

import { useState, useEffect, useRef } from 'react'

interface Broker { broker: string; active: boolean }
interface UserWithBroker { id: string; email: string; full_name: string; brokers: Broker[]; has_broker: boolean }

const LOT_SIZES: Record<string, number> = {
  NIFTY: 65, BANKNIFTY: 30, FINNIFTY: 60,
  SENSEX: 20, MIDCPNIFTY: 75,
}

export function TradeRouterTab() {
  const [users, setUsers] = useState<UserWithBroker[]>([])
  const [selectedUser, setSelectedUser] = useState('')
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<any[]>([])
  const [searching, setSearching] = useState(false)
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const [lots, setLots] = useState(1)
  const [lotSize, setLotSize] = useState(1)
  const [placing, setPlacing] = useState<string | null>(null)
  const [resultMsg, setResultMsg] = useState<{ success: boolean; message: string } | null>(null)
  const searchRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    fetch('/api/v1/admin/users/with-brokers').then(r => r.json()).then(d => setUsers(d.users || [])).catch(() => {})
  }, [])

  const [chainCache, setChainCache] = useState<Record<string, { expiry: string; chain: any[] }>>({})

  useEffect(() => {
    const indices = ['NIFTY', 'BANKNIFTY', 'FINNIFTY']
    indices.forEach(async sym => {
      try {
        const r = await fetch(`/api/v1/market/option-chain?symbol=${encodeURIComponent(sym)}`)
        const d = await r.json()
        const raw = d.data?.optionChain || []
        if (raw.length) {
          const expiry = d.expiry || d.expiries?.[0] || ''
          setChainCache(prev => ({ ...prev, [sym]: { expiry, chain: raw } }))
        }
      } catch {}
    })
  }, [])

  useEffect(() => {
    if (query.length < 1) { setResults([]); setDropdownOpen(false); return }
    const t = setTimeout(async () => {
      const isNum = /^\d+$/.test(query.trim())
      if (isNum) {
        const num = parseInt(query)
        const out: any[] = []
        for (const [sym, cache] of Object.entries(chainCache)) {
          const match = cache.chain.find((r: any) => (r.strikePrice || r.strike) === num)
          if (match) {
            const s = match.strikePrice || match.strike
            const ls = LOT_SIZES[sym] || 1
            const cePrice = match.call?.ltp || 0
            const pePrice = match.put?.ltp || 0
            const ceChg = match.call?.change_pct
            const peChg = match.put?.change_pct
            out.push({ type: 'strike', symbol: sym, strike: s, ce: cePrice, pe: pePrice, ceChg, peChg, lotSize: ls, expiry: cache.expiry })
          }
        }
        setResults(out)
        setDropdownOpen(out.length > 0)
      } else {
        setSearching(true)
        try {
          const r = await fetch(`/api/v1/marketdata/instruments?query=${encodeURIComponent(query)}&limit=8`)
          const d = await r.json()
          setResults(d.instruments || [])
          setDropdownOpen(true)
        } catch {}
        setSearching(false)
      }
    }, 200)
    return () => clearTimeout(t)
  }, [query, chainCache])

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (searchRef.current && !searchRef.current.contains(e.target as Node)) setDropdownOpen(false)
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  const buyStrike = async (symbol: string, strike: number, optionType: string, ls: number, expiry: string) => {
    if (!selectedUser) { setResultMsg({ success: false, message: 'Select a user first' }); return }
    const key = `${symbol}-${strike}-${optionType}`
    setPlacing(key)
    setResultMsg(null)
    try {
      const r = await fetch('/api/v1/admin/execute-trade', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: selectedUser, symbol, side: 'BUY', quantity: lots * ls,
          exchange: 'NFO', instrument_type: 'OPT', option_type: optionType,
          strike_price: strike, expiry_date: expiry.slice(0, 10),
          order_type: 'MARKET', product: 'INTRADAY', price: 0,
        }),
      })
      const d = await r.json()
      setResultMsg({ success: d.result?.success || d.success || false, message: d.result?.message || d.message || (r.ok ? 'Sent' : d.detail || 'Failed') })
    } catch (e) { setResultMsg({ success: false, message: String(e) }) }
    setPlacing(null)
  }

  return (
    <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
      <div style={{ flex: '1 1 560px', minWidth: 380 }}>
        <div className="t-panel" style={{ padding: 12, marginBottom: 12 }}>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            <select className="t-input" value={selectedUser} onChange={e => setSelectedUser(e.target.value)}
              style={{ fontSize: 12, flex: '1 1 200px' }}>
              <option value="">— Select User —</option>
              {users.filter(u => u.has_broker).map(u => (
                <option key={u.id} value={u.id}>{u.full_name || u.email}</option>
              ))}
            </select>
            <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <button onClick={() => setLots(Math.max(1, lots - 1))} style={{ padding: '2px 8px', fontSize: 13, border: '1px solid var(--border)', borderRadius: 3, background: 'var(--bg-tertiary)', cursor: 'pointer', color: 'var(--text)', lineHeight: 1 }}>−</button>
              <span style={{ fontSize: 12, fontWeight: 700, padding: '0 6px' }}>{lots}</span>
              <button onClick={() => setLots(lots + 1)} style={{ padding: '2px 8px', fontSize: 13, border: '1px solid var(--border)', borderRadius: 3, background: 'var(--bg-tertiary)', cursor: 'pointer', color: 'var(--text)', lineHeight: 1 }}>+</button>
              {results.find((r: any) => r.type === 'strike') && <span style={{ fontSize: 9, color: 'var(--text-faint)' }}>lot × {lotSize}</span>}
            </div>
          </div>
        </div>

        <div className="t-panel" style={{ padding: 12 }} ref={searchRef}>
          <div style={{ position: 'relative' }}>
            <input className="t-input" value={query} onChange={e => { setQuery(e.target.value); setLotSize(1) }}
              placeholder="Search symbol or strike (e.g. 24200, NIFTY, RELIANCE)..."
              style={{ width: '100%', fontSize: 14, padding: '10px 12px' }} />
            {searching && <span style={{ position: 'absolute', right: 12, top: 12, fontSize: 10, color: 'var(--text-faint)' }}>searching...</span>}
            {dropdownOpen && results.length > 0 && (
              <div style={{
                position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 100,
                background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: '0 0 8px 8px',
                maxHeight: 360, overflowY: 'auto', boxShadow: '0 4px 24px rgba(0,0,0,0.35)',
              }}>
                {results[0]?.type === 'strike' ? results.map((r: any, i: number) => (
                  <div key={i} style={{ padding: '10px 14px', borderBottom: '1px solid color-mix(in srgb, var(--border) 30%, transparent)', display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                    <strong style={{ fontSize: 14, minWidth: 80 }}>{r.symbol}</strong>
                    <span style={{ fontSize: 13, fontWeight: 600, minWidth: 60 }}>{r.strike}</span>
                    <span style={{ fontSize: 11, color: 'var(--text-faint)', minWidth: 70 }}>Exp: {r.expiry?.slice(0, 10)}</span>
                    <span style={{ fontSize: 13, color: 'var(--green)', fontWeight: 700, minWidth: 100 }}>CE: {r.ce != null ? r.ce : '—'} {r.ceChg != null ? <span style={{ fontSize: 10, color: r.ceChg >= 0 ? 'var(--green)' : 'var(--red)' }}>({r.ceChg >= 0 ? '+' : ''}{r.ceChg}%)</span> : ''}</span>
                    <span style={{ fontSize: 13, color: 'var(--red)', fontWeight: 700, minWidth: 100 }}>PE: {r.pe != null ? r.pe : '—'} {r.peChg != null ? <span style={{ fontSize: 10, color: r.peChg >= 0 ? 'var(--green)' : 'var(--red)' }}>({r.peChg >= 0 ? '+' : ''}{r.peChg}%)</span> : ''}</span>
                    <button onClick={() => { setLotSize(r.lotSize); buyStrike(r.symbol, r.strike, 'CE', r.lotSize, r.expiry) }}
                      disabled={placing !== null || !r.ce}
                      style={{ padding: '4px 10px', fontSize: 9, fontWeight: 700, borderRadius: 3, border: 'none', cursor: placing ? 'wait' : r.ce ? 'pointer' : 'default', background: 'color-mix(in srgb, var(--green) 12%, transparent)', color: 'var(--green)' }}>
                      {placing === `${r.symbol}-${r.strike}-CE` ? '...' : 'CE Buy'}
                    </button>
                    <button onClick={() => { setLotSize(r.lotSize); buyStrike(r.symbol, r.strike, 'PE', r.lotSize, r.expiry) }}
                      disabled={placing !== null || !r.pe}
                      style={{ padding: '4px 10px', fontSize: 9, fontWeight: 700, borderRadius: 3, border: 'none', cursor: placing ? 'wait' : r.pe ? 'pointer' : 'default', background: 'color-mix(in srgb, var(--red) 12%, transparent)', color: 'var(--red)' }}>
                      {placing === `${r.symbol}-${r.strike}-PE` ? '...' : 'PE Buy'}
                    </button>
                  </div>
                )) : results.map((s: any, i: number) => (
                  <div key={i} onClick={() => { setQuery(s.symbol || s.name || ''); setDropdownOpen(false) }}
                    style={{ padding: '10px 14px', cursor: 'pointer', fontSize: 13, borderBottom: '1px solid color-mix(in srgb, var(--border) 30%, transparent)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
                    onMouseEnter={e => (e.currentTarget.style.background = 'color-mix(in srgb, var(--violet) 6%, var(--bg))')}
                    onMouseLeave={e => (e.currentTarget.style.background = '')}>
                    <span><strong>{s.symbol || s.name || ''}</strong></span>
                    <span style={{ fontSize: 10, color: 'var(--text-faint)' }}>{s.exchange || ''} {s.instrument_type || ''}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {resultMsg && (
            <div style={{ padding: 10, marginTop: 12 }}>
              <p style={{ margin: 0, fontSize: 12, fontWeight: 600, color: resultMsg.success ? 'var(--green)' : 'var(--red)' }}>
                {resultMsg.success ? '✓ ' : '✗ '}{resultMsg.message}
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
