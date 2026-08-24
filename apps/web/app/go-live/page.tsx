'use client'

// Go-Live Wizard — the guided path from zero to a running strategy:
// Broker → Strategy → Mode & Symbols → Deploy. Paper-first by default.

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { api } from '@/lib/api'
import { track } from '@/lib/analytics'

interface Cred { broker: string; is_active: boolean }
interface UserStrategy { id: string; name: string; type?: string; is_active?: boolean }
interface AssignedStrategy { strategy_key: string; name: string; description: string; required_tier: string }

const STEPS = ['Broker', 'Strategy', 'Mode', 'Deploy']
const DEFAULT_SYMBOLS = 'NSE:NIFTY50-INDEX'

export default function GoLivePage() {
  const router = useRouter()
  const [step, setStep] = useState(0)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  // step 1
  const [creds, setCreds] = useState<Cred[]>([])
  const [broker, setBroker] = useState('')
  // step 2
  const [strategies, setStrategies] = useState<UserStrategy[]>([])
  const [assigned, setAssigned] = useState<AssignedStrategy[]>([])
  const [strategyId, setStrategyId] = useState('')
  // step 3
  const [mode, setMode] = useState<'PAPER' | 'LIVE'>('PAPER')
  const [symbols, setSymbols] = useState(DEFAULT_SYMBOLS)
  const [liveConfirm, setLiveConfirm] = useState('')
  // deploy
  const [runId, setRunId] = useState('')
  const [tgLinked, setTgLinked] = useState<boolean | null>(null)

  useEffect(() => {
    api.brokers.credentials().then((c: unknown) => {
      const list = ((c as { credentials?: Cred[] }).credentials || []) as Cred[]
      const active = list.filter(x => x.is_active)
      setCreds(active)
      if (active.length === 1) setBroker(active[0].broker)
    }).catch(() => {})
    api.strategies.list().then((s: unknown) => {
      setStrategies(((s as { strategies?: UserStrategy[] }).strategies || []) as UserStrategy[])
    }).catch(() => {})
    api.strategies.assigned().then((s: unknown) => {
      setAssigned(((s as { strategies?: AssignedStrategy[] }).strategies || []) as AssignedStrategy[])
    }).catch(() => {})
    api.notifications.telegramStatus().then((s: unknown) => {
      setTgLinked((s as { linked?: boolean }).linked === true)
    }).catch(() => setTgLinked(null))
  }, [])

  const canNext = () => {
    if (step === 0) return !!broker
    if (step === 1) return !!strategyId
    if (step === 2) return mode === 'PAPER' || liveConfirm.trim().toUpperCase() === 'LIVE'
    return true
  }

  const createFromCatalog = async (a: AssignedStrategy) => {
    setError(''); setBusy(true)
    try {
      const created = await api.strategies.create({
        name: a.name || a.strategy_key,
        type: a.strategy_key,
        config: {},
      }) as unknown as { id?: string; strategy_id?: string }
      const id = created.id || created.strategy_id
      if (!id) throw new Error('Strategy created but no id returned')
      setStrategies(prev => [{ id, name: a.name || a.strategy_key, type: a.strategy_key }, ...prev])
      setStrategyId(id)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Could not create strategy')
    } finally {
      setBusy(false)
    }
  }

  const deploy = async () => {
    setError(''); setBusy(true)
    try {
      const res = await api.engine.start({
        strategy_id: strategyId,
        broker,
        mode,
        symbols: symbols.split(',').map(s => s.trim()).filter(Boolean),
      }) as unknown as { run_id?: string; id?: string }
      setRunId(res.run_id || res.id || '')
      track(mode === 'LIVE' ? 'golive.live' : 'golive.paper')
      setStep(4)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Deployment failed')
    } finally {
      setBusy(false)
    }
  }

  const selectedStrategy = strategies.find(s => s.id === strategyId)

  return (
    <div style={{ maxWidth: 720, margin: '0 auto' }}>
      <div className="t-page-header" style={{ marginBottom: 16 }}>
        <div>
          <h1 className="t-page-title">Go Live</h1>
          <p className="t-page-subtitle">From zero to an automated strategy in four steps</p>
        </div>
      </div>

      {/* progress */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 20 }}>
        {STEPS.map((label, i) => (
          <div key={label} style={{ flex: 1 }}>
            <div style={{
              height: 4, borderRadius: 2,
              background: i <= step && !(step === 4) ? 'var(--violet)' : 'var(--panel-2)',
            }} />
            <div style={{
              fontSize: 10, marginTop: 5, letterSpacing: 0.5,
              color: i <= step ? 'var(--violet)' : 'var(--text-faint)',
              fontWeight: i === step ? 700 : 400,
            }}>{label.toUpperCase()}</div>
          </div>
        ))}
      </div>

      {error && (
        <div style={{
          padding: '10px 14px', borderRadius: 8, fontSize: 12, marginBottom: 14,
          background: 'rgba(248,113,113,0.08)', border: '1px solid rgba(248,113,113,0.15)',
          color: 'var(--text-red)',
        }}>{error}</div>
      )}

      {/* STEP 1: broker */}
      {step === 0 && (
        <div className="t-panel" style={{ padding: 18 }}>
          <h3 className="t-panel-title" style={{ marginBottom: 4 }}>Step 1 · Connect your broker</h3>
          <p className="t-faint" style={{ fontSize: 12, marginBottom: 14 }}>
            Pick the broker account this strategy should trade on.
          </p>
          {creds.length === 0 ? (
            <div>
              <p className="t-faint" style={{ fontSize: 12, marginBottom: 12 }}>No connected brokers yet.</p>
              <Link href="/brokers" className="t-btn t-btn-sm t-btn-primary">Connect a broker first</Link>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {creds.map(c => (
                <button
                  key={c.broker}
                  onClick={() => setBroker(c.broker)}
                  className="t-btn"
                  style={{
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    textAlign: 'left', padding: '12px 14px',
                    border: `1px solid ${broker === c.broker ? 'var(--violet)' : 'var(--border)'}`,
                    background: broker === c.broker ? 'color-mix(in srgb, var(--violet) 8%, transparent)' : 'transparent',
                  }}>
                  <span style={{ fontSize: 13, fontWeight: 600, textTransform: 'capitalize' }}>{c.broker}</span>
                  {broker === c.broker && <span style={{ fontSize: 11, color: 'var(--violet)' }}>SELECTED</span>}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* STEP 2: strategy */}
      {step === 1 && (
        <div className="t-panel" style={{ padding: 18 }}>
          <h3 className="t-panel-title" style={{ marginBottom: 4 }}>Step 2 · Choose your strategy</h3>
          <p className="t-faint" style={{ fontSize: 12, marginBottom: 14 }}>
            Pick an existing strategy, or create one from your plan&rsquo;s catalog.
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 16 }}>
            {strategies.length === 0 && (
              <p className="t-faint" style={{ fontSize: 12 }}>No strategies yet — create one below.</p>
            )}
            {strategies.map(s => (
              <button
                key={s.id}
                onClick={() => setStrategyId(s.id)}
                className="t-btn"
                style={{
                  textAlign: 'left', padding: '12px 14px',
                  border: `1px solid ${strategyId === s.id ? 'var(--violet)' : 'var(--border)'}`,
                  background: strategyId === s.id ? 'color-mix(in srgb, var(--violet) 8%, transparent)' : 'transparent',
                }}>
                <div style={{ fontSize: 13, fontWeight: 600 }}>{s.name}</div>
                <div style={{ fontSize: 11, color: 'var(--text-faint)' }}>{s.type || ''}</div>
              </button>
            ))}
          </div>
          {assigned.length > 0 && (
            <>
              <div className="t-faint" style={{ fontSize: 11, letterSpacing: 1, margin: '4px 0 8px' }}>CREATE FROM CATALOG</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {assigned.map(a => (
                  <button key={a.strategy_key} className="t-btn t-btn-sm" disabled={busy} onClick={() => createFromCatalog(a)}>
                    + {a.name || a.strategy_key}
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
      )}

      {/* STEP 3: mode & symbols */}
      {step === 2 && (
        <div className="t-panel" style={{ padding: 18 }}>
          <h3 className="t-panel-title" style={{ marginBottom: 4 }}>Step 3 · Trading mode</h3>
          <p className="t-faint" style={{ fontSize: 12, marginBottom: 14 }}>
            Paper first is strongly recommended — validate fills and behaviour without real money.
          </p>
          <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
            {(['PAPER', 'LIVE'] as const).map(m => (
              <button
                key={m}
                onClick={() => { setMode(m); if (m === 'PAPER') setLiveConfirm('') }}
                className="t-btn"
                style={{
                  flex: 1, padding: '14px',
                  border: `1px solid ${mode === m ? 'var(--violet)' : 'var(--border)'}`,
                  background: mode === m ? 'color-mix(in srgb, var(--violet) 8%, transparent)' : 'transparent',
                }}>
                <div style={{ fontSize: 13, fontWeight: 700 }}>{m}</div>
                <div style={{ fontSize: 11, color: 'var(--text-faint)', marginTop: 2 }}>
                  {m === 'PAPER' ? 'Simulated fills · recommended' : 'Real orders · real money'}
                </div>
              </button>
            ))}
          </div>
          {mode === 'LIVE' && (
            <div style={{ marginBottom: 16 }}>
              <label className="t-label">Type LIVE to confirm real-money trading</label>
              <input className="t-input" value={liveConfirm} onChange={e => setLiveConfirm(e.target.value)} placeholder="LIVE" />
            </div>
          )}
          <label className="t-label">Symbols (comma separated)</label>
          <input className="t-input" value={symbols} onChange={e => setSymbols(e.target.value)} />
          <p className="t-faint" style={{ fontSize: 11, marginTop: 10 }}>
            🛡️ Risk guardrails stay active: daily loss limit, max drawdown halt, exposure caps and the emergency kill switch
            (see Risk Control). {tgLinked === false && 'Connect Telegram in Settings to get every fill alert on your phone.'}
          </p>
        </div>
      )}

      {/* STEP 4 / success */}
      {step === 4 ? (
        <div className="t-panel" style={{ padding: 24, textAlign: 'center' }}>
          <div style={{ fontSize: 34, marginBottom: 8 }}>🚀</div>
          <h3 className="t-panel-title">{mode} strategy is running!</h3>
          <p className="t-faint" style={{ fontSize: 12, margin: '8px 0 16px' }}>
            Run ID <code>{runId}</code> · alerts go to Telegram if linked.
          </p>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'center' }}>
            <Link href="/live" className="t-btn t-btn-sm t-btn-primary">Open Live Dashboard</Link>
            <Link href="/positions" className="t-btn t-btn-sm">View Positions</Link>
          </div>
        </div>
      ) : (
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 18 }}>
          <button className="t-btn t-btn-sm" disabled={step === 0 || busy} onClick={() => setStep(s => Math.max(0, s - 1))}>
            ← Back
          </button>
          {step < 3 ? (
            <button className="t-btn t-btn-sm t-btn-primary" disabled={!canNext()} onClick={() => setStep(s => s + 1)}>
              Next →
            </button>
          ) : (
            <button className="t-btn t-btn-sm t-btn-primary" disabled={busy || !canNext()} onClick={deploy}>
              {busy ? 'Starting…' : `🚀 Start ${mode} trading`}
            </button>
          )}
        </div>
      )}

      {/* review line above deploy button */}
      {step === 3 && !runId && (
        <div className="t-panel" style={{ padding: 18, marginTop: 14 }}>
          <h3 className="t-panel-title" style={{ marginBottom: 10 }}>Review</h3>
          <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
            <tbody>
              {[
                ['Broker', broker],
                ['Strategy', selectedStrategy?.name || strategyId],
                ['Mode', mode],
                ['Symbols', symbols],
                ['Risk guards', 'Daily loss limit · drawdown halt · kill switch'],
              ].map(([k, v]) => (
                <tr key={k}>
                  <td style={{ padding: '5px 0', color: 'var(--text-faint)', width: 120 }}>{k}</td>
                  <td style={{ fontWeight: 600 }}>{v}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
