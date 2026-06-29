'use client'

import { useEffect, useState } from 'react'
import { api } from '@/lib/api'

const BROKER_INFO: Record<string, { name: string; icon: string; latency: string; status: string }> = {
  zerodha: { name: 'Zerodha (Kite)', icon: 'Z', latency: '< 5ms', status: 'Connected' },
  angelone: { name: 'Angel One', icon: 'A', latency: '< 8ms', status: 'Connected' },
  upstox: { name: 'Upstox', icon: 'U', latency: '< 5ms', status: 'Connected' },
  dhan: { name: 'Dhan', icon: 'D', latency: '< 6ms', status: 'Connected' },
  fyers: { name: 'Fyers', icon: 'F', latency: '< 8ms', status: 'Connected' },
  fivepaisa: { name: '5Paisa', icon: '5', latency: '< 8ms', status: 'Connected' },
  icici: { name: 'ICICI Direct', icon: 'I', latency: '< 10ms', status: 'Coming Soon' },
  hdfc: { name: 'HDFC Securities', icon: 'H', latency: '< 10ms', status: 'Coming Soon' },
  kotakneo: { name: 'Kotak Neo', icon: 'K', latency: '< 8ms', status: 'Connected' },
  aliceblue: { name: 'Alice Blue', icon: 'A', latency: '< 12ms', status: 'Coming Soon' },
  finvasia: { name: 'Shoonya', icon: 'S', latency: '< 6ms', status: 'Connected' },
  groww: { name: 'Groww', icon: 'G', latency: '-', status: 'Coming Soon' },
  iifl: { name: 'IIFL', icon: 'I', latency: '< 12ms', status: 'Coming Soon' },
  flattrade: { name: 'Flattrade', icon: 'F', latency: '< 8ms', status: 'Connected' },
  motilal: { name: 'Motilal Oswal', icon: 'M', latency: '-', status: 'Coming Soon' },
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
  const [msg, setMsg] = useState('')
  const [msgType, setMsgType] = useState<'success' | 'error'>('success')

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

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const authCode = params.get('auth_code')
    if (authCode) {
      api.brokers.fyersExchangeCode(authCode).then(() => {
        showMsg('Fyers authenticated successfully! Market feed will start shortly.')
        load()
      }).catch(() => {
        showMsg('Failed to exchange Fyers auth code. Try again.', 'error')
      })
    } else if (params.get('auth_success')) {
      showMsg('Fyers authenticated successfully! Market feed will start shortly.')
      load()
    } else if (params.get('auth_error')) {
      showMsg(`Fyers auth error: ${params.get('auth_error')}`, 'error')
    }
    if (authCode || params.get('auth_success') || params.get('auth_error')) {
      const url = new URL(window.location.href)
      url.searchParams.delete('auth_code')
      url.searchParams.delete('state')
      url.searchParams.delete('auth_success')
      url.searchParams.delete('auth_error')
      window.history.replaceState({}, '', url.toString())
    }
  }, [])

  const handleAdd = async () => {
    try {
      await api.brokers.saveCredentials({ broker: selectedBroker, api_key: apiKey, secret_key: secretKey })
      setShowAdd(false)
      setSelectedBroker('')
      setApiKey('')
      setSecretKey('')
      if (selectedBroker === 'fyers') {
        const authData = await api.brokers.fyersAuthUrl() as { auth_url: string }
        showMsg(`Fyers app ID saved! Click the link that opened to login.`)
        if (authData.auth_url) window.open(authData.auth_url, '_blank')
      } else {
        showMsg(`${BROKER_INFO[selectedBroker]?.name || selectedBroker} connected successfully`)
      }
      load()
    } catch (e: any) {
      const detail = e?.detail || e?.message || 'Failed to save credentials'
      showMsg(detail, 'error')
    }
  }

  const handleFyersReAuth = async () => {
    try {
      const data = await api.brokers.fyersReAuth() as { auth_url: string }
      if (data.auth_url) {
        window.open(data.auth_url, '_blank')
        showMsg('Fyers re-authentication link opened in new tab.')
      } else {
        showMsg('Failed to get Fyers auth URL', 'error')
      }
    } catch (e: any) {
      showMsg(e?.detail || 'Re-authentication failed', 'error')
    }
  }

  const handleDelete = async (broker: string) => {
    try {
      await api.brokers.deleteCredentials(broker)
      showMsg(`${BROKER_INFO[broker]?.name || broker} disconnected`)
      load()
    } catch {
      showMsg('Failed to disconnect broker', 'error')
    }
  }

  const connectedBrokers = credentials.map((c) => c.broker)
  const unconnected = Object.keys(BROKER_INFO).filter((b) => !connectedBrokers.includes(b))

  return (
    <div>
      <div className="page-header" style={{ flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h1 className="page-title">Brokers</h1>
          <p className="page-subtitle">
            Connect and manage your broker accounts
          </p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowAdd(true)}>
          + Connect Broker
        </button>
      </div>

      {msg && (
        <div style={{ background: msgType === 'error' ? 'rgba(239,68,68,0.1)' : 'rgba(34,197,94,0.1)', border: `1px solid ${msgType === 'error' ? 'rgba(239,68,68,0.2)' : 'rgba(34,197,94,0.2)'}`, borderRadius: 8, padding: '10px 14px', marginBottom: 16 }}>
          <p style={{ color: msgType === 'error' ? '#ef4444' : '#22c55e', fontSize: 13, margin: 0 }}>{msg}</p>
        </div>
      )}

      {showAdd && (
        <div className="modal-overlay" onClick={() => setShowAdd(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h2 style={{ fontFamily: 'Outfit', fontSize: 18, margin: '0 0 16px' }}>Connect Broker</h2>
            <div style={{ marginBottom: 16, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
              {unconnected.map((b) => {
                const info = BROKER_INFO[b]
                if (!info || info.status === 'Coming Soon') return null
                return (
                  <div
                    key={b}
                    onClick={() => setSelectedBroker(b)}
                    style={{
                      padding: '10px', borderRadius: 8, cursor: 'pointer',
                      border: selectedBroker === b ? '1px solid #8b5cf6' : '1px solid rgba(139,92,246,0.12)',
                      background: selectedBroker === b ? 'rgba(139,92,246,0.08)' : 'transparent',
                      textAlign: 'center', transition: 'all 150ms ease',
                    }}
                  >
                    <div style={{ width: 32, height: 32, borderRadius: 8, background: 'rgba(139,92,246,0.12)', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 6px', fontSize: 14, fontWeight: 700, color: '#8b5cf6' }}>{info.icon}</div>
                    <p style={{ margin: 0, fontSize: 11, fontWeight: 600 }}>{info.name}</p>
                    <p style={{ margin: '2px 0 0', fontSize: 9, color: '#555570' }}>{info.latency}</p>
                  </div>
                )
              })}
            </div>
            {selectedBroker && (
              <>
                <div style={{ marginBottom: 12 }}>
                  <label style={{ color: '#8888a0', fontSize: 12, display: 'block', marginBottom: 4 }}>API Key / Client ID</label>
                  <input className="input" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder="Your broker API key" />
                </div>
                <div style={{ marginBottom: 20 }}>
                  <label style={{ color: '#8888a0', fontSize: 12, display: 'block', marginBottom: 4 }}>Secret Key</label>
                  <input className="input" type="password" value={secretKey} onChange={(e) => setSecretKey(e.target.value)} placeholder="Your broker secret" />
                </div>
              </>
            )}
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button className="btn btn-secondary" onClick={() => setShowAdd(false)}>Cancel</button>
              <button className="btn btn-primary" onClick={handleAdd} disabled={!selectedBroker || !apiKey}>Connect</button>
            </div>
          </div>
        </div>
      )}

      {loading ? (
        <p style={{ color: '#8888a0' }}>Loading brokers...</p>
      ) : (
        <>
          {credentials.length > 0 && (
            <>
              <h2 style={{ fontFamily: 'Outfit', fontSize: 15, margin: '0 0 12px', color: '#f0f0f5' }}>
                Connected Brokers ({credentials.length})
              </h2>
              <div className="grid-auto" style={{ marginBottom: 28 }}>
                {credentials.map((c) => {
                  const info = BROKER_INFO[c.broker]
                  return (
                    <div key={c.id} className="strategy-card" style={{ padding: 0 }}>
                      <div style={{ padding: '18px', display: 'flex', alignItems: 'center', gap: 14 }}>
                        <div style={{ width: 40, height: 40, borderRadius: 10, background: 'rgba(139,92,246,0.12)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18, fontWeight: 700, color: '#8b5cf6' }}>
                          {info?.icon || c.broker[0].toUpperCase()}
                        </div>
                        <div style={{ flex: 1 }}>
                          <h3 style={{ fontFamily: 'Outfit', fontSize: 14, margin: 0 }}>{info?.name || c.broker}</h3>
                          <p style={{ margin: '2px 0 0', fontSize: 11, color: '#555570' }}>
                            Connected {new Date(c.created_at).toLocaleDateString()} · Latency {info?.latency || '-'}
                          </p>
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 6 }}>
                          <span className={`badge ${c.is_active ? 'badge-green' : 'badge-violet'}`} style={{ fontSize: 9, padding: '2px 8px' }}>
                            {c.is_active ? 'Active' : 'Inactive'}
                          </span>
                          {c.broker === 'fyers' && (
                            <button className="btn btn-sm btn-primary" style={{ fontSize: 10, padding: '3px 8px' }} onClick={handleFyersReAuth}>
                              Re-authenticate
                            </button>
                          )}
                          <button className="btn btn-sm btn-danger" style={{ fontSize: 10, padding: '3px 8px' }} onClick={() => handleDelete(c.broker)}>
                            Disconnect
                          </button>
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            </>
          )}

          <h2 style={{ fontFamily: 'Outfit', fontSize: 15, margin: '0 0 12px', color: '#f0f0f5' }}>
            Available Brokers
          </h2>
          <div className="grid-auto">
            {Object.entries(BROKER_INFO).filter(([b]) => !connectedBrokers.includes(b)).map(([key, info]) => (
              <div key={key} className="glass-card" style={{ padding: '16px', textAlign: 'center', opacity: info.status === 'Coming Soon' ? 0.5 : 1 }}>
                <div style={{ width: 40, height: 40, borderRadius: 10, background: info.status === 'Connected' ? 'rgba(34,197,94,0.1)' : 'rgba(139,92,246,0.06)', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 8px', fontSize: 18, fontWeight: 700, color: info.status === 'Connected' ? '#22c55e' : '#555570' }}>
                  {info.icon}
                </div>
                <p style={{ margin: 0, fontSize: 13, fontWeight: 600 }}>{info.name}</p>
                <p style={{ margin: '2px 0 0', fontSize: 10, color: '#555570' }}>Latency {info.latency}</p>
                <span className={`badge ${info.status === 'Connected' ? 'badge-green' : 'badge-violet'}`} style={{ fontSize: 9, padding: '1px 6px', marginTop: 6 }}>
                  {info.status}
                </span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
