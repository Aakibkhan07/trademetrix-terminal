'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { useMarketData } from '@/lib/use-market-data'
import { useToast } from '@/lib/use-toast'
import { useUIStore } from '@/lib/stores/ui-store'

const LOT_SIZES: Record<string, number> = {
  NIFTY: 65, BANKNIFTY: 30, FINNIFTY: 60, SENSEX: 20, MIDCPNIFTY: 75,
}

const OPTION_RE = /^([^:]+):([A-Z]+)(\d{2}[A-Z]{3})(\d+)(CE|PE)$/

interface OrderResult {
  success: boolean
  broker_order_id: string
  message: string
  status: string
}

interface ParsedOption {
  exchange: string
  underlying: string
  expiry: string
  strike: number
  optionType: 'CE' | 'PE'
  lotSize: number
}

function parseOption(symbol: string): ParsedOption | null {
  const m = symbol.toUpperCase().match(OPTION_RE)
  if (!m) return null
  return {
    exchange: m[1],
    underlying: m[2],
    expiry: m[3],
    strike: Number(m[4]),
    optionType: m[5] as 'CE' | 'PE',
    lotSize: LOT_SIZES[m[2]] || 1,
  }
}

function fmt(n: number) {
  return n.toLocaleString('en-IN', { minimumFractionDigits: 0, maximumFractionDigits: 2 })
}

