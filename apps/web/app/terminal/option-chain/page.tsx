'use client'

import { useEffect, useState, useCallback, useRef } from 'react'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'
import { SkeletonTable } from '@/components/skeleton'
import { EmptyState } from '@/components/empty-state'
import { ErrorMessage } from '@/components/error-message'

/* ─── Types ─── */

interface OptionSide {
  ltp: number
  change: number
  change_pct: number
  bid: number
  ask: number
  volume: number
  oi: number
  iv: number
}

interface OptionRow {
  strike: number
  call: OptionSide
  put: OptionSide
}

interface OiChange {
  strike: number
  call_oi_change: number
  put_oi_change: number
}

interface ChainResponse {
  symbol: string
  expiry: string
  expiries: string[]
  pcr: number
  max_pain: number
  is_simulated?: boolean
  data: {
    optionChain: OptionRow[]
    expiries: string[]
  }
}

/* ─── Constants ─── */

const SYMBOLS = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'SENSEX']
const POLL_INTERVAL = 30000

function fmt(n: number) {
  return n.toLocaleString('en-IN', { maximumFractionDigits: 2 })
}

function fmtInt(n: number) {
  return n >= 100000
    ? (n / 100000).toFixed(1) + 'L'
    : n >= 1000
      ? (n / 1000).toFixed(0) + 'K'
      : String(n)
}

function pcrZone(pcr: number): { label: string; color: string } {
  if (pcr < 0.5) return { label: 'Deep Bearish', color: 'var(--text-red)' }
  if (pcr < 0.8) return { label: 'Bearish', color: '#ff6d00' }
  if (pcr < 1.2) return { label: 'Neutral', color: 'var(--amber)' }
  if (pcr < 1.5) return { label: 'Bullish', color: '#69f0ae' }
  return { label: 'Deep Bullish', color: 'var(--text-green)' }
}

function changeClass(v: number) {
  return v > 0 ? 't-up' : v < 0 ? 't-down' : ''
}

function buildupColor(oiChange: number, priceChange: number): string {
  if (oiChange > 0 && priceChange > 0) return 'var(--text-green)'
  if (oiChange > 0 && priceChange < 0) return 'var(--text-red)'
  if (oiChange < 0 && priceChange < 0) return 'var(--text-green)'
  if (oiChange < 0 && priceChange > 0) return 'var(--text-red)'
  return ''
}

/* ─── Component ─── */

