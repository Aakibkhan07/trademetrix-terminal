'use client'

import { useEffect, useState } from 'react'
import { api } from '@/lib/api'

interface Strategy {
  id: string
  name: string
  type: string
  is_active: boolean
  created_at: string
}

export default function StrategiesPage() {
  const [strategies, setStrategies] = useState<Strategy[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [name, setName] = useState('')
  const [strategyType, setStrategyType] = useState('trend_rider')
  const [symbol, setSymbol] = useState('NIFTY')

  const load = async () => {
    try {
      const d = await api.strategies.list()
      setStrategies((d as { strategies: Strategy[] }).strategies)
    } catch {
      setStrategies([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handleCreate = async () => {
    await api.strategies.create({
      name,
      type: 'builtin',
      config: { type: strategyType, symbol, strategy_id: 'new' },
    })
    setShowCreate(false)
    setName('')
    load()
  }

  const handleToggle = async (s: Strategy) => {
    await api.strategies.update(s.id, { is_active: !s.is_active })
    load()
  }

  const handleDelete = async (id: string) => {
    await api.strategies.delete(id)
    load()
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <div>
          <h1 style={{ fontFamily: 'Outfit', fontSize: 24, margin: 0 }}>Strategies</h1>
          <p style={{ color: '#8888a0', fontSize: 14, margin: '4px 0 0' }}>
            Create and manage your trading strategies
          </p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowCreate(true)}>
          + New Strategy
        </button>
      </div>

      {showCreate && (
        <div className="modal-overlay" onClick={() => setShowCreate(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h2 style={{ fontFamily: 'Outfit', fontSize: 18, margin: '0 0 16px' }}>Create Strategy</h2>
            <div style={{ marginBottom: 12 }}>
              <label style={{ color: '#8888a0', fontSize: 12, display: 'block', marginBottom: 4 }}>Name</label>
              <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="My Strategy" />
            </div>
            <div style={{ marginBottom: 12 }}>
              <label style={{ color: '#8888a0', fontSize: 12, display: 'block', marginBottom: 4 }}>Type</label>
              <select className="select" value={strategyType} onChange={(e) => setStrategyType(e.target.value)}>
                <option value="trend_rider">Trend Rider</option>
                <option value="orb_pro">ORB Pro</option>
                <option value="smc_sniper">SMC Sniper</option>
                <option value="expiry_hunter">Expiry Hunter</option>
              </select>
            </div>
            <div style={{ marginBottom: 20 }}>
              <label style={{ color: '#8888a0', fontSize: 12, display: 'block', marginBottom: 4 }}>Symbol</label>
              <input className="input" value={symbol} onChange={(e) => setSymbol(e.target.value)} placeholder="NIFTY" />
            </div>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button className="btn btn-secondary" onClick={() => setShowCreate(false)}>Cancel</button>
              <button className="btn btn-primary" onClick={handleCreate} disabled={!name}>Create</button>
            </div>
          </div>
        </div>
      )}

      {loading ? (
        <p style={{ color: '#8888a0' }}>Loading strategies...</p>
      ) : strategies.length === 0 ? (
        <div className="panel" style={{ textAlign: 'center', padding: 48 }}>
          <p style={{ color: '#555570', margin: 0 }}>No strategies yet. Create your first one.</p>
        </div>
      ) : (
        <div style={{ display: 'grid', gap: 12 }}>
          {strategies.map((s) => (
            <div key={s.id} className="glass-card" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <h3 style={{ fontFamily: 'Outfit', fontSize: 16, margin: 0 }}>{s.name}</h3>
                <p style={{ color: '#8888a0', fontSize: 12, margin: '4px 0 0' }}>
                  {s.type} · Created {new Date(s.created_at).toLocaleDateString()}
                </p>
              </div>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <span className={`badge ${s.is_active ? 'badge-green' : 'badge-violet'}`}>
                  {s.is_active ? 'Active' : 'Inactive'}
                </span>
                <button className="btn btn-sm btn-secondary" onClick={() => handleToggle(s)}>
                  {s.is_active ? 'Pause' : 'Start'}
                </button>
                <button className="btn btn-sm btn-danger" onClick={() => handleDelete(s.id)}>
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
