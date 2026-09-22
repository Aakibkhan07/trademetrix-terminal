'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, friendlyApiError } from '@/lib/api'
import { Dialog } from '@/components/ui/dialog'
import { INDEXES, indexMeta } from '@/lib/options-contracts'
import type { IndexKey } from '@/lib/options-contracts'

/* ═══════════════════════════════════════════════════════════════════════════
   Visual Leg Builder — drag-and-drop option leg construction
   ═══════════════════════════════════════════════════════════════════════════ */

const LOT_SIZES: Record<string, number> = {
  NIFTY: 50, BANKNIFTY: 15, FINNIFTY: 60, MIDCPNIFTY: 75, SENSEX: 10,
}

const LEG_PRESETS = [
  { name: 'Long CE', position: 'buy' as const, optionType: 'CE' as const, lots: 1, strikeOffset: 0 },
  { name: 'Short CE', position: 'sell' as const, optionType: 'CE' as const, lots: 1, strikeOffset: 0 },
  { name: 'Long PE', position: 'buy' as const, optionType: 'PE' as const, lots: 1, strikeOffset: 0 },
  { name: 'Short PE', position: 'sell' as const, optionType: 'PE' as const, lots: 1, strikeOffset: 0 },
]

const STRATEGIES = [
  { name: 'Short Straddle', legs: [
    { position: 'sell' as const, optionType: 'CE' as const, lots: 1, strikeOffset: 0 },
    { position: 'sell' as const, optionType: 'PE' as const, lots: 1, strikeOffset: 0 },
  ]},
  { name: 'Long Straddle', legs: [
    { position: 'buy' as const, optionType: 'CE' as const, lots: 1, strikeOffset: 0 },
    { position: 'buy' as const, optionType: 'PE' as const, lots: 1, strikeOffset: 0 },
  ]},
  { name: 'Bull Call Spread', legs: [
    { position: 'buy' as const, optionType: 'CE' as const, lots: 1, strikeOffset: 0 },
    { position: 'sell' as const, optionType: 'CE' as const, lots: 1, strikeOffset: 100 },
  ]},
  { name: 'Bear Put Spread', legs: [
    { position: 'buy' as const, optionType: 'PE' as const, lots: 1, strikeOffset: 100 },
    { position: 'sell' as const, optionType: 'PE' as const, lots: 1, strikeOffset: 0 },
  ]},
  { name: 'Iron Butterfly', legs: [
    { position: 'sell' as const, optionType: 'CE' as const, lots: 1, strikeOffset: 0 },
    { position: 'sell' as const, optionType: 'PE' as const, lots: 1, strikeOffset: 0 },
    { position: 'buy' as const, optionType: 'CE' as const, lots: 1, strikeOffset: 100 },
    { position: 'buy' as const, optionType: 'PE' as const, lots: 1, strikeOffset: 100 },
  ]},
  { name: 'Iron Condor', legs: [
    { position: 'sell' as const, optionType: 'CE' as const, lots: 1, strikeOffset: 50 },
    { position: 'buy' as const, optionType: 'CE' as const, lots: 1, strikeOffset: 100 },
    { position: 'sell' as const, optionType: 'PE' as const, lots: 1, strikeOffset: 50 },
    { position: 'buy' as const, optionType: 'PE' as const, lots: 1, strikeOffset: 100 },
  ]},
]

function shortSymbol(sym: string | null | undefined): string {
  if (!sym) return ''
  return sym.replace(/^NSE:/, '').replace(/-INDEX$/, '')
}

function legColor(position: 'buy' | 'sell'): string {
  return position === 'buy' ? 'var(--cyan-dim)' : 'var(--red-dim)'
}
function legBorder(position: 'buy' | 'sell'): string {
  return position === 'buy' ? 'var(--cyan-dim)' : 'var(--red-dim)'
}
function legTextColor(position: 'buy' | 'sell'): string {
  return position === 'buy' ? 'var(--cyan)' : 'var(--red)'
}

export default function VisualLegBuilderPage() {
  return <Builder />
}

