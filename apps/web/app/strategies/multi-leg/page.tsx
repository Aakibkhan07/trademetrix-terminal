'use client'

import { useState, useEffect } from 'react'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'
import { useToast } from '@/lib/use-toast'

interface Leg {
  action: 'BUY' | 'SELL'
  symbol: string
  quantity: number
  order_type: string
  price: number
  instrument_type: string
  strike_price: number | null
  expiry_date: string | null
  option_type: string | null
}

interface Strategy {
  id: string
  name: string
  description: string
  underlying: string
  expiry: string
  leg_count: number
  status: string
  created_at: string
  legs?: Leg[]
}

const TEMPLATES: Record<string, { name: string; legs: Leg[] }> = {
  'long-straddle': {
    name: 'Long Straddle',
    legs: [
      { action: 'BUY', symbol: 'NIFTY', quantity: 50, order_type: 'MARKET', price: 0, instrument_type: 'OPT', strike_price: null, expiry_date: null, option_type: 'CE' },
      { action: 'BUY', symbol: 'NIFTY', quantity: 50, order_type: 'MARKET', price: 0, instrument_type: 'OPT', strike_price: null, expiry_date: null, option_type: 'PE' },
    ],
  },
  'short-straddle': {
    name: 'Short Straddle',
    legs: [
      { action: 'SELL', symbol: 'NIFTY', quantity: 50, order_type: 'MARKET', price: 0, instrument_type: 'OPT', strike_price: null, expiry_date: null, option_type: 'CE' },
      { action: 'SELL', symbol: 'NIFTY', quantity: 50, order_type: 'MARKET', price: 0, instrument_type: 'OPT', strike_price: null, expiry_date: null, option_type: 'PE' },
    ],
  },
  'long-iron-condor': {
    name: 'Long Iron Condor',
    legs: [
      { action: 'BUY', symbol: 'NIFTY', quantity: 50, order_type: 'MARKET', price: 0, instrument_type: 'OPT', strike_price: null, expiry_date: null, option_type: 'PE' },
      { action: 'SELL', symbol: 'NIFTY', quantity: 50, order_type: 'MARKET', price: 0, instrument_type: 'OPT', strike_price: null, expiry_date: null, option_type: 'PE' },
      { action: 'SELL', symbol: 'NIFTY', quantity: 50, order_type: 'MARKET', price: 0, instrument_type: 'OPT', strike_price: null, expiry_date: null, option_type: 'CE' },
      { action: 'BUY', symbol: 'NIFTY', quantity: 50, order_type: 'MARKET', price: 0, instrument_type: 'OPT', strike_price: null, expiry_date: null, option_type: 'CE' },
    ],
  },
  'bull-call-spread': {
    name: 'Bull Call Spread',
    legs: [
      { action: 'BUY', symbol: 'NIFTY', quantity: 50, order_type: 'MARKET', price: 0, instrument_type: 'OPT', strike_price: null, expiry_date: null, option_type: 'CE' },
      { action: 'SELL', symbol: 'NIFTY', quantity: 50, order_type: 'MARKET', price: 0, instrument_type: 'OPT', strike_price: null, expiry_date: null, option_type: 'CE' },
    ],
  },
  'bear-put-spread': {
    name: 'Bear Put Spread',
    legs: [
      { action: 'BUY', symbol: 'NIFTY', quantity: 50, order_type: 'MARKET', price: 0, instrument_type: 'OPT', strike_price: null, expiry_date: null, option_type: 'PE' },
      { action: 'SELL', symbol: 'NIFTY', quantity: 50, order_type: 'MARKET', price: 0, instrument_type: 'OPT', strike_price: null, expiry_date: null, option_type: 'PE' },
    ],
  },
  'covered-call': {
    name: 'Covered Call',
    legs: [
      { action: 'BUY', symbol: 'NIFTY', quantity: 50, order_type: 'MARKET', price: 0, instrument_type: 'FUT', strike_price: null, expiry_date: null, option_type: null },
      { action: 'SELL', symbol: 'NIFTY', quantity: 50, order_type: 'MARKET', price: 0, instrument_type: 'OPT', strike_price: null, expiry_date: null, option_type: 'CE' },
    ],
  },
}

const STRATEGY_NAMES: Record<string, string> = {
  'long-straddle': 'Long Straddle', 'short-straddle': 'Short Straddle',
  'long-iron-condor': 'Long Iron Condor', 'bull-call-spread': 'Bull Call Spread',
  'bear-put-spread': 'Bear Put Spread', 'covered-call': 'Covered Call',
}

