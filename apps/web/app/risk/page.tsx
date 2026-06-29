'use client'

import { useEffect, useState } from 'react'
import { api } from '@/lib/api'

interface RiskData {
  kill_switch: boolean
  is_live: boolean
  max_daily_loss: number
  max_drawdown: number
  max_open_positions: number
}

export default function RiskPage() {
  const [data, setData] = useState<RiskData>({
    kill_switch: false, is_live: false,
    max_daily_loss: 0, max_drawdown: 0, max_open_positions: 10,
  })
  const [loading, setLoading] = useState(true)
  const [liveConfirm, setLiveConfirm] = useState(false)
  const [showLiveModal, setShowLiveModal] = useState(false)

  const load = async () => {
    try {
      const [ks, live] = await Promise.all([
        api.risk.killSwitchStatus(),
        api.risk.liveStatus(),
      ])
      setData((prev) => ({
        ...prev,
        kill_switch: (ks as { kill_switch_enabled: boolean }).kill_switch_enabled,
        is_live: (live as { is_live: boolean }).is_live,
      }))
    } catch {
      // use defaults
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const toggleKillSwitch = async () => {
    if (data.kill_switch) {
      await api.risk.disableKillSwitch()
    } else {
      await api.risk.enableKillSwitch()
    }
    load()
  }

  const handleEnableLive = async () => {
    await api.risk.enableLive()
    setShowLiveModal(false)
    setLiveConfirm(false)
    load()
  }

  const handleDisableLive = async () => {
    await api.risk.disableLive()
    load()
  }

  if (loading) return <p style={{ color: '#8888a0' }}>Loading risk settings...</p>

  return (
    <div>
      <div className="page-header" style={{ marginBottom: 24 }}>
        <h1 className="page-title">Risk Control</h1>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 24 }}>
        <div className="panel">
          <div className="panel-header">
            <h3 className="panel-title">Kill Switch</h3>
          </div>
          <button
            className={`kill-switch ${data.kill_switch ? 'active' : 'inactive'}`}
            onClick={toggleKillSwitch}
            style={{ width: '100%', justifyContent: 'center' }}
          >
            <span style={{
              width: 10, height: 10, borderRadius: '50%', display: 'inline-block',
              background: data.kill_switch ? '#ef4444' : '#22c55e',
              boxShadow: data.kill_switch ? '0 0 10px #ef4444' : '0 0 10px #22c55e',
            }} />
            {data.kill_switch ? 'KILL SWITCH ACTIVE' : 'Kill Switch Disabled'}
          </button>
          <p style={{ color: '#555570', fontSize: 12, marginTop: 12 }}>
            Instantly halts all trading activity for your account.
          </p>
        </div>

        <div className="panel">
          <div className="panel-header">
            <h3 className="panel-title">Trading Mode</h3>
          </div>
          <div style={{ textAlign: 'center', padding: '16px 0' }}>
            <p style={{ fontSize: 32, fontWeight: 700, margin: 0 }} className={data.is_live ? 'negative' : 'neon-cyan'}>
              {data.is_live ? 'LIVE' : 'PAPER'}
            </p>
            <p style={{ color: '#555570', fontSize: 12, marginTop: 8 }}>
              {data.is_live
                ? 'Live trading is active. All orders will be sent to the broker.'
                : 'Paper mode. Orders are simulated. No real money at risk.'}
            </p>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              className={`btn ${data.is_live ? 'btn-danger' : 'btn-cyan'}`}
              style={{ flex: 1 }}
              onClick={() => data.is_live ? handleDisableLive() : setShowLiveModal(true)}
            >
              {data.is_live ? 'Switch to Paper' : 'Enable Live Trading'}
            </button>
          </div>
        </div>
      </div>

      <div className="panel" style={{ marginBottom: 24 }}>
        <div className="panel-header">
          <h3 className="panel-title">Risk Limits</h3>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
          <div>
            <p style={{ color: '#8888a0', fontSize: 12, margin: '0 0 4px' }}>Max Daily Loss</p>
            <p className="numeric" style={{ fontSize: 20, margin: 0 }}>{data.max_daily_loss || 'Not set'}</p>
          </div>
          <div>
            <p style={{ color: '#8888a0', fontSize: 12, margin: '0 0 4px' }}>Max Drawdown</p>
            <p className="numeric" style={{ fontSize: 20, margin: 0 }}>{data.max_drawdown || 'Not set'}%</p>
          </div>
          <div>
            <p style={{ color: '#8888a0', fontSize: 12, margin: '0 0 4px' }}>Max Open Positions</p>
            <p className="numeric" style={{ fontSize: 20, margin: 0 }}>{data.max_open_positions}</p>
          </div>
        </div>
      </div>

      {showLiveModal && (
        <div className="modal-overlay" onClick={() => setShowLiveModal(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h2 style={{ fontFamily: 'Outfit', fontSize: 18, margin: '0 0 8px', color: '#ef4444' }}>
              WARNING: Enable Live Trading
            </h2>
            <p style={{ color: '#8888a0', fontSize: 14, marginBottom: 16 }}>
              You are about to switch to LIVE trading mode. All signals generated by your strategies
              will be sent directly to your broker using REAL MONEY.
            </p>
            <p style={{ color: '#f59e0b', fontSize: 13, marginBottom: 16 }}>
              Ensure your risk settings are configured correctly before proceeding.
            </p>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 20, cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={liveConfirm}
                onChange={(e) => setLiveConfirm(e.target.checked)}
                style={{ accentColor: '#8b5cf6' }}
              />
              <span style={{ fontSize: 13, color: '#8888a0' }}>
                I understand the risks and want to enable live trading
              </span>
            </label>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button className="btn btn-secondary" onClick={() => setShowLiveModal(false)}>Cancel</button>
              <button className="btn btn-danger" onClick={handleEnableLive} disabled={!liveConfirm}>
                Confirm Live Mode
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
