'use client'

import { useEffect, useRef, useState } from 'react'
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
  aliceblue: { name: 'Alice Blue', icon: 'A', latency: '< 12ms', status: 'Connected' },
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
  const [clientCode, setClientCode] = useState('')
  const [secretKey, setSecretKey] = useState('')
  const [totpSecret, setTotpSecret] = useState('')
  const [msg, setMsg] = useState('')
  const [msgType, setMsgType] = useState<'success' | 'error'>('success')

  const msgTimer = useRef<ReturnType<typeof setTimeout>>()

  const showMsg = (text: string, type: 'success' | 'error' = 'success') => {
    setMsg(text)
    setMsgType(type)
    if (msgTimer.current) clearTimeout(msgTimer.current)
    msgTimer.current = setTimeout(() => { setMsg(''); msgTimer.current = undefined }, 12000)
  }

  const load = async () => {
    try {
      const [credData, brokerData] = await Promise.all([
        api.brokers.credentials(),
        api.brokers.list(),
      ])
      if (mountedRef.current) {
        setCredentials((credData as { credentials: BrokerCred[] }).credentials || [])
        setAvailable((brokerData as { brokers: string[] }).brokers || [])
      }
    } catch {
      if (mountedRef.current) { setCredentials([]); setAvailable([]) }
    } finally {
      if (mountedRef.current) setLoading(false)
    }
  }

  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    const fallback = setTimeout(() => { if (mountedRef.current) setLoading(false) }, 8000)
    load().finally(() => clearTimeout(fallback))
    return () => { mountedRef.current = false; clearTimeout(fallback) }
  }, [])

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const authCode = params.get('auth_code')
    let cancelled = false
    if (authCode) {
      api.brokers.fyersExchangeCode(authCode).then(() => {
        if (cancelled) return
        showMsg('Fyers authenticated successfully! Market feed will start shortly.')
        load()
      }).catch(() => {
        if (cancelled) return
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
    return () => { cancelled = true }
  }, [])

  const handleAdd = async () => {
    try {
      const additional_params: Record<string, string> = {}
      if (totpSecret) additional_params.totp_secret = totpSecret
      if (clientCode) additional_params.client_code = clientCode
      await api.brokers.saveCredentials({ broker: selectedBroker, api_key: apiKey, secret_key: secretKey, additional_params: Object.keys(additional_params).length ? additional_params : undefined })
      setShowAdd(false)
      setSelectedBroker('')
      setApiKey('')
      setClientCode('')
      setSecretKey('')
      setTotpSecret('')
      if (selectedBroker === 'fyers') {
        const authData = await api.brokers.fyersAuthUrl() as { auth_url: string }
        showMsg(`Fyers app ID saved! Click the link that opened to login.`)
        if (authData.auth_url) window.open(authData.auth_url, '_blank')
      } else {
        showMsg(`${BROKER_INFO[selectedBroker]?.name || selectedBroker} connected successfully`)
      }
      load()
    } catch (e: any) {
      showMsg(e?.message || 'Failed to save credentials', 'error')
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
      showMsg(e?.message || 'Re-authentication failed', 'error')
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
      <div className="t-row" style={{ alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <div>
          <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 22, fontWeight: 600, margin: 0, color: '#f0f0f5' }}>Brokers</h1>
          <p className="t-faint" style={{ margin: '2px 0 0' }}>
            Connect and manage your broker accounts
          </p>
        </div>
        <button className="t-btn t-btn-primary" onClick={() => setShowAdd(true)}>
          + Connect Broker
        </button>
      </div>

      {msg && (
        <div style={{
          background: msgType === 'error' ? 'rgba(239,68,68,0.1)' : 'rgba(34,197,94,0.1)',
          border: `1px solid ${msgType === 'error' ? 'rgba(239,68,68,0.2)' : 'rgba(34,197,94,0.2)'}`,
          borderRadius: 8, padding: '10px 14px', marginBottom: 16
        }}>
          <p style={{ color: msgType === 'error' ? '#ef4444' : '#22c55e', fontSize: 13, margin: 0 }}>
            {msg}
          </p>
        </div>
      )}

      {showAdd && (
        <div className="t-modal-overlay" onClick={() => setShowAdd(false)}>
          <div className="t-modal" onClick={(e) => e.stopPropagation()}>
            <div className="t-modal-title">Connect Broker</div>
            <div style={{ marginBottom: 16 }}>
              <div className="t-grid-2" style={{ gap: 8 }}>
                {unconnected.map((b) => {
                  const info = BROKER_INFO[b]
                  if (!info || info.status === 'Coming Soon') return null
                  return (
                    <div
                      key={b}
                      onClick={() => setSelectedBroker(b)}
                      className={`t-chip${selectedBroker === b ? ' active' : ''}`}
                      style={{ textAlign: 'center', padding: '10px', cursor: 'pointer' }}
                    >
                      <div style={{
                        width: 32, height: 32, borderRadius: 8,
                        background: 'rgba(139,92,246,0.12)',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        margin: '0 auto 6px', fontSize: 14, fontWeight: 700, color: '#8b5cf6'
                      }}>
                        {info.icon}
                      </div>
                      <p style={{ margin: 0, fontSize: 11, fontWeight: 600 }}>{info.name}</p>
                      <p className="t-sub" style={{ margin: '2px 0 0', fontSize: 9 }}>{info.latency}</p>
                    </div>
                  )
                })}
              </div>
            </div>
            {selectedBroker && (
              <div style={{ marginBottom: 16 }}>
                <div style={{ marginBottom: 12 }}>
                  <label className="t-label">
                    {selectedBroker === 'dhan' ? 'Client ID' : selectedBroker === 'angelone' ? 'API Key (SmartAPI App Key)' : 'API Key'}
                  </label>
                  <input className="t-input" value={apiKey} onChange={(e) => setApiKey(e.target.value)}
                    placeholder={selectedBroker === 'dhan' ? 'Your Dhan client ID' : selectedBroker === 'angelone' ? 'Your SmartAPI app key' : 'Your broker API key'} />
                </div>
                {selectedBroker === 'angelone' && (
                  <div style={{ marginBottom: 12 }}>
                    <label className="t-label">Client ID (Angel One Login ID)</label>
                    <input className="t-input" value={clientCode} onChange={(e) => setClientCode(e.target.value)}
                      placeholder="Your Angel One trading account ID" />
                  </div>
                )}
                <div style={{ marginBottom: selectedBroker === 'angelone' ? 12 : 20 }}>
                  <label className="t-label">
                    {selectedBroker === 'angelone' ? 'Password/PIN' : selectedBroker === 'dhan' ? 'Access Token' : 'Secret Key'}
                  </label>
                  <input className="t-input" type="password" value={secretKey} onChange={(e) => setSecretKey(e.target.value)}
                    placeholder={selectedBroker === 'angelone' ? 'Your Angel One login password' : selectedBroker === 'dhan' ? 'Your Dhan access token (JWT)' : 'Your broker secret'} />
                </div>
                {selectedBroker === 'angelone' && (
                  <div style={{ marginBottom: 20 }}>
                    <label className="t-label">TOTP Secret (Base32)</label>
                    <input className="t-input" type="password" value={totpSecret} onChange={(e) => setTotpSecret(e.target.value)}
                      placeholder="Your Angel One TOTP secret key" />
                  </div>
                )}
              </div>
            )}
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button className="t-btn t-btn-ghost" onClick={() => setShowAdd(false)}>Cancel</button>
              <button className="t-btn t-btn-primary" onClick={handleAdd} disabled={!selectedBroker || !apiKey}>Connect</button>
            </div>
          </div>
        </div>
      )}

      {loading ? (
        <p className="t-faint">Loading brokers...</p>
      ) : (
        <>
          {credentials.length > 0 && (
            <>
              <h2 className="t-panel-title" style={{ fontSize: 15, marginBottom: 12 }}>
                Connected Brokers ({credentials.length})
              </h2>
              <div className="t-grid-auto" style={{ marginBottom: 28 }}>
                {credentials.map((c) => {
                  const info = BROKER_INFO[c.broker]
                  return (
                    <div key={c.id} className="t-panel" style={{ padding: 0 }}>
                      <div style={{ padding: 18, display: 'flex', alignItems: 'center', gap: 14 }}>
                        <div style={{
                          width: 40, height: 40, borderRadius: 10,
                          background: 'rgba(139,92,246,0.12)',
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                          fontSize: 18, fontWeight: 700, color: '#8b5cf6'
                        }}>
                          {info?.icon || c.broker[0].toUpperCase()}
                        </div>
                        <div style={{ flex: 1 }}>
                          <h3 style={{ fontFamily: 'var(--font-display)', fontSize: 14, margin: 0 }}>
                            {info?.name || c.broker}
                          </h3>
                          <p className="t-faint" style={{ margin: '2px 0 0', fontSize: 11 }}>
                            Connected {new Date(c.created_at).toLocaleDateString()} · Latency {info?.latency || '-'}
                          </p>
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 6 }}>
                          <span className={`t-badge ${c.is_active ? 't-badge-green' : 't-badge-violet'}`} style={{ fontSize: 9, padding: '2px 8px' }}>
                            {c.is_active ? 'Active' : 'Inactive'}
                          </span>
                          {c.broker === 'fyers' && (
                            <button className="t-btn t-btn-sm t-btn-primary" style={{ fontSize: 10, padding: '3px 8px' }} onClick={handleFyersReAuth}>
                              Re-authenticate
                            </button>
                          )}
                          <button className="t-btn t-btn-sm t-btn-danger" style={{ fontSize: 10, padding: '3px 8px' }} onClick={() => handleDelete(c.broker)}>
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

          <div className="t-panel" style={{ marginBottom: 20 }}>
            <div className="t-panel-header">
              <h3 className="t-panel-title">
                <span style={{ marginRight: 6 }}>TV</span>
                TradingView Webhook Integration
              </h3>
            </div>
            <div className="t-panel-body">
              <p className="t-faint" style={{ fontSize: 12, margin: '0 0 8px' }}>
                Connect TradingView strategies via webhook. Configure alerts to POST to the endpoint below.
              </p>
              <div style={{
                background: 'rgba(0,0,0,0.2)', borderRadius: 6, padding: 10,
                fontFamily: 'var(--font-mono)', fontSize: 11, wordBreak: 'break-all', marginBottom: 8
              }}>
                <span style={{ color: '#22d3ee' }}>POST</span>{' '}
                <span style={{ color: '#f0f0f5' }}>
                  {process.env.NEXT_PUBLIC_API_URL || 'https://api.ai.trademetrix.tech/api/v1'}/tradingview/webhook
                </span>
              </div>
              <div className="t-grid-2" style={{ gap: 8, fontSize: 11, marginBottom: 8 }}>
                <div>
                  <p className="t-label" style={{ margin: '0 0 2px' }}>Request Format</p>
                  <pre style={{
                    margin: 0, fontSize: 10, color: '#8888a0',
                    background: 'rgba(0,0,0,0.15)', padding: 8, borderRadius: 4, lineHeight: 1.5
                  }}>
{`{
  "symbol": "NIFTY",
  "action": "BUY",
  "quantity": 65,
  "price": 0,
  "exchange": "NSE",
  "order_type": "MARKET",
  "product": "INTRADAY",
  "paper": true
}`}
                  </pre>
                </div>
                <div>
                  <p className="t-label" style={{ margin: '0 0 2px' }}>Pine Script Alert</p>
                  <pre style={{
                    margin: 0, fontSize: 10, color: '#8888a0',
                    background: 'rgba(0,0,0,0.15)', padding: 8, borderRadius: 4, lineHeight: 1.5
                  }}>
{`// In Strategy settings:
// Alert → Webhook URL
// Message:
{"symbol":"{{ticker}}",
 "action":"{{strategy.order.action}}",
 "quantity":{{strategy.order.contracts}},
 "paper":true}`}
                  </pre>
                </div>
              </div>
              <p className="t-sub" style={{ fontSize: 10, margin: 0 }}>
                Set <code style={{ color: '#22d3ee' }}>paper: false</code> for live execution. Optionally set{' '}
                <code style={{ color: '#22d3ee' }}>TRADINGVIEW_WEBHOOK_SECRET</code> env for HMAC verification.
              </p>
            </div>
          </div>

          <h2 className="t-panel-title" style={{ fontSize: 15, marginBottom: 12 }}>
            Available Brokers
          </h2>
          <div className="t-grid-auto">
            {Object.entries(BROKER_INFO).filter(([b]) => !connectedBrokers.includes(b)).map(([key, info]) => (
              <div key={key} className="t-panel" style={{
                padding: 16, textAlign: 'center',
                opacity: info.status === 'Coming Soon' ? 0.5 : 1
              }}>
                <div style={{
                  width: 40, height: 40, borderRadius: 10,
                  background: info.status === 'Connected' ? 'rgba(34,197,94,0.1)' : 'rgba(139,92,246,0.06)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  margin: '0 auto 8px', fontSize: 18, fontWeight: 700,
                  color: info.status === 'Connected' ? '#22c55e' : '#555570'
                }}>
                  {info.icon}
                </div>
                <p style={{ margin: 0, fontSize: 13, fontWeight: 600 }}>{info.name}</p>
                <p className="t-sub" style={{ margin: '2px 0 0', fontSize: 10 }}>Latency {info.latency}</p>
                <span className={`t-badge ${info.status === 'Connected' ? 't-badge-green' : 't-badge-violet'}`}
                  style={{ fontSize: 9, padding: '1px 6px', marginTop: 6 }}>
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
