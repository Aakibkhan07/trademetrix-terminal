'use client'

import { useEffect, useMemo, useState } from 'react'
import { api } from '@/lib/api'
import { useMarketData } from '@/lib/use-market-data'
import { useUIStore } from '@/lib/stores/ui-store'

interface ChainRow { strikePrice: number; call?: { ltp: number; oi: number; iv: number }; put?: { ltp: number; oi: number; iv: number } }

interface OptionChainPanelProps {
  symbol: string
  name: string
  onClose: () => void
}

function fmt(n: number | undefined, d = 1) { return n === undefined || n === null ? '—' : n.toLocaleString('en-IN', { maximumFractionDigits: d }) }
function oiFmt(n: number | undefined) { return n === undefined ? '—' : n >= 100000 ? (n / 100000).toFixed(1) + 'L' : n >= 1000 ? (n / 1000).toFixed(0) + 'K' : String(n) }

export default function OptionChainPanel({ symbol, name, onClose }: OptionChainPanelProps) {
  const { ticks, subscribe } = useMarketData()
  const openQuickOrder = useUIStore(s => s.openQuickOrder)
  const [rows, setRows] = useState<ChainRow[]>([])
  const [atm, setAtm] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (symbol) subscribe([symbol])
  }, [subscribe, symbol])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    const sym = symbol.replace(/^NSE:/, '')
    api.marketdata.optionChain(sym).then(d => {
      if (cancelled) return
      const r = ((d as { optionChain?: ChainRow[] }).optionChain || []) as ChainRow[]
      if (r.length) {
        const last = ticks[symbol]?.last_price ?? r[Math.floor(r.length / 2)].strikePrice
        const a = r.reduce((best, row) => Math.abs(row.strikePrice - last) < Math.abs(best - last) ? row.strikePrice : best, r[0].strikePrice)
        setAtm(a)
      } else setAtm(null)
      setRows(r)
      setLoading(false)
    }).catch(() => { if (!cancelled) { setRows([]); setLoading(false) } })
    return () => { cancelled = true }
  }, [symbol, ticks]) // eslint-disable-line

  const view = useMemo(() => {
    if (!rows.length || !atm) return rows
    const idx = rows.findIndex(r => r.strikePrice === atm)
    return rows.slice(Math.max(0, idx - 6), Math.min(rows.length, idx + 7))
  }, [rows, atm])

  const pcr = useMemo(() => {
    if (rows.length < 4) return null
    const c = rows.reduce((a, r) => a + (r.call?.oi || 0), 0)
    const p = rows.reduce((a, r) => a + (r.put?.oi || 0), 0)
    return c > 0 ? (p / c).toFixed(2) : null
  }, [rows])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      <div style={{
        padding: '10px 12px', borderBottom: '1px solid var(--border)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      }}>
        <div>
          <div style={{ fontSize: 13, fontWeight: 800 }}>☰ Option Chain</div>
          <div className="t-faint" style={{ fontSize: 10 }}>{name} · {symbol}{pcr ? ` · PCR ${pcr}` : ''}</div>
        </div>
        <button className="t-btn t-btn-sm t-btn-ghost" onClick={onClose}>✕</button>
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: 8 }}>
        {loading && <span className="t-faint" style={{ fontSize: 11 }}>Loading chain…</span>}
        {!loading && rows.length === 0 && (
          <span className="t-faint" style={{ fontSize: 11 }}>Option chain unavailable for {name}.</span>
        )}
        {rows.length > 0 && (
          <table className="t-table" style={{ width: '100%', minWidth: 0, borderCollapse: 'collapse' }}>
            <thead style={{ position: 'sticky', top: 0, background: 'var(--panel)', zIndex: 2 }}>
              <tr>
                <th style={{ fontSize: 8 }}>CE LTP</th><th style={{ fontSize: 8 }}>CE OI</th>
                <th style={{ fontSize: 8 }}>STRIKE</th>
                <th style={{ fontSize: 8 }}>PE OI</th><th style={{ fontSize: 8 }}>PE LTP</th>
              </tr>
            </thead>
            <tbody>
              {view.map(r => {
                const isAtm = r.strikePrice === atm
                const ltp = ticks[symbol]?.last_price
                const itmCe = ltp ? r.strikePrice <= ltp : false
                const itmPe = ltp ? r.strikePrice >= ltp : false
                return (
                  <tr key={r.strikePrice} style={{ background: isAtm ? 'rgba(34,211,238,.07)' : undefined }}>
                    <td>
                      <span className="t-num" style={{ fontSize: 10, color: itmCe ? 'var(--green)' : undefined }}>{fmt(r.call?.ltp)}</span>
                      <button className="t-btn t-btn-xs t-btn-ghost" title="Buy CE" style={{ marginLeft: 4, padding: 0, fontSize: 10, color: 'var(--green)' }}
                        onClick={() => openQuickOrder(symbol, name, 'BUY')}>B</button>
                    </td>
                    <td><span className="t-num t-faint" style={{ fontSize: 9 }}>{oiFmt(r.call?.oi)}</span></td>
                    <td style={{ textAlign: 'center' }}>
                      <span className={`t-num ${isAtm ? 't-up' : ''}`} style={{ fontSize: 10, fontWeight: 800 }}>{r.strikePrice}</span>
                    </td>
                    <td><span className="t-num t-faint" style={{ fontSize: 9 }}>{oiFmt(r.put?.oi)}</span></td>
                    <td>
                      <span className="t-num" style={{ fontSize: 10, color: itmPe ? 'var(--red)' : undefined }}>{fmt(r.put?.ltp)}</span>
                      <button className="t-btn t-btn-xs t-btn-ghost" title="Sell PE" style={{ marginLeft: 4, padding: 0, fontSize: 10, color: 'var(--red)' }}
                        onClick={() => openQuickOrder(symbol, name, 'SELL')}>S</button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
        <div className="t-faint" style={{ fontSize: 9, marginTop: 8, lineHeight: 1.5 }}>
          Buy/Sell on the chain opens the order drawer (strike snapping handled by the engine on execution).
        </div>
      </div>
    </div>
  )
}
