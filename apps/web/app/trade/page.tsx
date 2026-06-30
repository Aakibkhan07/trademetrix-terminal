'use client'

import { useState, useEffect, useCallback } from 'react'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'

/* -------- Types -------- */

interface BrokerCred {
  id: string
  broker: string
  is_active: boolean
  created_at: string
}

interface OptionRow {
  strike: number
  call: { ltp: number; bid: number; ask: number; volume: number; oi: number; iv: number }
  put: { ltp: number; bid: number; ask: number; volume: number; oi: number; iv: number }
}

interface ChainResponse {
  optionChain: OptionRow[]
  expiries: string[]
}

interface OrderResult {
  success: boolean
  broker_order_id: string
  message: string
  status: string
}

/* -------- Constants -------- */

const UNDERLYING = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'SENSEX']

function fmt(n: number) {
  return n.toLocaleString('en-IN', { minimumFractionDigits: 0, maximumFractionDigits: 2 })
}

/* -------- Skeleton helpers -------- */

function SkeletonLine({ w, h = 12 }: { w: string; h?: number }) {
  return <div style={{ width: w, height: h, background: 'rgba(139,92,246,0.08)', borderRadius: 4 }} />
}

function SkeletonBar() {
  return (
    <div className="panel" style={{ padding: '10px 16px', display: 'flex', gap: 12, marginBottom: 16 }}>
      <SkeletonLine w="80px" h={28} />
      <SkeletonLine w="80px" h={28} />
      <SkeletonLine w="80px" h={28} />
    </div>
  )
}

function SkeletonTable() {
  return (
    <div className="panel" style={{ padding: 14 }}>
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} style={{ display: 'flex', gap: 16, padding: '6px 0', borderBottom: '1px solid rgba(255,255,255,0.03)' }}>
          <SkeletonLine w="50px" />
          <SkeletonLine w="80px" />
          <SkeletonLine w="80px" />
          <SkeletonLine w="80px" />
          <SkeletonLine w="80px" />
          <SkeletonLine w="60px" />
        </div>
      ))}
    </div>
  )
}

/* -------- Main page -------- */

