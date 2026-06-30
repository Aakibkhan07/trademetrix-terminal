'use client'

import { useState, useCallback } from 'react'
import { useApi } from '@/lib/use-api'
import { useAuth } from '@/lib/auth-context'
import { api } from '@/lib/api'

/* -------- Types -------- */

interface StrategyInfo {
  key: string
  name: string
  description: string
  required_tier: string
}

interface Recipient {
  user_id: string
  email: string
  full_name: string
}

interface BroadcastResult {
  user_id: string
  email: string
  success: boolean
  broker_order_id: string
  message: string
  status: string
}

interface BroadcastResponse {
  results: BroadcastResult[]
  count: number
  paper: boolean
}

/* -------- Constants -------- */

const ACTIONS = ['BUY', 'SELL']
const EXCHANGES = ['NSE', 'BSE', 'NFO']
const ORDER_TYPES = ['MARKET', 'LIMIT']
const PRODUCTS = ['INTRADAY', 'NRML']

/* -------- Skeleton -------- */

function SkeletonLine({ w, h = 12 }: { w: string; h?: number }) {
  return <div style={{ width: w, height: h, background: 'rgba(139,92,246,0.08)', borderRadius: 4 }} />
}

/* -------- Not authorized -------- */

function NotAuthorized() {
  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Broadcast</h1>
          <p className="page-subtitle">Send signals to assigned users</p>
        </div>
      </div>
      <div className="alert alert-error">You do not have admin access.</div>
    </div>
  )
}

/* -------- Main -------- */

export default function BroadcastPage() {
  const { isAdmin, loading: authLoading } = useAuth()

  if (authLoading) {
    return (
      <div>
        <div className="page-header"><h1 className="page-title">Broadcast</h1></div>
        <div className="panel" style={{ padding: 20 }}><SkeletonLine w="40%" /><SkeletonLine w="60%" /></div>
      </div>
    )
  }
  if (!isAdmin) return <NotAuthorized />

  return <BroadcastDashboard />
}