export default function QuickOrderDrawer() {
  const { quickOrder, closeQuickOrder, drawerPrefs, setDrawerPrefs } = useUIStore()
  const { ticks, subscribe } = useMarketData()
  const { toast } = useToast()
  const qc = useQueryClient()

  const { open, symbol, name, side, prefillQty } = quickOrder
  const parsed = useMemo(() => (open ? parseOption(symbol) : null), [open, symbol])
  const ltp = open ? ticks[symbol]?.last_price || 0 : 0

  const [qty, setQty] = useState(1)
  const [orderType, setOrderType] = useState<'MARKET' | 'LIMIT'>(drawerPrefs.orderType)
  const [price, setPrice] = useState(0)
  const [product, setProduct] = useState<'INTRADAY' | 'NRML'>(drawerPrefs.product)
  const [isPaper, setIsPaper] = useState(drawerPrefs.paper)
  const [submitting, setSubmitting] = useState(false)
  const [advanced, setAdvanced] = useState(false)
  const [slPct, setSlPct] = useState(10)
  const [targetPct, setTargetPct] = useState(15)
  const [trailingSl, setTrailingSl] = useState(false)
  const [trailStep, setTrailStep] = useState(2)
  const [riskPct, setRiskPct] = useState(1)
  const [capital, setCapital] = useState(100000)

  useEffect(() => {
    if (open) {
      subscribe([symbol])
      setQty(prefillQty && prefillQty > 0 ? prefillQty : parsed?.lotSize || 1)
      setOrderType(drawerPrefs.orderType)
      setProduct(drawerPrefs.product)
      setIsPaper(drawerPrefs.paper)
      setSubmitting(false)
    }
  }, [open, symbol, parsed?.lotSize, subscribe, prefillQty, drawerPrefs.paper, drawerPrefs.product, drawerPrefs.orderType])

  useEffect(() => {
    if (open && ltp > 0) setPrice(ltp)
  }, [open, ltp])

  const close = useCallback(() => closeQuickOrder(), [closeQuickOrder])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') close() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, close])

  if (!open) return null

  const entry = orderType === 'LIMIT' ? (price || ltp || 0) : (ltp || 0)
  const lotSize = parsed?.lotSize || 1
  const lots = qty / lotSize
  const sl = side === 'BUY' ? entry * (1 - slPct / 100) : entry * (1 + slPct / 100)
  const target = side === 'BUY' ? entry * (1 + targetPct / 100) : entry * (1 - targetPct / 100)
  const notional = entry * qty
  const charges = side === 'SELL' ? 20 * 1.18 + notional * 0.000625 : 20 * 1.18
  const estMargin = notional * 0.18
  const riskAmount = entry > 0 ? Math.abs(entry - sl) * qty : 0
  const capitalRisk = capital > 0 && entry > 0 ? (riskAmount / capital) * 100 : 0
  const rr = slPct > 0 ? targetPct / slPct : 0

  const submit = async () => {
    if (qty <= 0) { toast('error', 'Quantity must be at least 1'); return }
    if (orderType === 'LIMIT' && price <= 0) { toast('error', 'Enter a limit price'); return }
    setSubmitting(true)
    try {
      const res = await api.engine.trade({
        symbol,
        side,
        quantity: qty,
        price: orderType === 'LIMIT' ? price : 0,
        exchange: parsed?.exchange || 'NSE',
        order_type: orderType,
        product,
        instrument_type: parsed ? 'OPT' : 'EQ',
        strike_price: parsed?.strike,
        expiry_date: parsed?.expiry,
        option_type: parsed?.optionType,
        is_paper: isPaper,
        source: 'quick_drawer',
      }) as { result: OrderResult }
      const r = res?.result
      if (r?.success) {
        toast('success', `${side} ${qty} ${name || symbol}${isPaper ? ' (paper)' : ''} — ${r.status}`)
        qc.invalidateQueries({ queryKey: ['orders'] })
        qc.invalidateQueries({ queryKey: ['positions'] })
        qc.invalidateQueries({ queryKey: ['funds'] })
        close()
      } else {
        toast('error', r?.message || 'Order rejected')
      }
    } catch (e) {
      toast('error', String(e))
    } finally {
      setSubmitting(false)
    }
  }

  const paperMode = isPaper
  const notPaper = !isPaper

  return (
    <div className="t-drawer-overlay" onClick={close}>
      <div className="t-drawer" onClick={e => e.stopPropagation()}>
        <div className="t-drawer-header">
          <div>
            <div className="t-drawer-title">{name || symbol}</div>
            <div className="t-faint" style={{ fontSize: 11, marginTop: 2 }}>{symbol}</div>
          </div>
          <button className="t-btn t-btn-sm t-btn-ghost" onClick={close}>✕</button>
        </div>

        <div className="t-drawer-body">
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
            <span className="t-num" style={{ fontSize: 26, fontWeight: 800 }}>{ltp ? fmt(ltp) : '—'}</span>
            {ltp > 0 && (
              <span className={`t-num ${(ticks[symbol]?.change_pct ?? 0) >= 0 ? 't-up' : 't-down'}`} style={{ fontSize: 13 }}>
                {(ticks[symbol]?.change_pct ?? 0) >= 0 ? '+' : ''}{(ticks[symbol]?.change_pct ?? 0).toFixed(2)}%
              </span>
            )}
          </div>

          <div className="t-seg" style={{ marginTop: 2 }}>
            <button
              className={`t-seg-btn buy ${side === 'BUY' ? 'active' : ''}`}
              onClick={() => useUIStore.setState(s => ({ quickOrder: { ...s.quickOrder, side: 'BUY' } }))}
            >
              BUY
            </button>
            <button
              className={`t-seg-btn sell ${side === 'SELL' ? 'active' : ''}`}
              onClick={() => useUIStore.setState(s => ({ quickOrder: { ...s.quickOrder, side: 'SELL' } }))}
            >
              SELL
            </button>
          </div>

          <div>
            <div className="t-drawer-label">QUANTITY {parsed && lotSize > 1 ? `(lots × ${lotSize})` : ''}</div>
            <div className="t-stepper">
              <button className="t-stepper-btn" onClick={() => setQty(q => Math.max(lotSize, q - lotSize))}>−</button>
              <div className="t-stepper-val">{parsed && lotSize > 1 ? `${lots} lots` : qty}</div>
              <button className="t-stepper-btn" onClick={() => setQty(q => q + lotSize)}>+</button>
              <span className="t-faint" style={{ fontSize: 11 }}>= {qty} qty</span>
            </div>
          </div>

          <div className="t-row" style={{ gap: 8 }}>
            <div className="t-col" style={{ flex: 1 }}>
              <div className="t-drawer-label">ORDER TYPE</div>
              <select className="t-select" value={orderType} onChange={e => { const v = e.target.value as 'MARKET' | 'LIMIT'; setOrderType(v); setDrawerPrefs({ orderType: v }) }}>
                <option value="MARKET">Market</option>
                <option value="LIMIT">Limit</option>
              </select>
            </div>
            <div className="t-col" style={{ flex: 1 }}>
              <div className="t-drawer-label">PRODUCT</div>
              <select className="t-select" value={product} onChange={e => { const v = e.target.value as 'INTRADAY' | 'NRML'; setProduct(v); setDrawerPrefs({ product: v }) }}>
                <option value="INTRADAY">Intraday (MIS)</option>
                <option value="NRML">Carry (NRML)</option>
              </select>
            </div>
          </div>

          {orderType === 'LIMIT' && (
            <div>
              <div className="t-drawer-label">LIMIT PRICE</div>
              <input
                className="t-input"
                type="number"
                step={0.05}
                value={price || ''}
                onChange={e => setPrice(Number(e.target.value))}
                placeholder="0.00"
              />
            </div>
          )}

          <div className="t-panel" style={{ padding: '10px 12px' }}>
            <div className="t-drawer-label" style={{ marginBottom: 8 }}>AUTO PROTECTION (applied on fill)</div>
            <div style={{ display: 'flex', gap: 8 }}>
              <span className="t-chip" style={{ color: 'var(--red)' }}>SL {entry ? fmt(sl) : '—'}</span>
              <span className="t-chip" style={{ color: 'var(--green)' }}>Target {entry ? fmt(target) : '—'}</span>
            </div>
            <div className="t-faint" style={{ fontSize: 10, marginTop: 6 }}>
              SL −{slPct}% / Target +{targetPct}% from entry. Exits auto-place when breached.
            </div>
          </div>

          <div className="t-panel" style={{ padding: '10px 12px' }}>
            <button
              className="t-btn t-btn-ghost"
              style={{ width: '100%', justifyContent: 'space-between', fontSize: 11, height: 'auto', padding: '2px 0' }}
              onClick={() => setAdvanced(a => !a)}
            >
              <span style={{ fontWeight: 800, letterSpacing: '.1em' }}>ADVANCED</span>
              <span style={{ color: 'var(--text-faint)' }}>{advanced ? '▾' : '▸'}</span>
            </button>
            {advanced && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 10 }}>
                <div className="t-row" style={{ gap: 8 }}>
                  <div className="t-col" style={{ flex: 1 }}>
                    <div className="t-drawer-label">SL %</div>
                    <input className="t-input" type="number" step={1} min={0.1} value={slPct} onChange={e => setSlPct(Number(e.target.value))} />
                  </div>
                  <div className="t-col" style={{ flex: 1 }}>
                    <div className="t-drawer-label">TARGET %</div>
                    <input className="t-input" type="number" step={1} min={0.1} value={targetPct} onChange={e => setTargetPct(Number(e.target.value))} />
                  </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <label className="t-drawer-label" style={{ marginBottom: 0 }}>TRAILING SL</label>
                  <input type="checkbox" checked={trailingSl} onChange={e => setTrailingSl(e.target.checked)} />
                  {trailingSl && (
                    <>
                      <span className="t-faint" style={{ fontSize: 10 }}>step %</span>
                      <input className="t-input" type="number" step={0.5} min={0.1} value={trailStep} onChange={e => setTrailStep(Number(e.target.value))} style={{ width: 64, height: 24 }} />
                    </>
                  )}
                </div>
                <div className="t-row" style={{ gap: 8 }}>
                  <div className="t-col" style={{ flex: 1 }}>
                    <div className="t-drawer-label">RISK / TRADE %</div>
                    <input className="t-input" type="number" step={0.25} min={0.1} value={riskPct} onChange={e => setRiskPct(Number(e.target.value))} />
                  </div>
                  <div className="t-col" style={{ flex: 1 }}>
                    <div className="t-drawer-label">CAPITAL ₹</div>
                    <input className="t-input" type="number" step={10000} value={capital} onChange={e => setCapital(Number(e.target.value))} />
                  </div>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
                  <span className="t-faint">Expected RR</span>
                  <span className="t-num">{rr.toFixed(2)}:1</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
                  <span className="t-faint">Risk amount</span>
                  <span className={`t-num ${capitalRisk > riskPct ? 't-down' : 't-up'}`}>₹{fmt(riskAmount)} ({capitalRisk.toFixed(2)}% cap)</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
                  <span className="t-faint">Est. margin</span>
                  <span className="t-num">₹{fmt(estMargin)}</span>
                </div>
                <div className="t-faint" style={{ fontSize: 9, lineHeight: 1.4 }}>
                  Risk/RR & margin are client-side estimates (placeholder). Actual bracket levels are auto-applied on fill.
                </div>
              </div>
            )}
          </div>

          <div className="t-panel" style={{ padding: '10px 12px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 4 }}>
              <span className="t-faint">Notional</span>
              <span className="t-num">₹{fmt(notional)}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 4 }}>
              <span className="t-faint">Est. charges (brokerage + taxes)</span>
              <span className="t-num">≈ ₹{fmt(charges)}</span>
            </div>
            <div className="t-faint" style={{ fontSize: 10, marginTop: 2 }}>Approximate only. Actual charges per broker.</div>
          </div>

          <div className="t-seg" style={{ marginTop: 'auto' }}>
            <button
              className={`t-mode-btn active-paper ${paperMode ? 'active-paper' : ''}`}
              onClick={() => { setIsPaper(true); setDrawerPrefs({ paper: true }) }}
              style={{ flex: 1 }}
            >
              PAPER
            </button>
            <button
              className={`t-mode-btn active-live ${notPaper ? 'active-live' : ''}`}
              onClick={() => { setIsPaper(false); setDrawerPrefs({ paper: false }) }}
              style={{ flex: 1 }}
            >
              LIVE
            </button>
          </div>
        </div>

        <div className="t-drawer-header" style={{ borderTop: '1px solid var(--border)', borderBottom: 'none' }}>
          <button
            className="t-btn t-btn-primary"
            style={{ flex: 1, background: side === 'BUY' ? 'rgba(52,211,153,.9)' : 'rgba(248,113,113,.9)', color: '#0a0a12' }}
            onClick={submit}
            disabled={submitting}
          >
            {submitting ? 'Placing…' : `${side} ${qty} ${name || symbol}`}
          </button>
        </div>
      </div>
    </div>
  )
}