export default function TradePage() {
  const { token } = useAuth()

  const [creds, setCreds] = useState<BrokerCred[]>([])
  const [credsLoading, setCredsLoading] = useState(true)
  const [credsError, setCredsError] = useState('')

  const [underlying, setUnderlying] = useState('NIFTY')
  const [chain, setChain] = useState<OptionRow[]>([])
  const [expiries, setExpiries] = useState<string[]>([])
  const [expiry, setExpiry] = useState('')
  const [chainLoading, setChainLoading] = useState(false)
  const [chainError, setChainError] = useState('')
  const [liveSource, setLiveSource] = useState(false)

  const [selectedStrike, setSelectedStrike] = useState<number | null>(null)
  const [selectedSide, setSelectedSide] = useState<'CE' | 'PE' | null>(null)
  const [orderQty, setOrderQty] = useState(1)
  const [orderPrice, setOrderPrice] = useState(0)
  const [orderType, setOrderType] = useState<'MARKET' | 'LIMIT'>('MARKET')
  const [isLiveMode, setIsLiveMode] = useState(false)
  const [placing, setPlacing] = useState(false)
  const [orderResult, setOrderResult] = useState<OrderResult | null>(null)
  const [orderError, setOrderError] = useState('')
  const [confirmingLive, setConfirmingLive] = useState(false)

  const activeBroker = creds.find(c => c.is_active)

  /* Load broker credentials */
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

  /* Load option chain */
  const loadChain = useCallback(async (sym: string) => {
    setChainLoading(true)
    setChainError('')
    try {
      const d = await api.marketdata.optionChain(sym) as ChainResponse
      const exps = d.expiries || []
      const rows = d.optionChain || []
      if (!rows.length) {
        setChainError('Empty response from server')
        return
      }
      setChain(rows)
      setExpiries(exps)
      if (exps.length && !exps.includes(expiry)) setExpiry(exps[0])
      const hasPrices = rows.some(r => r.call.ltp > 0 || r.put.ltp > 0)
      setLiveSource(hasPrices)
    } catch (e) {
      setChainError(String(e))
    } finally {
      setChainLoading(false)
    }
  }, [expiry])

  useEffect(() => { if (token) loadChain(underlying) }, [token, underlying])

  /* Activate broker */
  const handleActivate = async (broker: string) => {
    try {
      await api.brokers.activate(broker)
      await loadCreds()
    } catch (e) {
      setCredsError(String(e))
    }
  }

  /* Open order ticket */
  const openOrder = (strike: number, side: 'CE' | 'PE') => {
    setSelectedStrike(strike)
    setSelectedSide(side)
    setOrderQty(1)
    setOrderPrice(0)
    setOrderType('MARKET')
    setOrderResult(null)
    setOrderError('')
    setConfirmingLive(false)
  }

  const selectedRow = chain.find(r => r.strike === selectedStrike)
  const selectedQuote = selectedSide === 'CE' ? selectedRow?.call : selectedRow?.put

  /* Check live status + confirm */
  const handleToggleLive = async () => {
    if (isLiveMode) {
      setIsLiveMode(false)
      return
    }
    try {
      const status = await api.risk.liveStatus() as { is_live: boolean }
      if (status.is_live) {
        setIsLiveMode(true)
      } else {
        setConfirmingLive(true)
      }
    } catch {
      setConfirmingLive(true)
    }
  }

  const confirmLive = async () => {
    try {
      await api.risk.enableLive()
      setIsLiveMode(true)
      setConfirmingLive(false)
    } catch (e) {
      setOrderError(String(e))
      setConfirmingLive(false)
    }
  }

  /* Place order */
  const handlePlace = async () => {
    if (!selectedStrike || !selectedSide || !expiry) return
    setPlacing(true)
    setOrderResult(null)
    setOrderError('')

    const optionSymbol = `${underlying}${expiry}${selectedStrike}${selectedSide}`

    try {
      const res = await api.engine.trade({
        symbol: optionSymbol,
        side: selectedSide === 'CE' ? 'BUY' : 'SELL',
        quantity: orderQty,
        price: orderType === 'LIMIT' ? orderPrice : 0,
        exchange: 'NFO',
        order_type: orderType,
        product: isLiveMode ? 'NRML' : 'INTRADAY',
        instrument_type: 'OPT',
        strike_price: selectedStrike,
        expiry_date: expiry,
        option_type: selectedSide,
      }) as { result: OrderResult }

      setOrderResult(res.result)
      if (res.result.success) {
        setSelectedStrike(null)
        setSelectedSide(null)
      }
    } catch (e) {
      setOrderError(String(e))
    } finally {
      setPlacing(false)
    }
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Trade Desk</h1>
          <p className="page-subtitle">Manual order placement via broker</p>
        </div>
      </div>

      {/* Broker bar */}
      {credsLoading && <SkeletonBar />}
      {credsError && <div className="alert alert-error" style={{ marginBottom: 12 }}>{credsError}</div>}
      {!credsLoading && (
        <div className="panel" style={{ padding: '10px 16px', marginBottom: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 11, color: '#555570', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Broker</span>
            {creds.length === 0 && (
              <span style={{ fontSize: 12, color: '#555570' }}>No brokers connected. Go to Brokers page to add credentials.</span>
            )}
            {creds.map(c => (
              <button
                key={c.broker}
                className={`btn btn-sm ${c.is_active ? 'btn-cyan' : 'btn-secondary'}`}
                onClick={() => !c.is_active && handleActivate(c.broker)}
                style={{ fontSize: 11, textTransform: 'capitalize' }}
                disabled={c.is_active}
              >
                {c.is_active && <span className="live-dot active" />}
                {c.broker}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Underlying selector */}
      <div className="panel" style={{ padding: '10px 16px', marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <span style={{ fontSize: 11, color: '#555570', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Underlying</span>
          {UNDERLYING.map(s => (
            <button
              key={s}
              className={`btn btn-sm ${underlying === s ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => { setUnderlying(s); setSelectedStrike(null); setSelectedSide(null) }}
              style={{ fontSize: 11 }}
            >
              {s}
            </button>
          ))}
          {expiries.length > 0 && (
            <>
              <span style={{ fontSize: 11, color: '#555570', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', marginLeft: 8 }}>Expiry</span>
              <select className="select" value={expiry} onChange={e => setExpiry(e.target.value)} style={{ maxWidth: 120, fontSize: 11 }}>
                {expiries.map(e => <option key={e} value={e}>{e}</option>)}
              </select>
            </>
          )}
          {!liveSource && chain.length > 0 && (
            <span style={{ fontSize: 10, color: '#f59e0b', marginLeft: 8 }}>
              Live quotes coming soon — prices shown may be simulated
            </span>
          )}
          {chain.length > 0 && (
            <span style={{ fontSize: 10, color: '#555570', marginLeft: 'auto' }}>
              {chain.length} strikes
            </span>
          )}
        </div>
      </div>

      {/* Error / Loading */}
      {chainError && <div className="alert alert-error" style={{ marginBottom: 12 }}>{chainError}</div>}
      {chainLoading && <SkeletonTable />}

      {/* Option chain table */}
      {!chainLoading && !chainError && chain.length > 0 && (
        <div className="panel" style={{ padding: 0, overflow: 'hidden', marginBottom: 16 }}>
          <table className="data-table" style={{ fontSize: 11 }}>
            <thead>
              <tr>
                <th style={{ textAlign: 'center', width: 90 }}>CALL LTP</th>
                <th style={{ textAlign: 'center', width: 60 }}>Bid</th>
                <th style={{ textAlign: 'center', width: 60 }}>Ask</th>
                <th style={{ textAlign: 'center', width: 60 }}>Vol</th>
                <th style={{ textAlign: 'center', width: 70 }}>STRIKE</th>
                <th style={{ textAlign: 'center', width: 60 }}>Vol</th>
                <th style={{ textAlign: 'center', width: 60 }}>Bid</th>
                <th style={{ textAlign: 'center', width: 60 }}>Ask</th>
                <th style={{ textAlign: 'center', width: 90 }}>PUT LTP</th>
              </tr>
            </thead>
            <tbody>
              {chain.map(r => {
                const isSelected = selectedStrike === r.strike
                return (
                  <tr key={r.strike}
                    onClick={() => openOrder(r.strike, r.call.ltp > 0 ? 'CE' : 'CE')}
                    style={{ cursor: 'pointer', background: isSelected ? 'rgba(139,92,246,0.06)' : undefined }}
                  >
                    {/* CALL */}
                    <td style={{ textAlign: 'center' }}>
                      <button
                        className="btn btn-sm"
                        onClick={(e) => { e.stopPropagation(); openOrder(r.strike, 'CE') }}
                        style={{
                          fontSize: 10, padding: '1px 8px',
                          background: selectedStrike === r.strike && selectedSide === 'CE' ? 'rgba(34,211,238,0.15)' : 'transparent',
                          color: r.call.ltp > 0 ? '#22d3ee' : '#555570',
                          border: `1px solid ${selectedStrike === r.strike && selectedSide === 'CE' ? 'rgba(34,211,238,0.3)' : 'transparent'}`,
                          width: '100%',
                        }}
                      >
                        {r.call.ltp > 0 ? fmt(r.call.ltp) : '\u2014'}
                      </button>
                    </td>
                    <td style={{ textAlign: 'center', color: r.call.bid > 0 ? '#aaaac0' : '#555570' }}>{r.call.bid > 0 ? fmt(r.call.bid) : '\u2014'}</td>
                    <td style={{ textAlign: 'center', color: r.call.ask > 0 ? '#aaaac0' : '#555570' }}>{r.call.ask > 0 ? fmt(r.call.ask) : '\u2014'}</td>
                    <td style={{ textAlign: 'center', color: '#555570', fontSize: 10 }}>{r.call.volume || '\u2014'}</td>
                    {/* STRIKE */}
                    <td style={{ textAlign: 'center', fontWeight: 700, color: '#f0f0f5' }}>{r.strike}</td>
                    {/* PUT */}
                    <td style={{ textAlign: 'center', color: '#555570', fontSize: 10 }}>{r.put.volume || '\u2014'}</td>
                    <td style={{ textAlign: 'center', color: r.put.bid > 0 ? '#aaaac0' : '#555570' }}>{r.put.bid > 0 ? fmt(r.put.bid) : '\u2014'}</td>
                    <td style={{ textAlign: 'center', color: r.put.ask > 0 ? '#aaaac0' : '#555570' }}>{r.put.ask > 0 ? fmt(r.put.ask) : '\u2014'}</td>
                    <td style={{ textAlign: 'center' }}>
                      <button
                        className="btn btn-sm"
                        onClick={(e) => { e.stopPropagation(); openOrder(r.strike, 'PE') }}
                        style={{
                          fontSize: 10, padding: '1px 8px',
                          background: selectedStrike === r.strike && selectedSide === 'PE' ? 'rgba(239,68,68,0.15)' : 'transparent',
                          color: r.put.ltp > 0 ? '#ef4444' : '#555570',
                          border: `1px solid ${selectedStrike === r.strike && selectedSide === 'PE' ? 'rgba(239,68,68,0.3)' : 'transparent'}`,
                          width: '100%',
                        }}
                      >
                        {r.put.ltp > 0 ? fmt(r.put.ltp) : '\u2014'}
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {!chainLoading && !chainError && chain.length === 0 && (
        <div className="panel" style={{ padding: 20, textAlign: 'center' }}>
          <p style={{ margin: 0, fontSize: 13, color: '#555570' }}>
            No option chain data available for {underlying}.
          </p>
        </div>
      )}

      {/* Order ticket */}
      {selectedStrike && selectedSide && (
        <div className="panel" style={{ padding: 16, maxWidth: 420 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <h3 style={{ fontFamily: 'Outfit', fontSize: 14, margin: 0 }}>
              {underlying}{expiry}{selectedStrike}{selectedSide}
            </h3>
            <button className="btn btn-sm btn-ghost" onClick={() => { setSelectedStrike(null); setSelectedSide(null) }} style={{ fontSize: 11 }}>
              Clear
            </button>
          </div>

          {selectedQuote && (
            <div style={{ display: 'flex', gap: 12, marginBottom: 12, fontSize: 11 }}>
              <div>
                <span style={{ color: '#555570' }}>LTP</span>
                <p style={{ margin: '2px 0 0', fontWeight: 600 }}>
                  {selectedQuote.ltp > 0 ? `\u20B9${fmt(selectedQuote.ltp)}` : '\u2014'}
                </p>
              </div>
              <div>
                <span style={{ color: '#555570' }}>Bid/Ask</span>
                <p style={{ margin: '2px 0 0', fontWeight: 600 }}>
                  {selectedQuote.bid > 0 || selectedQuote.ask > 0
                    ? `\u20B9${fmt(selectedQuote.bid)} / \u20B9${fmt(selectedQuote.ask)}`
                    : '\u2014'}
                </p>
              </div>
              <div>
                <span style={{ color: '#555570' }}>IV</span>
                <p style={{ margin: '2px 0 0', fontWeight: 600 }}>{selectedQuote.iv > 0 ? `${selectedQuote.iv}%` : '\u2014'}</p>
              </div>
            </div>
          )}

          <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
            <div style={{ flex: 1 }}>
              <label style={{ color: '#555570', fontSize: 10, display: 'block', marginBottom: 2 }}>Side</label>
              <span style={{ fontSize: 13, fontWeight: 700, color: selectedSide === 'CE' ? '#22d3ee' : '#ef4444' }}>
                {selectedSide === 'CE' ? 'BUY' : 'SELL'}
              </span>
            </div>
            <div style={{ flex: 1 }}>
              <label style={{ color: '#555570', fontSize: 10, display: 'block', marginBottom: 2 }}>Qty</label>
              <input className="input" type="number" min={1} value={orderQty} onChange={e => setOrderQty(Number(e.target.value))} style={{ fontSize: 12, padding: '4px 8px' }} />
            </div>
            <div style={{ flex: 1 }}>
              <label style={{ color: '#555570', fontSize: 10, display: 'block', marginBottom: 2 }}>Type</label>
              <select className="select" value={orderType} onChange={e => setOrderType(e.target.value as 'MARKET' | 'LIMIT')} style={{ fontSize: 12, padding: '4px 8px' }}>
                <option value="MARKET">Market</option>
                <option value="LIMIT">Limit</option>
              </select>
            </div>
          </div>

          {orderType === 'LIMIT' && (
            <div style={{ marginBottom: 12 }}>
              <label style={{ color: '#555570', fontSize: 10, display: 'block', marginBottom: 2 }}>Limit Price</label>
              <input className="input" type="number" min={0} step={0.05} value={orderPrice} onChange={e => setOrderPrice(Number(e.target.value))} style={{ fontSize: 12, padding: '4px 8px' }} />
            </div>
          )}

          {/* Paper / Live toggle */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
            <span style={{ fontSize: 10, color: '#555570', fontWeight: 600 }}>Mode</span>
            <button
              className={`btn btn-sm ${!isLiveMode ? 'btn-success' : 'btn-secondary'}`}
              onClick={() => isLiveMode && setIsLiveMode(false)}
              style={{ fontSize: 10, opacity: !isLiveMode ? 1 : 0.5 }}
              disabled={!isLiveMode}
            >
              PAPER
            </button>
            <button
              className={`btn btn-sm ${isLiveMode ? 'btn-danger' : 'btn-secondary'}`}
              onClick={handleToggleLive}
              style={{ fontSize: 10, opacity: isLiveMode ? 1 : 0.5 }}
            >
              LIVE
            </button>
            {activeBroker && (
              <span style={{ fontSize: 10, color: '#555570', marginLeft: 'auto' }}>
                via {activeBroker.broker}
              </span>
            )}
          </div>

          {/* Confirm live dialog */}
          {confirmingLive && (
            <div style={{
              background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)',
              borderRadius: 8, padding: '10px 12px', marginBottom: 12,
            }}>
              <p style={{ margin: '0 0 8px', fontSize: 11, color: '#ef4444', fontWeight: 500 }}>
                Live trading is not enabled. Enable live mode to place real orders?
              </p>
              <div style={{ display: 'flex', gap: 6 }}>
                <button className="btn btn-sm btn-danger" onClick={confirmLive} style={{ fontSize: 10 }}>
                  Enable Live
                </button>
                <button className="btn btn-sm btn-secondary" onClick={() => setConfirmingLive(false)} style={{ fontSize: 10 }}>
                  Cancel
                </button>
              </div>
            </div>
          )}

          {orderError && (
            <div className="alert alert-error" style={{ marginBottom: 12 }}>
              {orderError}
            </div>
          )}

          {orderResult && (
            <div className={`alert ${orderResult.success ? 'alert-success' : 'alert-error'}`} style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 11 }}>
                {orderResult.success ? 'Order placed successfully' : 'Order rejected'}
                {orderResult.broker_order_id && <span style={{ display: 'block', fontSize: 10, color: '#555570', marginTop: 2 }}>ID: {orderResult.broker_order_id}</span>}
                {orderResult.message && <span style={{ display: 'block', fontSize: 10, marginTop: 2 }}>{orderResult.message}</span>}
              </div>
            </div>
          )}

          <button
            className={`btn ${isLiveMode ? 'btn-danger' : 'btn-primary'}`}
            onClick={handlePlace}
            disabled={placing}
            style={{ width: '100%', fontSize: 12 }}
          >
            {placing ? 'Placing...' : `${isLiveMode ? 'LIVE ' : ''}Place ${selectedSide === 'CE' ? 'BUY' : 'SELL'} ${underlying}${expiry}${selectedStrike}${selectedSide}`}
          </button>
        </div>
      )}
    </div>
  )
}
