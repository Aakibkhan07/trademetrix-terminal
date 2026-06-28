'use client'

import { useEffect, useState } from 'react'
import { api } from '@/lib/api'

const BROKER_INFO: Record<string, string> = {
  fyers: 'Fyers',
  dhan: 'Dhan',
  zerodha: 'Zerodha (Kite)',
  angelone: 'Angel One',
  upstox: 'Upstox',
  fivepaisa: '5Paisa',
  aliceblue: 'Alice Blue',
  finvasia: 'Finvasia (Shoonya)',
  flattrade: 'Flattrade',
  kotakneo: 'Kotak Neo',
}

interface BrokerCred {
  id: string
  broker: string
  is_active: boolean
  created_at: string
}

export default function BrokersPage() {
  const [credentials, setCredentials] = useState<BrokerCred[]>([])
  const [available, setAvailable] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [showAdd, setShowAdd] = useState(false)
  const [selectedBroker, setSelectedBroker] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [secretKey, setSecretKey] = useState('')

  const load = async () => {
    try {
      const [credData, brokerData] = await Promise.all([
        api.brokers.credentials(),
        api.brokers.list(),
      ])
      setCredentials((credData as { credentials: BrokerCred[] }).credentials || [])
      setAvailable((brokerData as { brokers: string[] }).brokers || [])
    } catch {
      setCredentials([])
      setAvailable([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handleAdd = async () => {
    await api.brokers.saveCredentials({ broker: selectedBroker, api_key: apiKey, secret_key: secretKey })
    setShowAdd(false)
    setSelectedBroker('')
    setApiKey('')
    setSecretKey('')
    load()
  }

  const handleDelete = async (broker: string) => {
    await api.brokers.deleteCredentials(broker)
    load()
  }

  const connectedBrokers = credentials.map((c) => c.broker)
  const unconnected = available.filter((b) => !connectedBrokers.includes(b))

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <div>
          <h1 style={{ fontFamily: 'Outfit', fontSize: 24, margin: 0 }}>Brokers</h1>
          <p style={{ color: '#8888a0', fontSize: 14, margin: '4px 0 0' }}>
            Connect your broker accounts
          </p>
        </div>
        {unconnected.length > 0 && (
          <button className="btn btn-primary" onClick={() => setShowAdd(true)}>
            + Connect Broker
          </button>
        )}
      </div>

      {showAdd && (
        <div className="modal-overlay" onClick={() => setShowAdd(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h2 style={{ fontFamily: 'Outfit', fontSize: 18, margin: '0 0 16px' }}>Connect Broker</h2>
            <div style={{ marginBottom: 12 }}>
              <label style={{ color: '#8888a0', fontSize: 12, display: 'block', marginBottom: 4 }}>Broker</label>
              <select className="select" value={selectedBroker} onChange={(e) => setSelectedBroker(e.target.value)}>
                <option value="">Select broker</option>
                {unconnected.map((b) => (
                  <option key={b} value={b}>{BROKER_INFO[b] || b}</option>
                ))}
              </select>
            </div>
            <div style={{ marginBottom: 12 }}>
              <label style={{ color: '#8888a0', fontSize: 12, display: 'block', marginBottom: 4 }}>API Key / Client ID</label>
              <input className="input" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder="Your broker API key" />
            </div>
            <div style={{ marginBottom: 20 }}>
              <label style={{ color: '#8888a0', fontSize: 12, display: 'block', marginBottom: 4 }}>Secret Key</label>
              <input className="input" type="password" value={secretKey} onChange={(e) => setSecretKey(e.target.value)} placeholder="Your broker secret" />
            </div>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button className="btn btn-secondary" onClick={() => setShowAdd(false)}>Cancel</button>
              <button className="btn btn-primary" onClick={handleAdd} disabled={!selectedBroker || !apiKey}>Connect</button>
            </div>
          </div>
        </div>
      )}

      {loading ? (
        <p style={{ color: '#8888a0' }}>Loading brokers...</p>
      ) : credentials.length === 0 ? (
        <div className="panel" style={{ textAlign: 'center', padding: 48 }}>
          <p style={{ color: '#555570', margin: 0 }}>No brokers connected. Click "Connect Broker" to get started.</p>
        </div>
      ) : (
        <div style={{ display: 'grid', gap: 12 }}>
          {credentials.map((c) => (
            <div key={c.id} className="glass-card" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <h3 style={{ fontFamily: 'Outfit', fontSize: 16, margin: 0 }}>
                  {BROKER_INFO[c.broker] || c.broker}
                </h3>
                <p style={{ color: '#8888a0', fontSize: 12, margin: '4px 0 0' }}>
                  Connected {new Date(c.created_at).toLocaleDateString()}
                </p>
              </div>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <span className={`badge ${c.is_active ? 'badge-green' : 'badge-violet'}`}>
                  {c.is_active ? 'Active' : 'Inactive'}
                </span>
                <button className="btn btn-sm btn-danger" onClick={() => handleDelete(c.broker)}>
                  Disconnect
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
