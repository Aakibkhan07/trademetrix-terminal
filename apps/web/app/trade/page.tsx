'use client'

import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'
import { useMarketData } from '@/lib/use-market-data'
import { buildContract, groupExpiries, indexMeta, marginLeg } from '@/lib/options-contracts'
import type { IndexKey, Moneyness } from '@/lib/options-contracts'
import { IndexStrip } from '@/components/trade/index-strip'
import { ChainPanel } from '@/components/trade/chain-panel'
import type { ChainMetrics } from '@/components/trade/chain-panel'
import { OrderCard } from '@/components/trade/order-card'
import type { OrderForm } from '@/components/trade/order-card'
import { PresetsBar } from '@/components/trade/presets-bar'
import { FillsTicker } from '@/components/trade/fills-ticker'
import type { Fill } from '@/components/trade/fills-ticker'
import type { ChainData, OrderResult } from '@/components/trade/types'

interface BrokerCred {
  id: string
  broker: string
  is_active: boolean
  created_at: string
}

interface MarginResp {
  total_margin: number
  span_margin: number
  exposure_margin: number
}

const EMPTY_CHAIN: ChainData = { optionChain: [], expiries: [] }

export default function TradePage() {
  const { token } = useAuth()
  const { ticks, connected, subscribe } = useMarketData()

  const [creds, setCreds] = useState<BrokerCred[]>([])
  const [credsLoading, setCredsLoading] = useState(true)
  const [credsError, setCredsError] = useState('')

  const [index, setIndex] = useState<IndexKey>('NIFTY')
  const [chain, setChain] = useState<ChainData>(EMPTY_CHAIN)
  const [chainLoading, setChainLoading] = useState(false)
  const [chainError, setChainError] = useState('')
  const [liveSource, setLiveSource] = useState(false)

  const [form, setForm] = useState<OrderForm>({
    index: 'NIFTY',
    moneyness: 'ATM',
    customStrike: null,
    optionType: 'CE',
    expiry: '',
    lots: 1,
    orderType: 'MARKET',
    limitPrice: 0,
  })

  const [lotSize, setLotSize] = useState(0)
  const [margin, setMargin] = useState<{ span: number; exposure: number; total: number } | null>(null)
  const [marginLoading, setMarginLoading] = useState(false)
  const [mode, setMode] = useState<'paper' | 'live'>('paper')
  const [confirmingLive, setConfirmingLive] = useState(false)
  const [placing, setPlacing] = useState(false)
  const [orderResult, setOrderResult] = useState<OrderResult | null>(null)
  const [orderError, setOrderError] = useState('')
  const marginSeq = useRef(0)

  const activeBroker = creds.find(c => c.is_active)
  const meta = indexMeta(index)
  const spotSymbol = meta.spotSymbol

  const spot = useMemo(() => {
    const t = ticks[spotSymbol]
    return t && t.last_price > 0 ? t.last_price : null
  }, [ticks, spotSymbol])

  const spotTick = ticks[spotSymbol]
  const changePct = spotTick && spotTick.change_pct != null ? spotTick.change_pct : null

  // ---- creds ----
  const loadCreds = useCallback(async () => {
    setCredsLoading(true)
    setCredsError('')
    try {
      const d = await api.brokers.credentials() as { credentials: BrokerCred[] }
      setCreds(d.credentials || [])
    } catch (e) {
      setCredsError(String(e))
    } finally {
      setCredsLoading(false)
    }
  }, [])
  useEffect(() => { if (token) loadCreds() }, [token, loadCreds])

  // ---- spot subscription ----
  useEffect(() => {
    if (!token) return
    subscribe([spotSymbol])
  }, [token, spotSymbol, subscribe])

  // ---- chain ----
  const loadChain = useCallback(async (sym: string) => {
    setChainLoading(true)
    setChainError('')
    try {
      const d = await api.marketdata.optionChain(sym) as ChainData
      const rows = d.optionChain || []
      const exps = d.expiries || []
      if (!rows.length) {
        setChainError('Empty response from server')
        setChain({ optionChain: [], expiries: exps })
        return
      }
      setChain({ optionChain: rows, expiries: exps })
      setLiveSource(rows.some(r => r.call.ltp > 0 || r.put.ltp > 0))
    } catch (e) {
      setChainError(String(e))
      setChain(EMPTY_CHAIN)
    } finally {
      setChainLoading(false)
    }
  }, [])

  const onIndexChange = useCallback((i: IndexKey) => {
    setIndex(i)
    setChain(EMPTY_CHAIN)
    setChainError('')
    setForm(f => ({ ...f, index: i, expiry: '', moneyness: 'ATM' }))
  }, [])

  useEffect(() => {
    if (!token) return
    loadChain(index)
  }, [token, index, loadChain])

  useEffect(() => {
    if (chain.expiries.length && !chain.expiries.includes(form.expiry)) {
      setForm(f => ({ ...f, expiry: chain.expiries[0] }))
    }
  }, [chain.expiries, form.expiry])

  // ---- lot size ----
  useEffect(() => {
    if (!token || !index) return
    let alive = true
    fetchLotSizeOnce(index).then(v => { if (alive) setLotSize(v) })
    return () => { alive = false }
  }, [token, index])

  // ---- contract + margin ----
  const contract = useMemo(() => {
    const strikes = chain.optionChain.map(r => r.strike)
    const exps = groupExpiries(chain.expiries)
    return buildContract({
      index,
      spot,
      chainStrikes: strikes,
      moneyness: form.moneyness,
      customStrike: form.customStrike,
      optionType: form.optionType,
      expiry: form.expiry || exps.weekly || '',
      expiryGroup: form.expiry === exps.monthly ? 'monthly' : 'weekly',
      lots: form.lots,
      lotSize: lotSize || meta.fallbackLot,
    })
  }, [index, spot, chain.optionChain, chain.expiries, form.moneyness, form.customStrike, form.optionType, form.expiry, form.lots, lotSize, meta])

  useEffect(() => {
    if (!token || !contract.strike || !form.expiry) return
    const seq = ++marginSeq.current
    setMarginLoading(true)
    api.marginEstimate({
      index_symbol: index,
      legs: [marginLeg({ position: 'sell', optionType: form.optionType, lots: form.lots, strikeCriteria: 'atm_offset', strikeValue: contract.strike })],
      ...(activeBroker ? { broker: activeBroker.broker } : {}),
    }).then(d => {
      if (marginSeq.current !== seq) return
      const r = d as unknown as MarginResp
      setMargin({ span: r.span_margin || 0, exposure: r.exposure_margin || 0, total: r.total_margin || 0 })
    }).catch(() => {
      if (marginSeq.current === seq) setMargin(null)
    }).finally(() => {
      if (marginSeq.current === seq) setMarginLoading(false)
    })
  }, [token, index, contract.strike, form.optionType, form.lots, form.expiry, activeBroker])

  // ---- quote for selected contract ----
  const selectedRow = chain.optionChain.find(r => r.strike === contract.strike)
  const ltp = selectedRow ? (form.optionType === 'CE' ? selectedRow.call.ltp : selectedRow.put.ltp) : 0

  // ---- live toggle ----
  const handleToggleLive = async () => {
    if (mode === 'live') { setMode('paper'); return }
    try {
      const status = await api.risk.liveStatus() as { is_live: boolean }
      if (status.is_live) setMode('live')
      else setConfirmingLive(true)
    } catch {
      setConfirmingLive(true)
    }
  }

  const confirmLive = async () => {
    try {
      await api.risk.enableLive()
      setMode('live')
      setConfirmingLive(false)
    } catch (e) {
      setOrderError(String(e))
      setConfirmingLive(false)
    }
  }

  // ---- place ----
  const handlePlace = async (side: 'BUY' | 'SELL') => {
    if (!contract.strike || !contract.symbol || !form.expiry) return
    setPlacing(true)
    setOrderResult(null)
    setOrderError('')
    try {
      const res = await api.engine.trade({
        symbol: contract.symbol,
        side,
        quantity: contract.quantity,
        price: form.orderType === 'LIMIT' ? form.limitPrice : 0,
        exchange: 'NFO',
        order_type: form.orderType,
        product: mode === 'live' ? 'NRML' : 'INTRADAY',
        instrument_type: 'OPT',
        strike_price: contract.strike,
        expiry_date: form.expiry,
        option_type: form.optionType,
        is_paper: mode === 'paper',
        source: 'manual',
      }) as { result: OrderResult }
      setOrderResult(res.result)
    } catch (e) {
      setOrderError(String(e))
    } finally {
      setPlacing(false)
    }
  }

  // ---- presets ----
  const applyPreset = (p: { index: IndexKey; moneyness: Moneyness; customStrike: number | null; optionType: 'CE' | 'PE'; lots: number; orderType: 'MARKET' | 'LIMIT' }) => {
    onIndexChange(p.index)
    setForm(f => ({ ...f, index: p.index, moneyness: p.moneyness, customStrike: p.customStrike, optionType: p.optionType, lots: p.lots, orderType: p.orderType, expiry: '' }))
  }

  const presetCurrent = useMemo(() => ({
    name: '',
    index,
    moneyness: form.moneyness,
    customStrike: form.customStrike,
    optionType: form.optionType,
    lots: form.lots,
    orderType: form.orderType,
  }), [index, form.moneyness, form.customStrike, form.optionType, form.lots, form.orderType])

  // ---- chain metrics (PCR / Max Pain from OI) ----
  const metrics = useMemo<ChainMetrics>(() => {
    const rows = chain.optionChain
    if (!rows.length) return { pcr: null, maxPain: null }
    const callOi = rows.reduce((s, r) => s + r.call.oi, 0)
    const putOi = rows.reduce((s, r) => s + r.put.oi, 0)
    const pcr = callOi > 0 ? putOi / callOi : null
    const maxStrike = rows.reduce((a, b) => (a.call.oi + a.put.oi) >= (b.call.oi + b.put.oi) ? a : b)
    return { pcr, maxPain: maxStrike.call.oi + maxStrike.put.oi > 0 ? maxStrike.strike : null }
  }, [chain.optionChain])

  const loadFills = useCallback(async (limit: number): Promise<Fill[]> => {
    const d = await api.paper.trades(limit) as { trades: Fill[] }
    return d.trades || []
  }, [])

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Trade Desk</h1>
          <p className="page-subtitle">Index options execution — NIFTY · BANKNIFTY · FINNIFTY · MIDCPNIFTY · SENSEX</p>
        </div>
      </div>

      {credsLoading && (
        <div className="t-panel" style={{ padding: '10px 16px', marginBottom: 12 }}>
          <div className="t-faint" style={{ fontSize: 10 }}>Loading broker…</div>
        </div>
      )}
      {credsError && <div className="alert alert-error" style={{ marginBottom: 12 }}>{credsError}</div>}
      {!credsLoading && (
        <div className="t-panel" style={{ marginBottom: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', padding: '8px 12px' }}>
            <span className="t-faint" style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.08em' }}>BROKER</span>
            {creds.length === 0 && (
              <span className="t-faint" style={{ fontSize: 11 }}>No brokers connected — paper orders work without one. Add credentials for live orders.</span>
            )}
            {creds.map(c => (
              <button
                key={c.broker}
                className={`t-btn t-btn-sm ${c.is_active ? 't-btn-primary' : 't-btn-ghost'}`}
                onClick={() => !c.is_active && api.brokers.activate(c.broker).then(loadCreds).catch(e => setCredsError(String(e)))}
                disabled={c.is_active}
              >
                {c.is_active && <span className="live-dot active" />}
                {c.broker}
              </button>
            ))}
          </div>
        </div>
      )}

      <PresetsBar
        current={presetCurrent}
        onApply={applyPreset}
      />

      <div style={{ marginBottom: 12 }}>
        <IndexStrip index={index} onIndexChange={onIndexChange} spot={spot} changePct={changePct} connected={connected} />
      </div>

      {chainError && <div className="alert alert-error" style={{ marginBottom: 12 }}>{chainError}</div>}
      {chainLoading && (
        <div className="t-panel" style={{ padding: 14 }}>
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} style={{ height: 14, marginBottom: 8, borderRadius: 6, background: 'color-mix(in srgb, var(--violet) 10%, transparent)' }} />
          ))}
        </div>
      )}

      {!chainLoading && !chainError && (
        <div className="t-trade-grid" style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 320px', gap: 12, alignItems: 'start' }}>
          <div>
            <div style={{ marginBottom: 8, display: 'flex', alignItems: 'center', gap: 8 }}>
              {!liveSource && chain.optionChain.length > 0 && (
                <span className="t-badge t-badge-amber" style={{ fontSize: 9 }}>SIMULATED</span>
              )}
              <span className="t-faint" style={{ fontSize: 10 }}>
                {chain.optionChain.length} strikes · {chain.expiries.length} expiries
              </span>
            </div>
            {chain.optionChain.length > 0 ? (
              <ChainPanel
                rows={chain.optionChain}
                metrics={metrics}
                spot={spot}
                selectedStrike={contract.strike}
                selectedSide={form.optionType}
                onSelectStrike={s => setForm(f => ({ ...f, moneyness: 'CUSTOM', customStrike: s }))}
                onSelectSide={(s, side) => setForm(f => ({ ...f, moneyness: 'CUSTOM', customStrike: s, optionType: side }))}
                notionalLots={form.lots}
              />
            ) : (
              <div className="t-panel" style={{ padding: 24, textAlign: 'center' }}>
                <p style={{ margin: 0, fontSize: 12, color: 'var(--t-faint)' }}>No option chain data available for {index}.</p>
              </div>
            )}
            <FillsTicker load={loadFills} />
          </div>

          <div className="t-trade-order-card" style={{ position: 'sticky', top: 12 }}>
            <OrderCard
              form={form}
              onChange={p => setForm(f => ({ ...f, ...p }))}
              chain={chain.optionChain.length ? chain : null}
              spot={spot}
              ltp={ltp > 0 ? ltp : null}
              lotSize={lotSize || meta.fallbackLot}
              margin={margin}
              marginLoading={marginLoading}
              mode={mode}
              onMode={m => {
                if (m === 'paper') { setMode('paper'); return }
                handleToggleLive()
              }}
              onPlace={handlePlace}
            />

            {confirmingLive && (
              <div style={{ marginTop: 10, background: 'color-mix(in srgb, var(--red) 8%, transparent)', border: '1px solid color-mix(in srgb, var(--red) 20%, transparent)', borderRadius: 8, padding: '10px 12px' }}>
                <p style={{ margin: '0 0 8px', fontSize: 11, color: 'var(--red)', fontWeight: 500 }}>
                  Live trading is not enabled. Enable live mode to place real orders?
                </p>
                <div style={{ display: 'flex', gap: 6 }}>
                  <button className="t-btn t-btn-sm t-btn-danger" onClick={confirmLive}>Enable Live</button>
                  <button className="t-btn t-btn-sm t-btn-ghost" onClick={() => setConfirmingLive(false)}>Cancel</button>
                </div>
              </div>
            )}

            {orderError && <div className="alert alert-error" style={{ marginBottom: 12, marginTop: 10 }}>{orderError}</div>}
            {orderResult && (
              <div className={`alert ${orderResult.success ? 'alert-success' : 'alert-error'}`} style={{ marginTop: 10 }}>
                <div style={{ fontSize: 11 }}>
                  {orderResult.success ? 'Order placed successfully' : 'Order rejected'}
                  {orderResult.broker_order_id && <span style={{ display: 'block', fontSize: 10, color: 'var(--t-faint)', marginTop: 2 }}>ID: {orderResult.broker_order_id}</span>}
                  {orderResult.message && <span style={{ display: 'block', fontSize: 10, marginTop: 2 }}>{orderResult.message}</span>}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// Lot size resolve (one-shot, api.get-based like all marketdata reads).
async function fetchLotSizeOnce(index: IndexKey): Promise<number> {
  try {
    const d = await api.get<{ instruments?: { symbol?: string; lot_size?: number }[] }>(
      `/marketdata/instruments?query=${encodeURIComponent(index)}&instrument_type=OPT&limit=20`,
    )
    const list = d.instruments || []
    const found = list.find(i => (i.lot_size || 0) > 1) || list.find(i => (i.symbol || '').toUpperCase().startsWith(index))
    if (found?.lot_size && found.lot_size > 1) return found.lot_size
  } catch { /* fall through */ }
  return indexMeta(index).fallbackLot
}