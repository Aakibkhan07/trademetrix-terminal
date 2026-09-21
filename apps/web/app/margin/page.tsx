'use client'

import { useState, useCallback, useMemo } from 'react'
import { api, friendlyApiError } from '@/lib/api'
import { INDEXES, indexMeta, type IndexKey } from '@/lib/options-contracts'

export default function MarginEstimatorPage() {
  return <Estimator />
}

function Estimator() {
  const [indexSymbol, setIndexSymbol] = useState<string>('NIFTY')
  const [selectedBroker, setSelectedBroker] = useState<string>('')
  const [legCount, setLegCount] = useState<number>(1)
  const [legs, setLegs] = useState<Array<{
    segment: string; position: string; lots: number
    optionType: string; expiry: string; strikeCriteria: string; strikeValue: number
  }>>(() => Array(legCount).fill({ segment: 'options', position: 'buy', lots: 1, optionType: 'CE', expiry: 'weekly', strikeCriteria: 'atm_offset', strikeValue: 0 }))

  const [result, setResult] = useState<{ supported: boolean; broker: string; totalMargin: number; spanMargin: number; exposureMargin: number; currency: string; error: string | null } | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const availableIndexes = useMemo(() => INDEXES.map(m => ({ id: m.key, label: m.name })), [])

  const handleLegChange = (i: number, key: string, value: string | number) => {
    const next = [...legs]
    ;(next[i] as Record<string, unknown>)[key] = value
    setLegs(next)
    setResult(null)
  }

  const addLeg = () => {
    if (legCount >= 8) return
    setLegCount(c => c + 1)
    setLegs(prev => [...prev, { segment: 'options', position: 'buy', lots: 1, optionType: 'CE', expiry: 'weekly', strikeCriteria: 'atm_offset', strikeValue: 0 }])
    setResult(null)
  }

  const removeLeg = (i: number) => {
    if (legCount <= 1) return
    setLegCount(c => c - 1)
    setLegs(prev => prev.filter((_, idx) => idx !== i))
    setResult(null)
  }

  const handleEstimate = useCallback(async () => {
    if (!legs.some(l => l.lots > 0)) { setError('Add at least one leg with quantity'); return }
    setLoading(true); setError(null); setResult(null)
    try {
      const legDicts = legs.map(l => ({
        segment: l.segment, position: l.position, lots: l.lots,
        option_type: l.optionType, expiry: l.expiry,
        strike_criteria: l.strikeCriteria, strike_value: l.strikeValue,
      }))
      const data = await api.marginEstimate({ index_symbol: indexSymbol, legs: legDicts, broker: selectedBroker || undefined })
      setResult({
        supported: data.supported,
        broker: data.broker,
        totalMargin: data.total_margin,
        spanMargin: data.span_margin,
        exposureMargin: data.exposure_margin,
        currency: data.currency,
        error: data.error ?? null,
      })
    } catch (err) {
      setError(friendlyApiError(err))
    } finally {
      setLoading(false)
    }
  }, [indexSymbol, legs, selectedBroker])

  const strategyPresets = [
    { name: 'Short Straddle', legs: [{ segment: 'options', position: 'sell', lots: 1, optionType: 'CE', expiry: 'weekly', strikeCriteria: 'atm_offset', strikeValue: 0 }, { segment: 'options', position: 'sell', lots: 1, optionType: 'PE', expiry: 'weekly', strikeCriteria: 'atm_offset', strikeValue: 0 }] },
    { name: 'Long Straddle', legs: [{ segment: 'options', position: 'buy', lots: 1, optionType: 'CE', expiry: 'weekly', strikeCriteria: 'atm_offset', strikeValue: 0 }, { segment: 'options', position: 'buy', lots: 1, optionType: 'PE', expiry: 'weekly', strikeCriteria: 'atm_offset', strikeValue: 0 }] },
    { name: 'Bull Call Spread', legs: [{ segment: 'options', position: 'buy', lots: 1, optionType: 'CE', expiry: 'weekly', strikeCriteria: 'atm_offset', strikeValue: 0 }, { segment: 'options', position: 'sell', lots: 1, optionType: 'CE', expiry: 'weekly', strikeCriteria: 'atm_offset', strikeValue: 100 }] },
    { name: 'Bear Put Spread', legs: [{ segment: 'options', position: 'buy', lots: 1, optionType: 'PE', expiry: 'weekly', strikeCriteria: 'atm_offset', strikeValue: 100 }, { segment: 'options', position: 'sell', lots: 1, optionType: 'PE', expiry: 'weekly', strikeCriteria: 'atm_offset', strikeValue: 0 }] },
    { name: 'Iron Condor', legs: [{ segment: 'options', position: 'sell', lots: 1, optionType: 'CE', expiry: 'weekly', strikeCriteria: 'atm_offset', strikeValue: 50 }, { segment: 'options', position: 'buy', lots: 1, optionType: 'CE', expiry: 'weekly', strikeCriteria: 'atm_offset', strikeValue: 100 }, { segment: 'options', position: 'sell', lots: 1, optionType: 'PE', expiry: 'weekly', strikeCriteria: 'atm_offset', strikeValue: 50 }, { segment: 'options', position: 'buy', lots: 1, optionType: 'PE', expiry: 'weekly', strikeCriteria: 'atm_offset', strikeValue: 100 }] },
  ]

  return (
    <div style={{ maxWidth: 720, margin: '0 auto', padding: '40px 20px', fontFamily: 'var(--font-sans)' }}>
      <div style={{ marginBottom: 28 }}>
        <h1 style={{ fontSize: 22, fontWeight: 600, margin: '0 0 6px', color: 'var(--text)' }}>Margin Estimator</h1>
        <p style={{ fontSize: 13, color: 'var(--text-dim)', margin: 0, lineHeight: 1.5 }}>
          Estimate SPAN/exposure margin for multi-leg option strategies before placing orders. Results use live brokerage session data where available.
        </p>
      </div>

      <div style={{ marginBottom: 20 }}>
        <label style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-dim)', marginBottom: 6, display: 'block' }}>Index</label>
        <select value={indexSymbol} onChange={e => { setIndexSymbol(e.target.value); setResult(null) }} style={{ width: '100%', padding: '8px 12px', borderRadius: 10, border: '1px solid var(--panel-brd)', background: 'var(--panel)', color: 'var(--text)', fontSize: 13, outline: 'none' }}>
          {availableIndexes.map((idx) => (
            <option key={idx.id} value={idx.id}>{idx.label} — {idx.id}</option>
          ))}
        </select>
      </div>

      <div style={{ marginBottom: 20 }}>
        <label style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-dim)', marginBottom: 6, display: 'block' }}>Broker (optional — uses live session data)</label>
        <select value={selectedBroker} onChange={e => { setSelectedBroker(e.target.value); setResult(null) }} style={{ width: '100%', padding: '8px 12px', borderRadius: 10, border: '1px solid var(--panel-brd)', background: 'var(--panel)', color: 'var(--text)', fontSize: 13, outline: 'none' }}>
          <option value="">Auto-detect (default: Fyers)</option>
          <option value="fyers">Fyers</option>
          <option value="dhan">Dhan</option>
          <option value="zerodha">Zerodha</option>
          <option value="upstox">Upstox</option>
          <option value="angelone">Angel One</option>
        </select>
      </div>

      <div style={{ marginBottom: 16, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {strategyPresets.map(p => (
          <button key={p.name} onClick={() => { setLegs(p.legs); setLegCount(p.legs.length); setResult(null) }} style={{ padding: '6px 12px', borderRadius: 10, border: '1px solid var(--panel-brd)', background: 'var(--panel)', color: 'var(--text-dim)', fontSize: 12, cursor: 'pointer', transition: 'all 0.15s' }} onMouseEnter={e => { e.currentTarget.style.background = 'var(--panel-hi)'; e.currentTarget.style.color = 'var(--text)' }} onMouseLeave={e => { e.currentTarget.style.background = 'var(--panel)'; e.currentTarget.style.color = 'var(--text-dim)' }}>
            {p.name}
          </button>
        ))}
      </div>

      <div style={{ marginBottom: 20, borderTop: '1px solid var(--panel-brd)', borderBottom: '1px solid var(--panel-brd)', padding: '14px 0' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
          <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--text)' }}>Legs ({legCount})</span>
          <div style={{ display: 'flex', gap: 8 }}>
            <button onClick={addLeg} disabled={legCount >= 8} style={{ padding: '4px 10px', borderRadius: 8, border: '1px solid var(--panel-brd)', background: 'var(--panel)', color: 'var(--text-dim)', fontSize: 12, cursor: legCount >= 8 ? 'not-allowed' : 'pointer' }}>+ Add</button>
          </div>
        </div>
        {legs.map((leg, i) => (
          <div key={i} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 0.8fr', gap: 10, marginBottom: i < legs.length - 1 ? 12 : 0, padding: 12, background: 'var(--panel-bg)', borderRadius: 10, border: '1px solid var(--panel-brd)' }}>
            <select value={leg.segment} onChange={e => handleLegChange(i, 'segment', e.target.value)} style={{ padding: '7px 10px', borderRadius: 8, border: '1px solid var(--panel-brd)', background: 'var(--panel)', color: 'var(--text)', fontSize: 12, outline: 'none' }}>
              <option value="options">Options</option>
              <option value="futures">Futures</option>
              <option value="spot">Spot</option>
            </select>
            <select value={leg.position} onChange={e => handleLegChange(i, 'position', e.target.value)} style={{ padding: '7px 10px', borderRadius: 8, border: '1px solid var(--panel-brd)', background: 'var(--panel)', color: 'var(--text)', fontSize: 12, outline: 'none' }}>
              <option value="buy">Buy</option>
              <option value="sell">Sell</option>
            </select>
            <input type="number" value={leg.lots} min={1} max={500} onChange={e => handleLegChange(i, 'lots', Number(e.target.value))} placeholder="Lots" style={{ padding: '7px 10px', borderRadius: 8, border: '1px solid var(--panel-brd)', background: 'var(--panel)', color: 'var(--text)', fontSize: 12, outline: 'none', width: '100%' }} />
            <select value={leg.optionType} onChange={e => handleLegChange(i, 'optionType', e.target.value)} style={{ padding: '7px 10px', borderRadius: 8, border: '1px solid var(--panel-brd)', background: 'var(--panel)', color: 'var(--text)', fontSize: 12, outline: 'none' }}>
              <option value="CE">CE</option>
              <option value="PE">PE</option>
            </select>
            <input type="number" value={leg.strikeValue} min={-500} max={5000} onChange={e => handleLegChange(i, 'strikeValue', Number(e.target.value))} placeholder="Offset" style={{ gridColumn: 'span 2', padding: '7px 10px', borderRadius: 8, border: '1px solid var(--panel-brd)', background: 'var(--panel)', color: 'var(--text)', fontSize: 12, outline: 'none', width: '100%' }} />
            <button onClick={() => removeLeg(i)} disabled={legCount <= 1} style={{ alignSelf: 'top', padding: '4px 10px', borderRadius: 8, border: '1px solid var(--err)', background: 'transparent', color: 'var(--err)', fontSize: 11, cursor: legCount <= 1 ? 'not-allowed' : 'pointer' }}>Remove</button>
          </div>
        ))}
      </div>

      <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 24 }}>
        <button onClick={handleEstimate} disabled={loading} style={{ padding: '9px 22px', borderRadius: 10, border: 'none', background: 'var(--accent)', color: '#fff', fontSize: 13, fontWeight: 500, cursor: loading ? 'wait' : 'pointer', boxShadow: '0 2px 8px rgba(0,0,0,0.15)' }}>
          {loading ? 'Estimating...' : 'Estimate Margin'}
        </button>
        {error && <span style={{ fontSize: 12.5, color: 'var(--err)', flex: 1 }}>{error}</span>}
      </div>

      {result && (
        <div style={{ background: 'var(--panel-bg)', borderRadius: 14, border: '1px solid var(--panel-brd)', padding: 20, marginBottom: 20 }}>
          <h3 style={{ fontSize: 14, fontWeight: 600, margin: '0 0 14px', color: 'var(--text)' }}>
            {result.supported ? `Margin Estimate — ${result.broker} (${result.currency})` : 'Estimate Unavailable'}
          </h3>
          {!result.supported ? (
            <p style={{ fontSize: 13, color: 'var(--text-dim)', margin: 0, lineHeight: 1.6 }}>
              {result.error ?? 'Broker connection not available. Connect your broker first, or leave Broker empty to use default Fyers session.'}
            </p>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
              <div style={{ padding: 14, background: 'var(--panel)', borderRadius: 10, border: '1px solid var(--panel-brd)' }}>
                <div style={{ fontSize: 11, color: 'var(--text-dim)', marginBottom: 4 }}>Total Margin</div>
                <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--text)', fontFamily: 'var(--font-mono)' }}>₹{result.totalMargin.toLocaleString('en-IN', { maximumFractionDigits: 0 })}</div>
              </div>
              <div style={{ padding: 14, background: 'var(--panel)', borderRadius: 10, border: '1px solid var(--panel-brd)' }}>
                <div style={{ fontSize: 11, color: 'var(--text-dim)', marginBottom: 4 }}>SPAN Margin</div>
                <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--text)', fontFamily: 'var(--font-mono)' }}>₹{result.spanMargin.toLocaleString('en-IN', { maximumFractionDigits: 0 })}</div>
              </div>
              <div style={{ padding: 14, background: 'var(--panel)', borderRadius: 10, border: '1px solid var(--panel-brd)' }}>
                <div style={{ fontSize: 11, color: 'var(--text-dim)', marginBottom: 4 }}>Exposure Margin</div>
                <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--text)', fontFamily: 'var(--font-mono)' }}>₹{result.exposureMargin.toLocaleString('en-IN', { maximumFractionDigits: 0 })}</div>
              </div>
            </div>
          )}
          <p style={{ fontSize: 11, color: 'var(--text-faint)', marginTop: 14, paddingTop: 12, borderTop: '1px solid var(--panel-brd)', lineHeight: 1.5 }}>
            Estimates are indicative. Actual margin may vary based on broker policy, real-time premiums, and SEBI circulars. Use for planning only — not a guarantee.
          </p>
        </div>
      )}
    </div>
  )
}