export default function MultiLegPage() {
  const { token } = useAuth()
  const { toast } = useToast()
  const [strategies, setStrategies] = useState<Strategy[]>([])
  const [loading, setLoading] = useState(true)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [underlying, setUnderlying] = useState('NIFTY')
  const [selectedTemplate, setSelectedTemplate] = useState('')
  const [legs, setLegs] = useState<Leg[]>([])
  const [placing, setPlacing] = useState<string | null>(null)
  const [showBuilder, setShowBuilder] = useState(false)

  useEffect(() => { if (token) load() }, [token])

  const load = async () => {
    try {
      const res = await api.multiLeg.list() as any
      setStrategies(res.strategies || [])
    } catch {} finally { setLoading(false) }
  }

  const applyTemplate = (key: string) => {
    const t = TEMPLATES[key]
    if (!t) return
    setSelectedTemplate(key)
    setName(t.name)
    setLegs(JSON.parse(JSON.stringify(t.legs)))
  }

  const addLeg = () => {
    setLegs([...legs, { action: 'BUY', symbol: underlying, quantity: 50, order_type: 'MARKET', price: 0, instrument_type: 'OPT', strike_price: null, expiry_date: null, option_type: 'CE' }])
  }

  const updateLeg = (i: number, field: keyof Leg, value: any) => {
    const updated = [...legs]
    ;(updated[i] as any)[field] = value
    setLegs(updated)
  }

  const removeLeg = (i: number) => {
    setLegs(legs.filter((_, idx) => idx !== i))
  }

  const handleCreate = async () => {
    if (!name.trim()) { toast('error', 'Strategy name required'); return }
    if (legs.length === 0) { toast('error', 'At least one leg required'); return }
    const apiLegs = legs.map(l => ({
      action: l.action,
      symbol: l.symbol,
      quantity: l.quantity,
      order_type: l.order_type,
      price: l.price,
      instrument_type: l.instrument_type,
      strike_price: l.strike_price ?? undefined,
      expiry_date: l.expiry_date ?? undefined,
      option_type: l.option_type ?? undefined,
      exchange: 'NFO',
      product: 'INTRADAY',
    }))
    try {
      const res = await api.multiLeg.create({
        name, description, underlying, expiry: 'weekly', legs: apiLegs,
      }) as any
      toast('success', `Strategy "${res.name}" created`)
      setShowBuilder(false)
      setName(''); setDescription(''); setLegs([]); setSelectedTemplate('')
      load()
    } catch { toast('error', 'Failed to create strategy') }
  }

  const handlePlace = async (sid: string) => {
    setPlacing(sid)
    try {
      const res = await api.multiLeg.place(sid) as any
      toast('success', `Placed ${res.results?.length || 0} legs`)
      load()
    } catch { toast('error', 'Failed to place strategy') }
    finally { setPlacing(null) }
  }

  const handleDelete = async (sid: string) => {
    try {
      await api.multiLeg.delete(sid)
      toast('success', 'Strategy deleted')
      load()
    } catch { toast('error', 'Failed to delete') }
  }

  return (
    <div>
      <div className="t-page-header">
        <div>
          <h1 className="t-page-title">Multi-Leg Strategies</h1>
          <p className="t-page-subtitle">Build and deploy multi-leg option strategies as a single order group</p>
        </div>
        <button className="t-btn t-btn-sm" onClick={() => setShowBuilder(!showBuilder)}>
          {showBuilder ? 'Cancel' : 'New Strategy'}
        </button>
      </div>

      {showBuilder && (
        <div className="t-panel" style={{ marginBottom: 16 }}>
          <div className="t-panel-header">
            <h3 className="t-panel-title">Create New Strategy</h3>
          </div>
          <div className="t-panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
              <div style={{ flex: 1, minWidth: 200 }}>
                <label className="t-label">Name</label>
                <input className="t-input" value={name} onChange={e => setName(e.target.value)} placeholder="My Iron Condor" />
              </div>
              <div style={{ flex: 1, minWidth: 200 }}>
                <label className="t-label">Underlying</label>
                <select className="t-input" value={underlying} onChange={e => setUnderlying(e.target.value)}>
                  {['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'SENSEX'].map(s => <option key={s}>{s}</option>)}
                </select>
              </div>
            </div>
            <div>
              <label className="t-label">Description</label>
              <input className="t-input" value={description} onChange={e => setDescription(e.target.value)} placeholder="Optional description" />
            </div>

            <div>
              <label className="t-label">Templates</label>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {Object.entries(TEMPLATES).map(([key, t]) => (
                  <button key={key} className={`t-btn t-btn-xs ${selectedTemplate === key ? 't-btn-active' : 't-btn-ghost'}`}
                    onClick={() => applyTemplate(key)}>{t.name}</button>
                ))}
              </div>
            </div>

            <div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                <span className="t-label" style={{ margin: 0 }}>Legs ({legs.length})</span>
                <button className="t-btn t-btn-xs t-btn-ghost" onClick={addLeg}>+ Add Leg</button>
              </div>
              {legs.map((leg, i) => (
                <div key={i} style={{ display: 'flex', gap: 6, alignItems: 'center', padding: '6px 8px', background: 'var(--bg-hover)', borderRadius: 6, marginBottom: 4, flexWrap: 'wrap' }}>
                  <select className="t-input t-input-xs" value={leg.action} onChange={e => updateLeg(i, 'action', e.target.value)} style={{ width: 70 }}>
                    <option value="BUY">BUY</option>
                    <option value="SELL">SELL</option>
                  </select>
                  <select className="t-input t-input-xs" value={leg.option_type || ''} onChange={e => updateLeg(i, 'option_type', e.target.value || null)} style={{ width: 60 }}>
                    <option value="">FUT</option>
                    <option value="CE">CE</option>
                    <option value="PE">PE</option>
                  </select>
                  <input className="t-input t-input-xs" type="number" placeholder="Strike" value={leg.strike_price || ''} onChange={e => updateLeg(i, 'strike_price', e.target.value ? Number(e.target.value) : null)} style={{ width: 80 }} />
                  <input className="t-input t-input-xs" type="number" value={leg.quantity} onChange={e => updateLeg(i, 'quantity', Number(e.target.value))} style={{ width: 70 }} />
                  <select className="t-input t-input-xs" value={leg.order_type} onChange={e => updateLeg(i, 'order_type', e.target.value)} style={{ width: 85 }}>
                    <option value="MARKET">MARKET</option>
                    <option value="LIMIT">LIMIT</option>
                  </select>
                  {leg.order_type === 'LIMIT' && (
                    <input className="t-input t-input-xs" type="number" placeholder="Price" value={leg.price} onChange={e => updateLeg(i, 'price', Number(e.target.value))} style={{ width: 70 }} />
                  )}
                  <button className="t-btn t-btn-xs t-btn-danger" onClick={() => removeLeg(i)} style={{ marginLeft: 'auto' }}>✕</button>
                </div>
              ))}
              {legs.length === 0 && <p className="t-faint" style={{ fontSize: 11, padding: 8 }}>Add legs or choose a template above</p>}
            </div>

            <div>
              <button className="t-btn" onClick={handleCreate}>Create Strategy</button>
            </div>
          </div>
        </div>
      )}

      <div className="t-panel" style={{ padding: 0 }}>
        <div className="t-panel-header">
          <h3 className="t-panel-title">Saved Strategies ({strategies.length})</h3>
        </div>
        {loading ? (
          <div className="t-panel-body t-faint">Loading...</div>
        ) : strategies.length === 0 ? (
          <div className="t-panel-body t-faint" style={{ textAlign: 'center', padding: 24 }}>No strategies yet. Create your first multi-leg strategy above.</div>
        ) : (
          <div className="t-table-wrap">
            <table className="t-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Underlying</th>
                  <th>Legs</th>
                  <th>Status</th>
                  <th>Created</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {strategies.map((s) => (
                  <tr key={s.id}>
                    <td style={{ fontWeight: 600 }}>{s.name}</td>
                    <td>{s.underlying}</td>
                    <td className="t-num">{s.leg_count}</td>
                    <td>
                      <span className={`t-badge ${s.status === 'active' ? 't-badge-green' : s.status === 'placed' ? 't-badge-cyan' : 't-badge-sub'}`}>
                        {s.status}
                      </span>
                    </td>
                    <td className="t-faint t-num" style={{ fontSize: 11 }}>
                      {s.created_at ? new Date(s.created_at).toLocaleDateString() : '-'}
                    </td>
                    <td>
                      <div style={{ display: 'flex', gap: 4 }}>
                        <button className="t-btn t-btn-xs t-btn-green" onClick={() => handlePlace(s.id)} disabled={placing === s.id}>
                          {placing === s.id ? 'Placing...' : 'Place'}
                        </button>
                        <button className="t-btn t-btn-xs t-btn-danger" onClick={() => handleDelete(s.id)}>Delete</button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
