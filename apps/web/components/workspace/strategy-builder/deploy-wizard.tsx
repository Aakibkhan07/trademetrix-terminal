'use client'

import { useMemo, useState } from 'react'
import { Dialog } from '@/components/ui/dialog'
import { api } from '@/lib/api'

export interface DeploymentDraft {
  symbol: string
  interval: string
  mode: 'paper' | 'live'
  broker: string
  capital: number
  risk_per_trade: number
  max_daily_loss: number
  stop_loss_pct: number
  target_pct: number
  trading_days: string[]
  start_time: string
  end_time: string
  confirm_live: boolean
}

const DEFAULT_DRAFT: DeploymentDraft = {
  symbol: 'NIFTY',
  interval: '15m',
  mode: 'paper',
  broker: '',
  capital: 100000,
  risk_per_trade: 1.0,
  max_daily_loss: 0,
  stop_loss_pct: 0,
  target_pct: 0,
  trading_days: ['MON', 'TUE', 'WED', 'THU', 'FRI'],
  start_time: '09:15',
  end_time: '15:30',
  confirm_live: false,
}

const WEEKDAYS = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN']

export default function DeployWizard({
  strategyId,
  status,
  defaultSymbol,
  onClose,
  onDeployed,
}: {
  strategyId: string
  status: string
  defaultSymbol?: string
  onClose: () => void
  onDeployed: () => void
}) {
  const [draft, setDraft] = useState<DeploymentDraft>({ ...DEFAULT_DRAFT, symbol: defaultSymbol || DEFAULT_DRAFT.symbol })
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')

  const canDeploy = useMemo(() => {
    if (busy) return false
    if (draft.mode === 'live' && !draft.broker.trim()) return false
    if (draft.mode === 'live' && !draft.confirm_live) return false
    if (!draft.symbol.trim()) return false
    return true
  }, [busy, draft, draft.confirm_live])

  const liveNeedsConfirm = draft.mode === 'live' && draft.broker.trim() !== '' && !draft.confirm_live

  const set = <K extends keyof DeploymentDraft>(k: K, v: DeploymentDraft[K]) => {
    setDraft(prev => ({ ...prev, [k]: v }))
  }

  const toggleDay = (d: string) => {
    setDraft(prev => ({
      ...prev,
      trading_days: prev.trading_days.includes(d)
        ? prev.trading_days.filter(x => x !== d)
        : [...prev.trading_days, d].sort(),
    }))
  }

  const deploy = async () => {
    setBusy('Deploying…')
    setError('')
    try {
      await api.builder.deploy(strategyId, {
        symbol: draft.symbol,
        interval: draft.interval,
        mode: draft.mode,
        broker: draft.broker,
        confirm_live: draft.confirm_live,
        capital: draft.capital,
        risk: {
          risk_per_trade: draft.risk_per_trade,
          max_daily_loss: draft.max_daily_loss,
          stop_loss_pct: draft.stop_loss_pct,
          target_pct: draft.target_pct,
        },
        schedule: {
          trading_days: draft.trading_days,
          start_time: draft.start_time,
          end_time: draft.end_time,
          timezone: 'Asia/Kolkata',
        },
      })
      onDeployed()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Deployment failed')
    } finally {
      setBusy('')
    }
  }

  return (
    <Dialog onClose={onClose} maxWidth={560} padding={0} title={
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 14px', borderBottom: '1px solid var(--border)' }}>
        <div>
          <span style={{ fontSize: 13, fontWeight: 700 }}>Deploy Strategy</span>
          <span className={`t-badge ${status === 'live' ? 't-badge-green' : status === 'paper' ? 't-badge-cyan' : 't-badge-sub'}`} style={{ fontSize: 9, marginLeft: 8, textTransform: 'uppercase' }}>
            {status}
          </span>
        </div>
        <button className="t-btn t-btn-sm" onClick={onClose}>✕</button>
      </div>
    }>
        <div style={{ padding: 14, maxHeight: '60vh', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div className="t-seg" style={{ alignSelf: 'flex-start' }}>
            <button className={`t-seg-btn ${draft.mode === 'paper' ? 'active' : ''}`} onClick={() => set('mode', 'paper')} style={{ fontSize: 11, padding: '0 12px' }}>
              📄 Paper
            </button>
            <button className={`t-seg-btn ${draft.mode === 'live' ? 'active' : ''}`} onClick={() => { set('confirm_live', false); set('mode', 'live') }} style={{ fontSize: 11, padding: '0 12px' }}>
              ⚡ Live
            </button>
          </div>

          {liveNeedsConfirm && (
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8, padding: '8px 10px', borderRadius: 8, background: 'color-mix(in srgb, var(--red) 8%, transparent)', border: '1px solid color-mix(in srgb, var(--red) 25%, transparent)' }}>
              <input
                type="checkbox"
                id="confirm-live"
                checked={draft.confirm_live}
                onChange={e => set('confirm_live', e.target.checked)}
              />
              <label htmlFor="confirm-live" style={{ fontSize: 11, color: 'var(--text)', margin: 0 }}>
                <strong>I confirm this deploys real money on {draft.broker.toUpperCase()}.</strong> Live orders are executed through the broker with risk checks and can only be stopped via the Kill Switch / Emergency Stop.
              </label>
            </div>
          )}

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <div>
              <label className="t-stat-label" style={{ display: 'block', marginBottom: 4 }}>Symbol</label>
              <input className="t-input" value={draft.symbol} onChange={e => set('symbol', e.target.value)} placeholder="NIFTY" />
            </div>
            <div>
              <label className="t-stat-label" style={{ display: 'block', marginBottom: 4 }}>Interval</label>
              <select className="t-select" value={draft.interval} onChange={e => set('interval', e.target.value)}>
                {['1m', '5m', '15m', '30m', '1h', '4h', '1d'].map(i => <option key={i} value={i}>{i}</option>)}
              </select>
            </div>
          </div>

          <div>
            <label className="t-stat-label" style={{ display: 'block', marginBottom: 4 }}>
              Broker {draft.mode === 'live' && <span style={{ color: 'var(--red)' }}>*</span>}
            </label>
            <select className="t-select" value={draft.broker} onChange={e => set('broker', e.target.value)}>
              <option value="">{draft.mode === 'live' ? 'Select broker…' : 'Paper broker (default)'}</option>
              <option value="fyers">Fyers</option>
              <option value="angelone">Angel One</option>
              <option value="zerodha">Zerodha</option>
            </select>
            {draft.mode === 'live' && !draft.broker && (
              <p style={{ margin: '4px 0 0', fontSize: 10, color: 'var(--red)' }}>Live deployment requires a connected broker</p>
            )}
          </div>

          <div>
            <label className="t-stat-label" style={{ display: 'block', marginBottom: 4 }}>Capital (₹)</label>
            <input className="t-input" type="number" value={draft.capital} onChange={e => set('capital', Number(e.target.value))} />
          </div>

          <div>
            <p className="t-stat-label" style={{ margin: '0 0 6px' }}>Risk</p>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
              <div>
                <input className="t-input" type="number" step="0.1" value={draft.risk_per_trade} onChange={e => set('risk_per_trade', Number(e.target.value))} />
                <label className="t-stat-label" style={{ fontSize: 9, display: 'block', marginTop: 2 }}>Risk / trade %</label>
              </div>
              <div>
                <input className="t-input" type="number" value={draft.max_daily_loss} onChange={e => set('max_daily_loss', Number(e.target.value))} />
                <label className="t-stat-label" style={{ fontSize: 9, display: 'block', marginTop: 2 }}>Max daily loss</label>
              </div>
              <div>
                <input className="t-input" type="number" step="0.1" value={draft.stop_loss_pct} onChange={e => set('stop_loss_pct', Number(e.target.value))} />
                <label className="t-stat-label" style={{ fontSize: 9, display: 'block', marginTop: 2 }}>SL %</label>
              </div>
            </div>
          </div>

          <div>
            <label className="t-stat-label" style={{ display: 'block', marginBottom: 4 }}>Trading days</label>
            <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
              {WEEKDAYS.map(d => (
                <button
                  key={d}
                  className={`t-btn t-btn-sm ${draft.trading_days.includes(d) ? 't-btn-primary' : ''}`}
                  onClick={() => toggleDay(d)}
                  style={{ fontSize: 9, padding: '2px 8px' }}
                >
                  {d}
                </button>
              ))}
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <div>
              <label className="t-stat-label" style={{ display: 'block', marginBottom: 4 }}>Start time</label>
              <input className="t-input" type="time" value={draft.start_time} onChange={e => set('start_time', e.target.value)} />
            </div>
            <div>
              <label className="t-stat-label" style={{ display: 'block', marginBottom: 4 }}>End time</label>
              <input className="t-input" type="time" value={draft.end_time} onChange={e => set('end_time', e.target.value)} />
            </div>
          </div>

          {error && <p style={{ margin: 0, fontSize: 11, color: 'var(--red)' }}>{error}</p>}
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, padding: '10px 14px', borderTop: '1px solid var(--border)' }}>
          <button className="t-btn" onClick={onClose} disabled={!!busy}>Cancel</button>
          <button className="t-btn t-btn-primary" onClick={deploy} disabled={!canDeploy}>
            {busy ? busy : draft.mode === 'live' ? 'Deploy Live' : 'Deploy Paper'}
          </button>
        </div>
    </Dialog>
  )
}
