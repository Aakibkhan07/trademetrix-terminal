'use client'

import { useState, useEffect, useCallback } from 'react'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'

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

const UNDERLYING = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'SENSEX']

function fmt(n: number) {
  return n.toLocaleString('en-IN', { minimumFractionDigits: 0, maximumFractionDigits: 2 })
}

function SkeletonLine({ w, h = 12 }: { w: string; h?: number }) {
  return <div style={{ width: w, height: h, background: 'rgba(139,92,246,0.08)', borderRadius: 4 }} />
}

function SkeletonBar() {
  return (
    <div className="t-panel" style={{ padding: '10px 16px', display: 'flex', gap: 12, marginBottom: 16 }}>
      <SkeletonLine w="80px" h={28} />
      <SkeletonLine w="80px" h={28} />
      <SkeletonLine w="80px" h={28} />
    </div>
  )
}

function SkeletonTable() {
  return (
    <div className="t-panel" style={{ padding: 14 }}>
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

  const handleActivate = async (broker: string) => {
    try {
      await api.brokers.activate(broker)
      await loadCreds()
    } catch (e) {
      setCredsError(String(e))
    }
  }

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

      {credsLoading && <SkeletonBar />}
      {credsError && <div className="alert alert-error" style={{ marginBottom: 12 }}>{credsError}</div>}
      {!credsLoading && (
        <div className="t-panel" style={{ marginBottom: 16 }}>
          <div className="t-panel-body" style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
            <span className="t-faint" style={{ fontSize: 10, fontWeight: 600, letterSpacing: '0.08em' }}>BROKER</span>
            {creds.length === 0 && (
              <span className="t-faint" style={{ fontSize: 11 }}>No brokers connected. Go to Brokers page to add credentials.</span>
            )}
            {creds.map(c => (
              <button
                key={c.broker}
                className={`t-btn t-btn-sm ${c.is_active ? 't-btn-primary' : 't-btn-ghost'}`}
                onClick={() => !c.is_active && handleActivate(c.broker)}
                disabled={c.is_active}
              >
                {c.is_active && <span className="live-dot active" />}
                {c.broker}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="t-panel" style={{ marginBottom: 16 }}>
        <div className="t-panel-body" style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <span className="t-faint" style={{ fontSize: 10, fontWeight: 600, letterSpacing: '0.08em' }}>UNDERLYING</span>
          {UNDERLYING.map(s => (
            <button
              key={s}
              className={`t-btn t-btn-sm ${underlying === s ? 't-btn-primary' : 't-btn-ghost'}`}
              onClick={() => { setUnderlying(s); setSelectedStrike(null); setSelectedSide(null) }}
            >
              {s}
            </button>
          ))}
          {expiries.length > 0 && (
            <>
              <span className="t-faint" style={{ fontSize: 10, fontWeight: 600, letterSpacing: '0.08em', marginLeft: 12 }}>EXPIRY</span>
              <select className="t-select" value={expiry} onChange={e => setExpiry(e.target.value)} style={{ maxWidth: 120 }}>
                {expiries.map(e => <option key={e} value={e}>{e}</option>)}
              </select>
            </>
          )}
          {!liveSource && chain.length > 0 && (
            <span className="t-badge t-badge-amber" style={{ marginLeft: 8, fontSize: 9 }}>
              SIMULATED
            </span>
          )}
          {chain.length > 0 && (
            <span className="t-faint" style={{ marginLeft: 'auto', fontSize: 10 }}>
              {chain.length} strikes
            </span>
          )}
        </div>
      </div>

      {chainError && <div className="alert alert-error" style={{ marginBottom: 12 }}>{chainError}</div>}
      {chainLoading && <SkeletonTable />}

      {!chainLoading && !chainError && chain.length > 0 && (
        <div className="t-panel" style={{ marginBottom: 16 }}>
          <div className="t-table-wrap">
            <table className="t-table" style={{ fontSize: 10 }}>
              <thead>
                <tr>
                  <th className="t-faint" style={{ textAlign: 'right', paddingRight: 4 }}>CALL</th>
                  <th style={{ textAlign: 'right', width: 60 }}>LTP</th>
                  <th style={{ textAlign: 'right', width: 50 }}>Bid</th>
                  <th style={{ textAlign: 'right', width: 50 }}>Ask</th>
                  <th style={{ textAlign: 'right', width: 40 }}>Vol</th>
                  <th style={{ textAlign: 'right', width: 40 }}>OI</th>
                  <th style={{ textAlign: 'center', width: 64, borderLeft: '1px solid rgba(255,255,255,0.06)', borderRight: '1px solid rgba(255,255,255,0.06)' }} className="t-faint">STRIKE</th>
                  <th style={{ textAlign: 'left', width: 40 }}>OI</th>
                  <th style={{ textAlign: 'left', width: 40 }}>Vol</th>
                  <th style={{ textAlign: 'left', width: 50 }}>Bid</th>
                  <th style={{ textAlign: 'left', width: 50 }}>Ask</th>
                  <th style={{ textAlign: 'left', width: 60 }}>LTP</th>
                  <th className="t-faint" style={{ textAlign: 'left', paddingLeft: 4 }}>PUT</th>
                </tr>
              </thead>
              <tbody>
                {chain.map(r => {
                  const isSelected = selectedStrike === r.strike
                  return (
                    <tr key={r.strike}
                      onClick={() => openOrder(r.strike, r.call.ltp > r.put.ltp ? 'CE' : 'PE')}
                      className={isSelected ? 'selected' : undefined}
                      style={{ cursor: 'pointer' }}
                    >
                      <td colSpan={6} style={{ padding: 0 }}>
                        <div style={{ display: 'flex', width: '100%', gap: 0, alignItems: 'center' }}>
                          <button
                            className={`t-btn t-btn-sm ${selectedStrike === r.strike && selectedSide === 'CE' ? 't-btn-primary' : 't-btn-ghost'}`}
                            onClick={(e) => { e.stopPropagation(); openOrder(r.strike, 'CE') }}
                            style={{
                              flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 4,
                              padding: '2px 4px', minWidth: 0,
                            }}
                          >
                            <span className={r.call.ltp > 0 ? 't-num t-up' : 't-faint'} style={{ fontSize: 11 }}>
                              {r.call.ltp > 0 ? fmt(r.call.ltp) : '\u2014'}
                            </span>
                            <span className="t-faint" style={{ fontSize: 9, width: 20, textAlign: 'right' }}>
                              {r.call.iv > 0 ? `${r.call.iv}%` : '\u2014'}
                            </span>
                          </button>
                        </div>
                      </td>
                      <td style={{ textAlign: 'center', fontWeight: 700, borderLeft: '1px solid rgba(255,255,255,0.06)', borderRight: '1px solid rgba(255,255,255,0.06)', padding: '4px 0' }}>
                        {r.strike}
                      </td>
                      <td colSpan={6} style={{ padding: 0 }}>
                        <div style={{ display: 'flex', width: '100%', gap: 0, alignItems: 'center' }}>
                          <button
                            className={`t-btn t-btn-sm ${selectedStrike === r.strike && selectedSide === 'PE' ? 't-btn-danger' : 't-btn-ghost'}`}
                            onClick={(e) => { e.stopPropagation(); openOrder(r.strike, 'PE') }}
                            style={{
                              flex: 1, display: 'flex', alignItems: 'center', gap: 4,
                              padding: '2px 4px', minWidth: 0,
                            }}
                          >
                            <span className="t-faint" style={{ fontSize: 9, width: 20 }}>
                              {r.put.iv > 0 ? `${r.put.iv}%` : '\u2014'}
                            </span>
                            <span className={r.put.ltp > 0 ? 't-num t-down' : 't-faint'} style={{ fontSize: 11 }}>
                              {r.put.ltp > 0 ? fmt(r.put.ltp) : '\u2014'}
                            </span>
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {!chainLoading && !chainError && chain.length === 0 && (
        <div className="t-panel" style={{ padding: 24, textAlign: 'center' }}>
          <p style={{ margin: 0, fontSize: 12, color: 'var(--t-faint)' }}>
            No option chain data available for {underlying}.
          </p>
        </div>
      )}

      {selectedStrike && selectedSide && (
        <div className="t-panel" style={{ maxWidth: 420, borderTop: `3px solid ${selectedSide === 'CE' ? '#22c55e' : '#ef4444'}` }}>
          <div className="t-panel-header">
            <span className="t-panel-title" style={{ fontSize: 12 }}>
              <span className={selectedSide === 'CE' ? 't-badge t-badge-green' : 't-badge t-badge-red'} style={{ fontSize: 9, marginRight: 6 }}>
                {selectedSide === 'CE' ? 'BUY' : 'SELL'}
              </span>
              {underlying}{expiry}{selectedStrike}{selectedSide}
            </span>
            <button className="t-btn t-btn-sm t-btn-ghost" onClick={() => { setSelectedStrike(null); setSelectedSide(null) }}>
              Clear
            </button>
          </div>
          <div className="t-panel-body">
            {selectedQuote && (
              <div className="t-row" style={{ gap: 16, marginBottom: 12 }}>
                <div className="t-col">
                  <span className="t-faint" style={{ fontSize: 10 }}>LTP</span>
                  <div className="t-num" style={{ fontSize: 16, fontWeight: 700, color: selectedSide === 'CE' ? '#22c55e' : '#ef4444' }}>
                    {selectedQuote.ltp > 0 ? `\u20B9${fmt(selectedQuote.ltp)}` : '\u2014'}
                  </div>
                </div>
                <div className="t-col">
                  <span className="t-faint" style={{ fontSize: 10 }}>Bid/Ask</span>
                  <div style={{ fontSize: 13, fontWeight: 600 }}>
                    {selectedQuote.bid > 0 || selectedQuote.ask > 0
                      ? `\u20B9${fmt(selectedQuote.bid)} / \u20B9${fmt(selectedQuote.ask)}`
                      : '\u2014'}
                  </div>
                </div>
                <div className="t-col">
                  <span className="t-faint" style={{ fontSize: 10 }}>IV</span>
                  <div style={{ fontSize: 13, fontWeight: 600 }}>{selectedQuote.iv > 0 ? `${selectedQuote.iv}%` : '\u2014'}</div>
                </div>
              </div>
            )}

            <div className="t-row" style={{ gap: 8, marginBottom: 12 }}>
              <div className="t-col">
                <label className="t-label">Side</label>
                <span style={{ fontSize: 13, fontWeight: 700, color: selectedSide === 'CE' ? '#22c55e' : '#ef4444' }}>
                  {selectedSide === 'CE' ? 'BUY' : 'SELL'}
                </span>
              </div>
              <div className="t-col">
                <label className="t-label">Qty</label>
                <input className="t-input" type="number" min={1} value={orderQty} onChange={e => setOrderQty(Number(e.target.value))} />
              </div>
              <div className="t-col">
                <label className="t-label">Type</label>
                <select className="t-select" value={orderType} onChange={e => setOrderType(e.target.value as 'MARKET' | 'LIMIT')}>
                  <option value="MARKET">Market</option>
                  <option value="LIMIT">Limit</option>
                </select>
              </div>
            </div>

            {orderType === 'LIMIT' && (
              <div style={{ marginBottom: 12 }}>
                <label className="t-label">Limit Price</label>
                <input className="t-input" type="number" min={0} step={0.05} value={orderPrice} onChange={e => setOrderPrice(Number(e.target.value))} />
              </div>
            )}

            <div className="t-row" style={{ alignItems: 'center', gap: 6, marginBottom: 12 }}>
              <span className="t-faint" style={{ fontSize: 10, fontWeight: 600 }}>MODE</span>
              <button
                className={`t-chip ${!isLiveMode ? 'active' : ''}`}
                onClick={() => isLiveMode && setIsLiveMode(false)}
                style={{ color: !isLiveMode ? undefined : 'var(--t-faint)' }}
              >
                PAPER
              </button>
              <button
                className={`t-chip ${isLiveMode ? 'active' : ''}`}
                onClick={handleToggleLive}
                style={{ color: isLiveMode ? '#ef4444' : 'var(--t-faint)' }}
              >
                LIVE
              </button>
              {activeBroker && (
                <span className="t-faint" style={{ fontSize: 10, marginLeft: 'auto' }}>
                  via {activeBroker.broker}
                </span>
              )}
            </div>

            {confirmingLive && (
              <div style={{
                background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)',
                borderRadius: 8, padding: '10px 12px', marginBottom: 12,
              }}>
                <p style={{ margin: '0 0 8px', fontSize: 11, color: '#ef4444', fontWeight: 500 }}>
                  Live trading is not enabled. Enable live mode to place real orders?
                </p>
                <div className="t-row" style={{ gap: 6 }}>
                  <button className="t-btn t-btn-sm t-btn-danger" onClick={confirmLive}>
                    Enable Live
                  </button>
                  <button className="t-btn t-btn-sm t-btn-ghost" onClick={() => setConfirmingLive(false)}>
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
                  {orderResult.broker_order_id && <span style={{ display: 'block', fontSize: 10, color: 'var(--t-faint)', marginTop: 2 }}>ID: {orderResult.broker_order_id}</span>}
                  {orderResult.message && <span style={{ display: 'block', fontSize: 10, marginTop: 2 }}>{orderResult.message}</span>}
                </div>
              </div>
            )}

            <button
              className={`t-btn ${isLiveMode ? 't-btn-danger' : 't-btn-primary'}`}
              onClick={handlePlace}
              disabled={placing}
              style={{ width: '100%' }}
            >
              {placing ? 'Placing...' : `${isLiveMode ? 'LIVE ' : ''}Place ${selectedSide === 'CE' ? 'BUY' : 'SELL'} ${underlying}${expiry}${selectedStrike}${selectedSide}`}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
