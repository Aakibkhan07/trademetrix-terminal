'use client'

import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import Link from 'next/link'

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
      setStrategies((d as { strategies: Strategy[] }).strategies || [])
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
      <div className="page-header">
        <div>
          <h1 className="page-title">Strategies</h1>
          <p className="page-subtitle">
            Create, deploy, and manage your trading strategies
          </p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowCreate(true)}>
          + New Strategy
        </button>
      </div>

      {strategies.length === 0 && !loading && (
        <div style={{ background: 'rgba(34,211,238,0.06)', border: '1px solid rgba(34,211,238,0.12)', borderRadius: 10, padding: '12px 16px', marginBottom: 20, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <p style={{ margin: 0, fontSize: 13, color: '#22d3ee', fontWeight: 500 }}>No strategies yet</p>
            <p style={{ margin: '2px 0 0', fontSize: 12, color: '#555570' }}>Create your first strategy or explore the built-in types below.</p>
          </div>
          <button className="btn btn-sm btn-cyan" onClick={() => setShowCreate(true)}>Create Strategy</button>
        </div>
      )}

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
                <option value="rsi_mean_reversion">RSI Mean Reversion</option>
                <option value="bollinger_bandit">Bollinger Bandit</option>
                <option value="macd_cross">MACD Crossover</option>
                <option value="vwap_band">VWAP Band</option>
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
      ) : (
        <>
          <h2 style={{ fontFamily: 'Outfit', fontSize: 15, margin: '0 0 14px', color: '#f0f0f5' }}>
            Saved Strategies ({strategies.length})
          </h2>
          <div className="grid-auto" style={{ marginBottom: 28 }}>
            {strategies.map((s) => {
              return (
                <div key={s.id} className="strategy-card" style={{ padding: 0, display: 'flex', flexDirection: 'column' }}>
                  <div style={{ padding: '18px', flex: 1 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 14 }}>
                      <div>
                        <h3 style={{ fontFamily: 'Outfit', fontSize: 14, margin: 0 }}>{s.name}</h3>
                        <p style={{ margin: '2px 0 0', fontSize: 11, color: '#555570' }}>{s.type}</p>
                      </div>
                      <span className={`badge ${s.is_active ? 'badge-green' : 'badge-violet'}`} style={{ fontSize: 9, padding: '2px 8px' }}>
                        {s.is_active ? 'Active' : 'Inactive'}
                      </span>
                    </div>
                    <p style={{ margin: 0, fontSize: 11, color: '#555570' }}>
                      Created {new Date(s.created_at).toLocaleDateString()}
                    </p>
                  </div>
                  <div style={{ borderTop: '1px solid rgba(139,92,246,0.06)', padding: '10px 18px', display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
                    <button className="btn btn-sm btn-secondary" onClick={() => handleToggle(s)} style={{ fontSize: 11 }}>
                      {s.is_active ? 'Pause' : 'Start'}
                    </button>
                    <button className="btn btn-sm btn-danger" onClick={() => handleDelete(s.id)} style={{ fontSize: 11 }}>
                      Delete
                    </button>
                    <Link href="/backtest" className="btn btn-sm btn-cyan" style={{ fontSize: 11 }}>Backtest</Link>
                  </div>
                </div>
              )
            })}
          </div>

            <div className="panel" style={{ padding: '20px' }}>
            <div className="panel-header" style={{ marginBottom: 12 }}>
              <h3 className="panel-title" style={{ fontSize: 15 }}>Built-in Strategy Types</h3>
            </div>
            <div className="grid-2">
              <div>
                <p style={{ margin: '0 0 4px', fontSize: 13, fontWeight: 600 }}>Trend Rider</p>
                <p style={{ margin: 0, fontSize: 11, color: '#555570' }}>EMA crossover (9/21) trend following with momentum confirmation.</p>
              </div>
              <div>
                <p style={{ margin: '0 0 4px', fontSize: 13, fontWeight: 600 }}>ORB Pro</p>
                <p style={{ margin: 0, fontSize: 11, color: '#555570' }}>Opening Range Breakout with volume confirmation for high-volatility openings.</p>
              </div>
              <div>
                <p style={{ margin: '0 0 4px', fontSize: 13, fontWeight: 600 }}>SMC Sniper</p>
                <p style={{ margin: 0, fontSize: 11, color: '#555570' }}>Smart Money Concepts: order blocks, FVG, and liquidity sweep detection.</p>
              </div>
              <div>
                <p style={{ margin: '0 0 4px', fontSize: 13, fontWeight: 600 }}>Expiry Hunter</p>
                <p style={{ margin: 0, fontSize: 11, color: '#555570' }}>Options theta decay capture with IV rank analysis for weekly expiry.</p>
              </div>
              <div>
                <p style={{ margin: '0 0 4px', fontSize: 13, fontWeight: 600 }}>RSI Mean Reversion</p>
                <p style={{ margin: 0, fontSize: 11, color: '#555570' }}>Buys when RSI exits oversold (&lt;30), sells when RSI exits overbought (&gt;70).</p>
              </div>
              <div>
                <p style={{ margin: '0 0 4px', fontSize: 13, fontWeight: 600 }}>Bollinger Bandit</p>
                <p style={{ margin: 0, fontSize: 11, color: '#555570' }}>Mean reversion on Bollinger Band touches. Fades moves to outer bands.</p>
              </div>
              <div>
                <p style={{ margin: '0 0 4px', fontSize: 13, fontWeight: 600 }}>MACD Crossover</p>
                <p style={{ margin: 0, fontSize: 11, color: '#555570' }}>MACD line / signal line crossovers. Standard 12/26/9 parameters.</p>
              </div>
              <div>
                <p style={{ margin: '0 0 4px', fontSize: 13, fontWeight: 600 }}>VWAP Band</p>
                <p style={{ margin: 0, fontSize: 11, color: '#555570' }}>Mean reversion around VWAP with deviation band triggers. Tick-based execution.</p>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
