'use client'

import { useState, useEffect } from 'react'
import { api, Alert } from '@/lib/api'

const CHANNELS = ['email', 'sms', 'whatsapp'] as const

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [loading, setLoading] = useState(true)
  const [symbol, setSymbol] = useState('')
  const [condition, setCondition] = useState('above')
  const [target, setTarget] = useState('')
  const [note, setNote] = useState('')
  const [creating, setCreating] = useState(false)
  const [msg, setMsg] = useState('')

  const [notifChannels, setNotifChannels] = useState<string[]>(['email'])
  const [notifOpen, setNotifOpen] = useState(false)

  useEffect(() => {
    api.alerts.list().then(d => { setAlerts(d.alerts); setLoading(false) }).catch(() => setLoading(false))
    api.alerts.getNotificationPrefs().then(d => setNotifChannels(d.channels)).catch(() => {})
  }, [])

  const handleCreate = async () => {
    if (!symbol || !target) { setMsg('Fill symbol and target price'); return }
    setCreating(true); setMsg('')
    try {
      const a = await api.alerts.create({ symbol: symbol.toUpperCase(), condition, target_price: parseFloat(target), note })
      setAlerts(prev => [a, ...prev])
      setSymbol(''); setTarget(''); setNote('')
    } catch (err: unknown) { setMsg(err instanceof Error ? err.message : 'Failed') }
    finally { setCreating(false) }
  }

  const handleToggle = async (id: string) => {
    const res = await api.alerts.toggle(id)
    setAlerts(prev => prev.map(a => a.id === id ? { ...a, is_active: res.is_active } : a))
  }

  const handleDelete = async (id: string) => {
    await api.alerts.remove(id)
    setAlerts(prev => prev.filter(a => a.id !== id))
  }

  const toggleChannel = (ch: string) => {
    const next = notifChannels.includes(ch) ? notifChannels.filter(c => c !== ch) : [...notifChannels, ch]
    setNotifChannels(next.length ? next : ['email'])
    api.alerts.updateNotificationPrefs(next.length ? next : ['email']).catch(() => {})
  }

  return (
    <div>
      <div style={{ marginBottom: 20 }}>
        <h1 className="t-page-title">Price Alerts</h1>
        <p className="t-sub" style={{ fontSize: 12 }}>Get notified when prices cross your target</p>
      </div>

      <div style={{ display: 'flex', gap: 10, marginBottom: 20 }}>
        <div className="t-panel" style={{ padding: 16, flex: 1, maxWidth: 500 }}>
          <h3 style={{ fontFamily: 'var(--font-display)', fontSize: 13, margin: '0 0 10px', color: '#f0f0f5' }}>New Alert</h3>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 8 }}>
            <input className="t-input" value={symbol} onChange={e => setSymbol(e.target.value.toUpperCase())}
              placeholder="Symbol" style={{ width: 100, fontSize: 11 }} />
            <select className="t-select" value={condition} onChange={e => setCondition(e.target.value)} style={{ fontSize: 11, width: 80 }}>
              <option value="above">Above</option>
              <option value="below">Below</option>
            </select>
            <input className="t-input" type="number" step="0.05" value={target} onChange={e => setTarget(e.target.value)}
              placeholder="Price" style={{ width: 100, fontSize: 11 }} />
            <button className="t-btn t-btn-sm" onClick={handleCreate} disabled={creating} style={{ fontSize: 10 }}>
              {creating ? '...' : 'Create'}
            </button>
          </div>
          <input className="t-input" value={note} onChange={e => setNote(e.target.value)}
            placeholder="Note (optional)" style={{ fontSize: 10, width: '100%' }} />
          {msg && <p style={{ fontSize: 10, margin: '4px 0 0', color: msg.includes('symbol') ? '#ef4444' : '#22c55e' }}>{msg}</p>}
        </div>

        <div className="t-panel" style={{ padding: 16, width: 260 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <h3 style={{ fontFamily: 'var(--font-display)', fontSize: 12, margin: 0, color: '#f0f0f5' }}>Notifications</h3>
            <span style={{ fontSize: 9, color: notifChannels.length ? '#22c55e' : '#8888a0' }}>
              {notifChannels.length ? notifChannels.join(', ') : 'off'}
            </span>
          </div>
          {CHANNELS.map(ch => (
            <label key={ch} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '4px 0', cursor: 'pointer', fontSize: 12 }}>
              <input type="checkbox" checked={notifChannels.includes(ch)} onChange={() => toggleChannel(ch)}
                style={{ accentColor: '#8b5cf6' }} />
              <span style={{ textTransform: 'capitalize' }}>{ch}</span>
              <span className="t-faint" style={{ fontSize: 9 }}>
                {ch === 'email' ? 'via SMTP' : ch === 'sms' ? 'via Fast2SMS' : 'via Twilio'}
              </span>
            </label>
          ))}
          <p className="t-faint" style={{ fontSize: 9, margin: '6px 0 0' }}>
            Alerts trigger automatically when price crosses target
          </p>
        </div>
      </div>

      {loading && <div className="t-panel" style={{ padding: 16, textAlign: 'center' }}><span className="t-faint">Loading...</span></div>}
      {!loading && alerts.length === 0 && (
        <div className="t-panel" style={{ padding: 20, textAlign: 'center' }}>
          <p style={{ fontSize: 13, color: '#555570', margin: 0 }}>No alerts yet. Create one above.</p>
        </div>
      )}
      {alerts.map(a => (
        <div key={a.id} className="t-panel" style={{
          padding: '10px 14px', marginBottom: 6, display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          borderLeft: `3px solid ${a.is_active ? (a.triggered_at ? '#f59e0b' : 'var(--violet)') : '#555570'}`,
        }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 14, fontWeight: 700, fontFamily: 'var(--font-mono)' }}>{a.symbol}</span>
              <span style={{
                fontSize: 10, padding: '1px 6px', borderRadius: 4, fontWeight: 600,
                background: a.condition === 'above' ? 'rgba(34,197,94,0.1)' : 'rgba(239,68,68,0.1)',
                color: a.condition === 'above' ? '#22c55e' : '#ef4444',
              }}>
                {a.condition === 'above' ? '>' : '<'} ₹{a.target_price.toFixed(2)}
              </span>
              {a.triggered_at && <span style={{ fontSize: 9, color: '#f59e0b' }}>Triggered</span>}
            </div>
            {a.note && <p style={{ margin: '2px 0 0', fontSize: 10, color: '#8888a0' }}>{a.note}</p>}
          </div>
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <button className={`t-btn t-btn-xs ${a.is_active ? 't-btn-ghost' : ''}`}
              onClick={() => handleToggle(a.id)}
              style={{ fontSize: 9, color: a.is_active ? '#22c55e' : '#8888a0' }}>
              {a.is_active ? 'ON' : 'OFF'}
            </button>
            <button className="t-btn t-btn-xs t-btn-danger" onClick={() => handleDelete(a.id)} style={{ fontSize: 9 }}>X</button>
          </div>
        </div>
      ))}
    </div>
  )
}