function BroadcastDashboard() {
  const [strategyKey, setStrategyKey] = useState('')
  const [symbol, setSymbol] = useState('NIFTY')
  const [action, setAction] = useState('BUY')
  const [quantity, setQuantity] = useState(1)
  const [price, setPrice] = useState(0)
  const [exchange, setExchange] = useState('NFO')
  const [orderType, setOrderType] = useState('MARKET')
  const [product, setProduct] = useState('INTRADAY')
  const [reason, setReason] = useState('')
  const [isPaper, setIsPaper] = useState(true)
  const [confirmingLive, setConfirmingLive] = useState(false)
  const [sending, setSending] = useState(false)
  const [sendError, setSendError] = useState('')
  const [sendResult, setSendResult] = useState<BroadcastResponse | null>(null)
  const [broadcasts, setBroadcasts] = useState<BroadcastResponse[]>([])
  const [previewKey, setPreviewKey] = useState('')

  const { data: catalogData } = useApi<{ strategies: StrategyInfo[] }>('/strategies/list-builtin')
  const catalog = catalogData?.strategies || []

  const { data: recipData, loading: recipLoading } = useApi<{ recipients: Recipient[] }>(
    previewKey ? `/admin/broadcast/recipients?strategy_key=${previewKey}` : null,
  )
  const recipients = recipData?.recipients || []

  const selectedStrategy = catalog.find(s => s.key === strategyKey)

  const handlePreview = useCallback(() => {
    if (strategyKey) setPreviewKey(strategyKey)
  }, [strategyKey])

  const handleSend = async (confirmedLive = false) => {
    if (!strategyKey) return
    if (!isPaper && !confirmingLive && !confirmedLive) {
      setConfirmingLive(true)
      return
    }
    setConfirmingLive(false)
    setSending(true)
    setSendError('')
    try {
      const res = await api.admin.broadcast.send({
        strategy_key: strategyKey,
        symbol,
        action,
        quantity,
        price: orderType === 'LIMIT' ? price : 0,
        exchange,
        order_type: orderType,
        product,
        reason,
        paper: isPaper || confirmedLive === false,
      })
      setSendResult(res)
      setBroadcasts(prev => [res, ...prev].slice(0, 20))
    } catch (e) {
      setSendError(e instanceof Error ? e.message : String(e))
    } finally {
      setSending(false)
    }
  }

  const placed = sendResult?.results.filter(r => r.success) || []
  const rejected = sendResult?.results.filter(r => !r.success) || []

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Broadcast Signal</h1>
          <p className="page-subtitle">Send a trading signal to all users assigned to a strategy</p>
        </div>
      </div>

      {/* Composer */}
      <div className="panel" style={{ padding: 16, marginBottom: 20 }}>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 12 }}>
          <div style={{ flex: '0 0 200px' }}>
            <label style={{ color: '#555570', fontSize: 10, display: 'block', marginBottom: 2 }}>Strategy</label>
            <select className="select" value={strategyKey} onChange={e => { setStrategyKey(e.target.value); setPreviewKey(''); setSendResult(null) }} style={{ fontSize: 12, padding: '4px 8px' }}>
              <option value="">Select strategy...</option>
              {catalog.map(s => (
                <option key={s.key} value={s.key}>{s.name} ({s.required_tier})</option>
              ))}
            </select>
          </div>

          <div>
            <label style={{ color: '#555570', fontSize: 10, display: 'block', marginBottom: 2 }}>Symbol</label>
            <input className="input" value={symbol} onChange={e => setSymbol(e.target.value.toUpperCase())} style={{ width: 100, fontSize: 12, padding: '4px 8px' }} />
          </div>

          <div>
            <label style={{ color: '#555570', fontSize: 10, display: 'block', marginBottom: 2 }}>Action</label>
            <select className="select" value={action} onChange={e => setAction(e.target.value)} style={{ width: 80, fontSize: 12, padding: '4px 8px' }}>
              {ACTIONS.map(a => <option key={a} value={a}>{a}</option>)}
            </select>
          </div>

          <div>
            <label style={{ color: '#555570', fontSize: 10, display: 'block', marginBottom: 2 }}>Qty</label>
            <input className="input" type="number" min={1} value={quantity} onChange={e => setQuantity(Number(e.target.value))} style={{ width: 80, fontSize: 12, padding: '4px 8px' }} />
          </div>

          <div>
            <label style={{ color: '#555570', fontSize: 10, display: 'block', marginBottom: 2 }}>Exchange</label>
            <select className="select" value={exchange} onChange={e => setExchange(e.target.value)} style={{ width: 80, fontSize: 12, padding: '4px 8px' }}>
              {EXCHANGES.map(e => <option key={e} value={e}>{e}</option>)}
            </select>
          </div>

          <div>
            <label style={{ color: '#555570', fontSize: 10, display: 'block', marginBottom: 2 }}>Type</label>
            <select className="select" value={orderType} onChange={e => { setOrderType(e.target.value); if (e.target.value === 'MARKET') setPrice(0) }} style={{ width: 80, fontSize: 12, padding: '4px 8px' }}>
              {ORDER_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>

          <div>
            <label style={{ color: '#555570', fontSize: 10, display: 'block', marginBottom: 2 }}>Product</label>
            <select className="select" value={product} onChange={e => setProduct(e.target.value)} style={{ width: 90, fontSize: 12, padding: '4px 8px' }}>
              {PRODUCTS.map(p => <option key={p} value={p}>{p}</option>)}
            </select>
          </div>

          {orderType === 'LIMIT' && (
            <div>
              <label style={{ color: '#555570', fontSize: 10, display: 'block', marginBottom: 2 }}>Price</label>
              <input className="input" type="number" min={0} step={0.05} value={price} onChange={e => setPrice(Number(e.target.value))} style={{ width: 90, fontSize: 12, padding: '4px 8px' }} />
            </div>
          )}
        </div>

        <div style={{ marginBottom: 12 }}>
          <label style={{ color: '#555570', fontSize: 10, display: 'block', marginBottom: 2 }}>Reason (optional)</label>
          <input className="input" value={reason} onChange={e => setReason(e.target.value)} placeholder="e.g. Admin broadcast test" style={{ fontSize: 12, padding: '4px 8px' }} />
        </div>

        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <button
            className="btn btn-sm btn-secondary"
            onClick={handlePreview}
            disabled={!strategyKey}
            style={{ fontSize: 11 }}
          >
            Preview Recipients
          </button>

          <span style={{ fontSize: 10, color: '#555570' }}>
            {recipients.length} user{recipients.length !== 1 ? 's' : ''} will receive this signal
          </span>

          <div style={{ marginLeft: 'auto', display: 'flex', gap: 6, alignItems: 'center' }}>
            <button
              className={`btn btn-sm ${isPaper ? 'btn-success' : 'btn-secondary'}`}
              onClick={() => { setIsPaper(true); setConfirmingLive(false) }}
              style={{ fontSize: 10 }}
            >
              PAPER
            </button>
            <button
              className={`btn btn-sm ${!isPaper ? 'btn-danger' : 'btn-secondary'}`}
              onClick={() => setIsPaper(false)}
              style={{ fontSize: 10 }}
            >
              LIVE
            </button>
          </div>
        </div>

        {sendError && <div className="alert alert-error" style={{ marginTop: 12 }}>{sendError}</div>}

        {sendResult && (
          <div style={{ marginTop: 12 }}>
            <div className={`alert ${rejected.length === 0 ? 'alert-success' : 'alert-error'}`}>
              <span style={{ fontSize: 12, fontWeight: 600 }}>
                {placed.length} placed, {rejected.length} rejected
                {sendResult.paper ? ' (PAPER)' : ' (LIVE)'}
              </span>
            </div>
            {rejected.length > 0 && (
              <div style={{ marginTop: 8 }}>
                <p style={{ fontSize: 11, color: '#ef4444', fontWeight: 500, margin: '0 0 4px' }}>Rejections:</p>
                {rejected.map(r => (
                  <div key={r.user_id} className="glass-card" style={{ padding: '6px 10px', marginBottom: 4, fontSize: 11 }}>
                    <span style={{ color: '#f0f0f5', fontWeight: 600 }}>{r.email}</span>
                    <span style={{ color: '#555570', marginLeft: 8 }}>{r.message}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Live confirm dialog - two-step */}
        {confirmingLive && (
          <div style={{
            marginTop: 12, background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)',
            borderRadius: 8, padding: '12px',
          }}>
            <p style={{ margin: '0 0 8px', fontSize: 12, color: '#ef4444', fontWeight: 600 }}>
              Confirm LIVE Broadcast
            </p>
            <p style={{ margin: '0 0 10px', fontSize: 11, color: '#aaaac0' }}>
              Real orders will be placed in <strong>{recipients.length} user account{recipients.length !== 1 ? 's' : ''}</strong>,
              each through their own broker gate. This uses real capital.
            </p>
            <div style={{ display: 'flex', gap: 6 }}>
              <button className="btn btn-sm btn-danger" onClick={() => handleSend(true)} style={{ fontSize: 10 }}>
                Confirm LIVE Broadcast
              </button>
              <button className="btn btn-sm btn-secondary" onClick={() => setConfirmingLive(false)} style={{ fontSize: 10 }}>
                Cancel
              </button>
            </div>
          </div>
        )}

        <button
          className={`btn ${!isPaper ? 'btn-danger' : 'btn-primary'}`}
          onClick={() => handleSend()}
          disabled={!strategyKey || sending}
          style={{ marginTop: 12, width: '100%', fontSize: 12 }}
        >
          {sending ? 'Sending...' : `Send ${action} ${symbol} to ${recipients.length} user${recipients.length !== 1 ? 's' : ''}${!isPaper ? ' (LIVE)' : ''}`}
        </button>
      </div>

      {/* Recipients preview */}
      {recipLoading && (
        <div className="panel" style={{ padding: 16, marginBottom: 20 }}>
          <SkeletonLine w="30%" /><SkeletonLine w="60%" />
        </div>
      )}

      {!recipLoading && previewKey && recipients.length > 0 && (
        <div className="panel" style={{ padding: 0, overflow: 'hidden', marginBottom: 20 }}>
          <div className="panel-header" style={{ padding: '12px 16px', margin: 0 }}>
            <h3 className="panel-title" style={{ fontSize: 13 }}>Recipients Preview</h3>
            <span style={{ fontSize: 11, color: '#555570' }}>{recipients.length} user{recipients.length !== 1 ? 's' : ''}</span>
          </div>
          <table className="data-table" style={{ fontSize: 12 }}>
            <thead>
              <tr>
                <th>Name</th>
                <th>Email</th>
              </tr>
            </thead>
            <tbody>
              {recipients.map(r => (
                <tr key={r.user_id}>
                  <td style={{ fontWeight: 600 }}>{r.full_name || r.email.split('@')[0]}</td>
                  <td>{r.email}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {!recipLoading && previewKey && recipients.length === 0 && (
        <div className="panel" style={{ padding: 16, marginBottom: 20, textAlign: 'center' }}>
          <p style={{ fontSize: 12, color: '#555570', margin: 0 }}>
            No recipients for this strategy. Users must have this strategy assigned with mirror enabled.
          </p>
        </div>
      )}

      {/* Recent broadcasts */}
      {broadcasts.length > 0 && (
        <div className="panel" style={{ padding: 0, overflow: 'hidden' }}>
          <div className="panel-header" style={{ padding: '12px 16px', margin: 0 }}>
            <h3 className="panel-title" style={{ fontSize: 13 }}>Recent Broadcasts</h3>
          </div>
          {broadcasts.map((b, i) => {
            const p = b.results.filter(r => r.success).length
            const rj = b.results.filter(r => !r.success).length
            return (
              <div key={i} className="glass-card" style={{ padding: '8px 12px', margin: '0 12px 8px', fontSize: 11 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontWeight: 600, color: '#f0f0f5' }}>
                    {b.count} users
                  </span>
                  <span style={{ color: b.paper ? '#22c55e' : '#ef4444', fontWeight: 600 }}>
                    {b.paper ? 'PAPER' : 'LIVE'}
                  </span>
                </div>
                <div style={{ marginTop: 4 }}>
                  <span style={{ color: '#22c55e' }}>{p} placed</span>
                  {rj > 0 && <span style={{ color: '#ef4444', marginLeft: 8 }}>{rj} rejected</span>}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