function Builder() {
  const [indexSymbol, setIndexSymbol] = useState<string>('NIFTY')
  const [legs, setLegs] = useState<Array<{
    id: string
    segment: 'options' | 'futures'
    position: 'buy' | 'sell'
    optionType: 'CE' | 'PE'
    lots: number
    strikeOffset: number
    expiry: 'weekly' | 'monthly'
  }>>([])

  const [dragLeg, setDragLeg] = useState<number | null>(null)
  const [dragOffset, setDragOffset] = useState<{ x: number; y: number }>({ x: 0, y: 0 })

  const [marginResult, setMarginResult] = useState<{ supported: boolean; broker: string; total_margin: number; span_margin: number; exposure_margin: number; currency: string; error: string | null } | null>(null)
  const [marginLoading, setMarginLoading] = useState(false)
  const [marginError, setMarginError] = useState<string | null>(null)

  const [showPresets, setShowPresets] = useState(false)

  const fetchMargin = useCallback(async () => {
    if (!legs.some(l => l.lots > 0)) return
    setMarginLoading(true); setMarginError(null); setMarginResult(null)
    try {
      const legDicts = legs.filter(l => l.lots > 0).map(l => ({
        segment: l.segment, position: l.position, lots: l.lots,
        option_type: l.optionType, expiry: l.expiry,
        strike_criteria: 'atm_offset', strike_value: l.strikeOffset,
      }))
      const data = await api.marginEstimate({ index_symbol: indexSymbol, legs: legDicts })
      setMarginResult({
        supported: data.supported, broker: data.broker,
        total_margin: data.total_margin, span_margin: data.span_margin,
        exposure_margin: data.exposure_margin, currency: data.currency,
        error: data.error ?? null,
      })
    } catch (e) { setMarginError(friendlyApiError(e)) }
    finally { setMarginLoading(false) }
  }, [legs, indexSymbol])

  const addLeg = (template?: { position: 'buy' | 'sell'; optionType: 'CE' | 'PE'; lots: number; strikeOffset: number }) => {
    const t = template ?? { position: 'buy', optionType: 'CE', lots: 1, strikeOffset: 0 }
    setLegs(prev => [...prev, {
      id: `leg_${Date.now()}_${Math.random().toString(36).slice(2,6)}`,
      segment: 'options', position: t.position, optionType: t.optionType,
      lots: t.lots, strikeOffset: t.strikeOffset, expiry: 'weekly',
    }])
  }

  const updateLeg = (id: string, key: string, value: unknown) => {
    setLegs(prev => prev.map(l => l.id === id ? { ...l, [key]: value } : l))
  }

  const removeLeg = (id: string) => {
    setLegs(prev => prev.filter(l => l.id !== id))
  }

  const totalLots = useMemo(() => {
    const bySide = { buy: 0, sell: 0 }
    for (const l of legs) {
      if (l.lots > 0) bySide[l.position] += l.lots
    }
    return bySide
  }, [legs])

  const lotSize = LOT_SIZES[indexSymbol] ?? 50

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto', padding: '40px 20px', fontFamily: 'var(--font-sans)' }}>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 22, fontWeight: 600, margin: '0 0 6px', color: 'var(--text)' }}>Visual Leg Builder</h1>
        <p style={{ fontSize: 13, color: 'var(--text-sub)', margin: 0, lineHeight: 1.5 }}>
          Drag and drop option legs to build multi-leg strategies visually. Connect legs to form spreads, straddles, condors.
          Margin estimates use live broker session data.
        </p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '280px 1fr', gap: 20, alignItems: 'start' }}>
        {/* ── Sidebar ── */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, background: 'var(--panel-2)', borderRadius: 14, border: '1px solid var(--border-2)', padding: 16, position: 'sticky', top: 20 }}>
          <div>
            <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-sub)', marginBottom: 6, display: 'block' }}>INDEX</label>
            <select value={indexSymbol} onChange={e => { setIndexSymbol(e.target.value); setMarginResult(null) }} style={{ width: '100%', padding: '8px 10px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-2)', background: 'var(--panel)', color: 'var(--text)', fontSize: 12, outline: 'none' }}>
              {INDEXES.map(m => <option key={m.key} value={m.key}>{m.key} (Lot: {LOT_SIZES[m.key] ?? 50})</option>)}
            </select>
          </div>

          <button onClick={() => setShowPresets(!showPresets)} style={{ padding: '8px 12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-2)', background: 'var(--panel)', color: 'var(--text)', fontSize: 12, cursor: 'pointer', textAlign: 'left', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            {showPresets ? '▲ Hide Templates' : '▼ Strategy Templates'}
          </button>

          {showPresets && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {STRATEGIES.map((t) => (
                <button key={t.name} onClick={() => { setLegs([]); t.legs.forEach(l => addLeg({ position: l.position, optionType: l.optionType, lots: l.lots, strikeOffset: l.strikeOffset })) }} style={{ padding: '8px 10px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-2)', background: 'var(--panel)', color: 'var(--text-sub)', fontSize: 11.5, cursor: 'pointer', textAlign: 'left' }}>
                  {t.name} ({t.legs.length} legs)
                </button>
              ))}
            </div>
          )}

          <div style={{ borderTop: '1px solid var(--border-2)', paddingTop: 12, marginTop: 4 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-sub)', marginBottom: 8 }}>DRAG TO ADD LEGS</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {LEG_PRESETS.map(p => (
                <button key={p.name}
                  draggable
                  onDragStart={e => { e.dataTransfer.setData('text/plain', JSON.stringify(p)); }}
                  onClick={() => addLeg(p)}
                  style={{ padding: '8px 10px', borderRadius: 'var(--radius-sm)', border: `1px solid ${legBorder(p.position)}`, background: legColor(p.position), color: legTextColor(p.position), fontSize: 11.5, cursor: 'grab', textAlign: 'left', display: 'flex', justifyContent: 'space-between', alignItems: 'center', transition: 'transform 0.1s', WebkitAppearance: 'none' }}
                  onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.transform = 'scale(1.03)'; (e.currentTarget as HTMLButtonElement).style.cursor = 'grabbing' }}
                  onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.transform = 'scale(1)'; (e.currentTarget as HTMLButtonElement).style.cursor = 'grab' }}
                >
                  <span><span style={{ fontWeight: 700 }}>{p.position.toUpperCase()}</span> {p.optionType} · {p.lots} lot{p.lots > 1 ? 's' : ''}</span>
                  <span style={{ fontSize: 10, opacity: 0.6, color: 'var(--text-faint)' }}>+</span>
                </button>
              ))}
            </div>
          </div>

          {legs.length > 0 && (
            <div style={{ borderTop: '1px solid var(--border-2)', paddingTop: 12, marginTop: 4 }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-sub)', marginBottom: 6 }}>POSITION SUMMARY</div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, fontSize: 12 }}>
                <div style={{ padding: 8, background: legColor('buy'), borderRadius: 8, border: `1px solid ${legBorder('buy')}` }}>
                  <div style={{ color: legTextColor('buy'), fontWeight: 700 }}>BUY</div>
                  <div style={{ color: 'var(--text-sub)', fontSize: 10 }}>{totalLots.buy} lots</div>
                </div>
                <div style={{ padding: 8, background: legColor('sell'), borderRadius: 8, border: `1px solid ${legBorder('sell')}` }}>
                  <div style={{ color: legTextColor('sell'), fontWeight: 700 }}>SELL</div>
                  <div style={{ color: 'var(--text-sub)', fontSize: 10 }}>{totalLots.sell} lots</div>
                </div>
              </div>
              <div style={{ marginTop: 8, fontSize: 10, color: 'var(--text-faint)', textAlign: 'center' }}>
                Net: {totalLots.buy === totalLots.sell ? 'Hedged' : `${Math.abs(totalLots.buy - totalLots.sell)} lot${Math.abs(totalLots.buy - totalLots.sell) > 1 ? 's' : ''} net ${totalLots.buy > totalLots.sell ? 'long' : 'short'}`}
                {' '}· Lot size: {lotSize}
              </div>
            </div>
          )}

          {marginResult && (
            <div style={{ borderTop: '1px solid var(--border-2)', paddingTop: 12, marginTop: 4 }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-sub)', marginBottom: 6 }}>ESTIMATED MARGIN</div>
              {!marginResult.supported ? (
                <div style={{ fontSize: 11, color: 'var(--text-sub)', padding: 8, background: 'var(--panel-2)', borderRadius: 8 }}>{marginResult.error ?? 'Unavailable'}</div>
              ) : (
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 6 }}>
                  <div style={{ padding: 8, background: 'var(--panel)', borderRadius: 8, textAlign: 'center' }}>
                    <div style={{ fontSize: 9, color: 'var(--text-faint)', marginBottom: 2 }}>Total</div>
                    <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text)', fontFamily: 'var(--font-mono)' }}>₹{Math.round(marginResult.total_margin).toLocaleString('en-IN')}</div>
                  </div>
                  <div style={{ padding: 8, background: 'var(--panel)', borderRadius: 8, textAlign: 'center' }}>
                    <div style={{ fontSize: 9, color: 'var(--text-faint)', marginBottom: 2 }}>SPAN</div>
                    <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text)', fontFamily: 'var(--font-mono)' }}>₹{Math.round(marginResult.span_margin).toLocaleString('en-IN')}</div>
                  </div>
                  <div style={{ padding: 8, background: 'var(--panel)', borderRadius: 8, textAlign: 'center' }}>
                    <div style={{ fontSize: 9, color: 'var(--text-faint)', marginBottom: 2 }}>Exposure</div>
                    <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text)', fontFamily: 'var(--font-mono)' }}>₹{Math.round(marginResult.exposure_margin).toLocaleString('en-IN')}</div>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* ── Canvas ── */}
        <div
          onDragOver={e => e.preventDefault()}
          onDrop={e => {
            e.preventDefault()
            try {
              const data = JSON.parse(e.dataTransfer.getData('text/plain'))
              addLeg(data)
            } catch {
              addLeg()
            }
          }}
          style={{ background: 'var(--panel-2)', borderRadius: 14, border: '1px solid var(--border-2)', minHeight: 420, padding: 20, position: 'relative', overflow: 'auto' }}
        >
          {legs.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '60px 20px', color: 'var(--text-sub)' }}>
              <div style={{ fontSize: 36, marginBottom: 12, opacity: 0.5 }}>⊞</div>
              <p style={{ fontSize: 13, margin: 0 }}>Drag option legs from the sidebar or click to add</p>
              <p style={{ fontSize: 11, marginTop: 4, color: 'var(--text-faint)' }}>Try a template above for instant setup</p>
            </div>
          ) : (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, alignItems: 'flex-start', justifyContent: 'center', minHeight: 380 }}>
              {legs.map((leg, i) => (
                <LegCard
                  key={leg.id}
                  leg={leg}
                  index={i}
                  lotSize={lotSize}
                  onUpdate={(key, value) => updateLeg(leg.id, key, value)}
                  onRemove={() => removeLeg(leg.id)}
                />
              ))}
            </div>
          )}

          {legs.length > 0 && (
            <div style={{ display: 'flex', gap: 10, marginTop: 20, paddingTop: 16, borderTop: '1px solid var(--border-2)' }}>
              <button onClick={fetchMargin} disabled={marginLoading} style={{ padding: '8px 18px', borderRadius: 'var(--radius-md)', border: 'none', background: 'var(--gradient-primary)', color: 'var(--text-inverse)', fontSize: 12.5, fontWeight: 500, cursor: marginLoading ? 'wait' : 'pointer', boxShadow: '0 2px 8px rgba(0,0,0,0.12)' }}>
                {marginLoading ? 'Estimating...' : 'Estimate Margin'}
              </button>
              <button onClick={() => setLegs([])} style={{ padding: '8px 18px', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-2)', background: 'var(--panel)', color: 'var(--text-sub)', fontSize: 12.5, cursor: 'pointer' }}>
                Clear All
              </button>
              <div style={{ flex: 1 }} />
              {marginError && <span style={{ fontSize: 11.5, color: 'var(--red)' }}>{marginError}</span>}
            </div>
          )}
        </div>
      </div>

      {/* ── How it works ── */}
      <div style={{ marginTop: 36, padding: 20, background: 'var(--panel-2)', borderRadius: 14, border: '1px solid var(--border-2)' }}>
        <h2 style={{ fontSize: 14, fontWeight: 600, margin: '0 0 12px', color: 'var(--text)' }}>How to build a strategy visually</h2>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, fontSize: 12, color: 'var(--text-sub)' }}>
          <Step num="1" title="Pick Index" desc="Choose NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY, or SENSEX" />
          <Step num="2" title="Add Legs" desc="Drag Buy/Sell CE/PE cards onto the canvas, or pick a template" />
          <Step num="3" title="Configure" desc="Set lots, strike offset, expiry for each leg. See live position summary" />
          <Step num="4" title="Estimate" desc="Hit Estimate Margin to see SPAN + exposure for your broker" />
        </div>
      </div>
    </div>
  )
}