export default function OptionChainPage() {
  const { user } = useAuth()

  const [symbol, setSymbol] = useState('NIFTY')
  const [expiry, setExpiry] = useState('')
  const [expiries, setExpiries] = useState<string[]>([])
  const [rows, setRows] = useState<OptionRow[]>([])
  const [pcr, setPcr] = useState(0)
  const [maxPain, setMaxPain] = useState(0)
  const [isSimulated, setIsSimulated] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [lastUpdated, setLastUpdated] = useState('')
  const [oiChanges, setOiChanges] = useState<Map<number, OiChange>>(new Map())

  const prevRowsRef = useRef<OptionRow[]>([])

  const loadChain = useCallback(async (sym: string, exp: string) => {
    setError('')
    try {
      const d = await api.market.optionChain(sym, exp) as ChainResponse
      const chain = d.data?.optionChain || []
      const exps = d.expiries || d.data?.expiries || []
      setRows(chain)
      setExpiries(exps)
      setPcr(d.pcr ?? 0)
      setMaxPain(d.max_pain ?? 0)
      setIsSimulated(d.is_simulated ?? false)
      if (exp && !exps.includes(exp)) setExpiry('')
      else if (!exp && exps.length) setExpiry(d.expiry || exps[0])
      setLastUpdated(new Date().toLocaleTimeString('en-IN'))

      const prev = prevRowsRef.current
      if (prev.length) {
        const prevMap = new Map(prev.map(r => [r.strike, r]))
        const changes: OiChange[] = []
        for (const row of chain) {
          const prevRow = prevMap.get(row.strike)
          if (prevRow) {
            changes.push({
              strike: row.strike,
              call_oi_change: row.call.oi - prevRow.call.oi,
              put_oi_change: row.put.oi - prevRow.put.oi,
            })
          }
        }
        setOiChanges(new Map(changes.map(c => [c.strike, c])))
      }
      prevRowsRef.current = chain
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    setLoading(true)
    loadChain(symbol, expiry)
    const timer = setInterval(() => loadChain(symbol, expiry), POLL_INTERVAL)
    return () => clearInterval(timer)
  }, [symbol, expiry, loadChain])

  const atmx = rows.length ? rows.reduce((a, b) => Math.abs(a.strike) < Math.abs(b.strike) ? a : b) : null

  if (!user) return null

  if (loading && !rows.length) {
    return (
      <div style={{ padding: 16 }}>
        <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} style={{ width: 80, height: 28, borderRadius: 6, background: 'var(--border)', animation: 'pulse 1.5s infinite' }} />
          ))}
        </div>
        <SkeletonTable rows={8} />
      </div>
    )
  }

  if (error && !rows.length) {
    return (
      <div style={{ padding: 16 }}>
        <ErrorMessage message={error} onRetry={() => { setLoading(true); loadChain(symbol, expiry) }} />
      </div>
    )
  }

  if (!loading && !rows.length) {
    return (
      <div style={{ padding: 16 }}>
        <EmptyState title="No option chain data" description={`No data available for ${symbol}. Try a different symbol.`} />
      </div>
    )
  }

  return (
    <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
      {/* ── Header Controls ── */}
      <div className="t-panel" style={{ padding: '10px 14px', display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <select className="t-select" value={symbol} onChange={e => { setSymbol(e.target.value); setLoading(true) }}
          style={{ width: 130, padding: '4px 8px', borderRadius: 6, border: '1px solid var(--border)', background: 'var(--bg-tertiary)', color: 'var(--text)', fontSize: 12, fontFamily: 'var(--font-mono)' }}>
          {SYMBOLS.map(s => <option key={s} value={s}>{s}</option>)}
        </select>

        <select className="t-select" value={expiry} onChange={e => { setExpiry(e.target.value); setLoading(true) }}
          style={{ width: 100, padding: '4px 8px', borderRadius: 6, border: '1px solid var(--border)', background: 'var(--bg-tertiary)', color: 'var(--text)', fontSize: 12, fontFamily: 'var(--font-mono)' }}>
          {expiries.map(e => <option key={e} value={e}>{e}</option>)}
        </select>

        <span style={{ fontSize: 10, color: 'var(--text-faint)', fontFamily: 'var(--font-mono)' }}>
          {lastUpdated ? `Updated ${lastUpdated}` : ''}
        </span>

        {loading && <span style={{ fontSize: 10, color: 'var(--cyan)', fontFamily: 'var(--font-mono)' }}>loading...</span>}

        {isSimulated && (
          <span className="t-badge t-badge-amber" style={{ fontSize: 9 }}>
            SIMULATED DATA
          </span>
        )}
      </div>

      {/* ── Analytics Panel ── */}
      <div className="t-panel" style={{ padding: '10px 14px', display: 'flex', gap: 24, flexWrap: 'wrap' }}>
        <div>
          <div className="t-stat-label">PCR (OI)</div>
          <div className="t-stat-value" style={{ color: pcrZone(pcr).color, fontSize: 18 }}>{pcr.toFixed(2)}</div>
          <div className="t-stat-sub" style={{ color: pcrZone(pcr).color }}>{pcrZone(pcr).label}</div>
        </div>
        <div>
          <div className="t-stat-label">Max Pain</div>
          <div className="t-stat-value" style={{ fontSize: 18 }}>{fmt(maxPain)}</div>
          <div className="t-stat-sub t-sub">Max option writer pain</div>
        </div>
        <div>
          <div className="t-stat-label">Call Resistance</div>
          <div className="t-stat-value" style={{ fontSize: 18, color: 'var(--text-red)' }}>
            {(() => {
              const maxCe = [...rows].sort((a, b) => (b.call.oi ?? 0) - (a.call.oi ?? 0))[0]
              return maxCe ? fmt(maxCe.strike) : '-'
            })()}
          </div>
          <div className="t-stat-sub t-sub">Highest CE OI</div>
        </div>
        <div>
          <div className="t-stat-label">Put Support</div>
          <div className="t-stat-value" style={{ fontSize: 18, color: 'var(--text-green)' }}>
            {(() => {
              const maxPe = [...rows].sort((a, b) => (b.put.oi ?? 0) - (a.put.oi ?? 0))[0]
              return maxPe ? fmt(maxPe.strike) : '-'
            })()}
          </div>
          <div className="t-stat-sub t-sub">Highest PE OI</div>
        </div>
      </div>

      {/* ── Chain Table ── */}
      <div style={{ overflowX: 'auto', WebkitOverflowScrolling: 'touch' }}>
        <table className="t-table" style={{ minWidth: 580, fontSize: 11, borderCollapse: 'collapse', width: '100%' }}>
          <thead>
            <tr style={{ borderBottom: '1px solid var(--border)' }}>
              <th colSpan={5} style={{ textAlign: 'center', padding: '6px 4px', color: 'var(--text-green)', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.05em' }}>CALL</th>
              <th style={{ padding: '6px 8px', textAlign: 'center', position: 'sticky', left: 0, zIndex: 2, background: 'var(--bg-secondary)', borderRight: '1px solid var(--border)', borderLeft: '1px solid var(--border)', color: 'var(--text)', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.05em' }}>STRIKE</th>
              <th colSpan={5} style={{ textAlign: 'center', padding: '6px 4px', color: 'var(--text-red)', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.05em' }}>PUT</th>
            </tr>
            <tr style={{ borderBottom: '1px solid var(--border)' }}>
              <th style={cellHeader}>OI</th>
              <th style={cellHeader}>OI Chg</th>
              <th style={cellHeader}>Vol</th>
              <th style={cellHeader}>IV</th>
              <th style={cellHeader}>LTP</th>
              <th style={{ ...cellHeader, position: 'sticky', left: 0, zIndex: 1, background: 'var(--bg-secondary)', borderRight: '1px solid var(--border)', borderLeft: '1px solid var(--border)' }}>STRIKE</th>
              <th style={cellHeader}>LTP</th>
              <th style={cellHeader}>IV</th>
              <th style={cellHeader}>Vol</th>
              <th style={cellHeader}>OI Chg</th>
              <th style={cellHeader}>OI</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const oc = oiChanges.get(row.strike)
              const isAtm = atmx && row.strike === atmx.strike
              return (
                <tr key={row.strike}
                  style={{
                    borderBottom: '1px solid var(--border)',
                    background: isAtm ? 'var(--bg-active)' : undefined,
                  }}>
                  {/* CE side */}
                  <td style={cellData}>{fmtInt(row.call.oi)}</td>
                  <td style={{ ...cellData, color: oc ? buildupColor(oc.call_oi_change, row.call.change) : '' }}>
                    {oc ? (oc.call_oi_change > 0 ? '+' : '') + fmtInt(oc.call_oi_change) : '-'}
                  </td>
                  <td style={cellData}>{fmtInt(row.call.volume)}</td>
                  <td style={cellData}>{row.call.iv > 0 ? row.call.iv.toFixed(1) : '-'}</td>
                  <td style={{ ...cellData, ...colorCell(row.call.change) }}>{row.call.ltp > 0 ? row.call.ltp.toFixed(1) : '-'}</td>
                  {/* Strike (sticky) */}
                  <td style={{
                    ...cellData,
                    fontWeight: 600,
                    position: 'sticky',
                    left: 0,
                    zIndex: 0,
                    background: isAtm ? 'var(--bg-active)' : 'var(--bg-secondary)',
                    borderRight: '1px solid var(--border)',
                    borderLeft: '1px solid var(--border)',
                    textAlign: 'center',
                  }}>
                    {fmt(row.strike)}
                  </td>
                  {/* PE side */}
                  <td style={{ ...cellData, ...colorCell(row.put.change) }}>{row.put.ltp > 0 ? row.put.ltp.toFixed(1) : '-'}</td>
                  <td style={cellData}>{row.put.iv > 0 ? row.put.iv.toFixed(1) : '-'}</td>
                  <td style={cellData}>{fmtInt(row.put.volume)}</td>
                  <td style={{ ...cellData, color: oc ? buildupColor(oc.put_oi_change, row.put.change) : '' }}>
                    {oc ? (oc.put_oi_change > 0 ? '+' : '') + fmtInt(oc.put_oi_change) : '-'}
                  </td>
                  <td style={cellData}>{fmtInt(row.put.oi)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

/* ─── Styles ─── */

const cellHeader: React.CSSProperties = {
  padding: '4px 6px',
  fontSize: 9,
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
  color: 'var(--text-faint)',
  fontWeight: 600,
  whiteSpace: 'nowrap',
  textAlign: 'right',
}

const cellData: React.CSSProperties = {
  padding: '4px 6px',
  whiteSpace: 'nowrap',
  textAlign: 'right',
  fontFamily: 'var(--font-mono)',
  fontSize: 10,
  fontVariantNumeric: 'tabular-nums',
}

function colorCell(v: number): React.CSSProperties {
  if (v > 0) return { color: 'var(--text-green)' }
  if (v < 0) return { color: 'var(--text-red)' }
  return {}
}