function LegCard({ leg, index, lotSize, onUpdate, onRemove }: {
  leg: { id: string; position: 'buy' | 'sell'; optionType: 'CE' | 'PE'; lots: number; strikeOffset: number; expiry: 'weekly' | 'monthly' }
  index: number
  lotSize: number
  onUpdate: (key: string, value: unknown) => void
  onRemove: () => void
}) {
  const qty = leg.lots * lotSize

  return (
    <div
      draggable
      onDragStart={e => { e.dataTransfer.setData('text/plain', JSON.stringify({ position: leg.position, optionType: leg.optionType, lots: 1, strikeOffset: leg.strikeOffset })); }}
      style={{
        width: 200, padding: 14, borderRadius: 12,
        background: legColor(leg.position), border: `1.5px solid ${legBorder(leg.position)}`,
        cursor: 'grab', position: 'relative', transition: 'transform 0.1s, box-shadow 0.1s',
        boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
      }}
      onMouseEnter={e => { (e.currentTarget as HTMLDivElement).style.transform = 'translateY(-2px)'; (e.currentTarget as HTMLDivElement).style.boxShadow = '0 6px 16px rgba(0,0,0,0.12)'; (e.currentTarget as HTMLDivElement).style.cursor = 'grabbing' }}
      onMouseLeave={e => { (e.currentTarget as HTMLDivElement).style.transform = 'translateY(0)'; (e.currentTarget as HTMLDivElement).style.boxShadow = '0 2px 8px rgba(0,0,0,0.08)'; (e.currentTarget as HTMLDivElement).style.cursor = 'grab' }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <span style={{ fontSize: 10, fontWeight: 700, color: legTextColor(leg.position), textTransform: 'uppercase', letterSpacing: '0.5px' }}>
          {leg.position} {leg.optionType}
        </span>
        <button onClick={onRemove} style={{ background: 'none', border: 'none', color: 'var(--text-faint)', cursor: 'pointer', fontSize: 14, padding: '2px 4px', borderRadius: 4, lineHeight: 1 }} title="Remove leg">
          ×
        </button>
      </div>

      <div style={{ fontSize: 11, color: 'var(--text-sub)', marginBottom: 8 }}>
        Leg #{index + 1} · {leg.expiry}
      </div>

      <div style={{ display: 'grid', gap: 6 }}>
        <div>
          <label style={{ fontSize: 9, color: 'var(--text-faint)', display: 'block', marginBottom: 2 }}>Lots</label>
          <input type="number" value={leg.lots} min={1} max={500} onChange={e => onUpdate('lots', Math.max(1, Number(e.target.value)))} style={{ width: '100%', padding: '5px 8px', borderRadius: 'var(--radius-xs)', border: '1px solid var(--border-2)', background: 'var(--panel)', color: 'var(--text)', fontSize: 12, outline: 'none' }} />
        </div>
        <div>
          <label style={{ fontSize: 9, color: 'var(--text-faint)', display: 'block', marginBottom: 2 }}>Qty (lots × {lotSize}) = {qty}</label>
          <input type="number" value={leg.strikeOffset} min={-500} max={5000} onChange={e => onUpdate('strikeOffset', Number(e.target.value))} style={{ width: '100%', padding: '5px 8px', borderRadius: 'var(--radius-xs)', border: '1px solid var(--border-2)', background: 'var(--panel)', color: 'var(--text)', fontSize: 12, outline: 'none' }} />
        </div>
        <div>
          <label style={{ fontSize: 9, color: 'var(--text-faint)', display: 'block', marginBottom: 2 }}>Strike Offset (₹)</label>
          <select value={leg.expiry} onChange={e => onUpdate('expiry', e.target.value as 'weekly' | 'monthly')} style={{ width: '100%', padding: '5px 8px', borderRadius: 'var(--radius-xs)', border: '1px solid var(--border-2)', background: 'var(--panel)', color: 'var(--text)', fontSize: 12, outline: 'none' }}>
            <option value="weekly">Weekly</option>
            <option value="monthly">Monthly</option>
          </select>
        </div>
      </div>

      <div style={{ marginTop: 10, paddingTop: 8, borderTop: '1px dashed var(--border-2)', fontSize: 10, color: 'var(--text-faint)', textAlign: 'center' }}>
        {leg.position === 'buy'
          ? `Pay ~₹${Math.round(leg.strikeOffset + 20000)} premium`
          : `Recive ~₹${Math.round(leg.strikeOffset + 20000)} premium`}
      </div>
    </div>
  )
}

function Step({ num, title, desc }: { num: string; title: string; desc: string }) {
  return (
    <div>
      <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--cyan)', marginBottom: 4 }}>{num}</div>
      <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text)', marginBottom: 4 }}>{title}</div>
      <div style={{ lineHeight: 1.5 }}>{desc}</div>
    </div>
  )
}
