'use client'

import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import { useToast } from '@/lib/use-toast'

export default function RiskPage() {
  const { toast } = useToast()
  const [killSwitch, setKillSwitch] = useState(false)
  const [loading, setLoading] = useState(true)
  const [limits, setLimits] = useState({
    max_daily_loss: 0, max_drawdown: 0, max_open_positions: 10,
  })
  const [usage, setUsage] = useState<{ openPositions: number; filledToday: number } | null>(null)
  const [editing, setEditing] = useState(false)
  const [editValues, setEditValues] = useState(limits)

  const load = async () => {
    try {
      const ks = await api.risk.killSwitchStatus() as { kill_switch_enabled: boolean }
      setKillSwitch(ks.kill_switch_enabled)
      const s = await api.risk.settings() as any
      if (s?.max_daily_loss != null) setLimits(prev => ({ ...prev, max_daily_loss: s.max_daily_loss }))
      if (s?.max_drawdown != null) setLimits(prev => ({ ...prev, max_drawdown: s.max_drawdown }))
      if (s?.max_open_positions != null) setLimits(prev => ({ ...prev, max_open_positions: s.max_open_positions }))
    } catch (e) { console.error('Failed to load risk settings:', e) }
    finally { setLoading(false) }
    // live usage vs guardrails (fail-open display, never blocks the page)
    try {
      const [pos, ords] = await Promise.all([
        api.engine.positions().catch(() => ({ positions: [] })),
        api.engine.orders().catch(() => ({ orders: [] })),
      ])
      const positions = ((pos as { positions?: unknown[] }).positions || [])
      const openNow = positions.filter((p: any) => Number(p.quantity) !== 0).length
      const today = new Date().toISOString().slice(0, 10)
      const orders = ((ords as { orders?: any[] }).orders || [])
      const filledToday = orders.filter(o =>
        o?.status && ['FILLED', 'PARTIALLY_FILLED'].includes(String(o.status).toUpperCase()) &&
        String(o.created_at || o.updated_at || '').slice(0, 10) === today
      ).length
      setUsage({ openPositions: openNow, filledToday })
    } catch { /* keep null */ }
  }

  useEffect(() => { load() }, [])

  const toggleKillSwitch = async () => {
    try {
      if (killSwitch) {
        await api.risk.disableKillSwitch()
        toast('success', 'Kill switch disabled')
      } else {
        await api.risk.enableKillSwitch()
        toast('warning', 'Kill switch enabled — all trading halted')
      }
      setKillSwitch(!killSwitch)
    } catch {
      toast('error', 'Failed to toggle kill switch')
    }
  }

  const handleSaveLimits = async () => {
    try {
      await api.risk.update(editValues)
      setLimits(editValues)
      setEditing(false)
      toast('success', 'Risk limits updated')
    } catch {
      toast('error', 'Failed to update limits')
    }
  }

  if (loading) return <p style={{ color: 'var(--text-faint)', fontSize: 12 }}>Loading risk settings...</p>

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div>
        <h1 style={{ fontFamily: 'var(--font-body)', fontWeight: 700, fontSize: 18, margin: 0, color: 'var(--text)' }}>Risk Control</h1>
        <p style={{ color: 'var(--text-sub)', fontSize: 12, margin: '2px 0 0' }}>
          Manage trading risk and safety controls
        </p>
      </div>

      {/* Kill Switch */}
      <div style={{
        background: killSwitch ? 'color-mix(in srgb, var(--red) 6%, transparent)' : 'var(--panel)',
        border: `1px solid ${killSwitch ? 'color-mix(in srgb, var(--red) 20%, transparent)' : 'var(--border)'}`,
        borderRadius: 'var(--radius-md)', padding: 16,
        transition: 'all 200ms ease',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{
            width: 48, height: 48, borderRadius: 'var(--radius-md)',
            background: killSwitch ? 'color-mix(in srgb, var(--red) 12%, transparent)' : 'var(--bg-tertiary)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 20, flexShrink: 0,
          }}>
            {killSwitch ? '🔴' : '🟢'}
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text)' }}>
              Kill Switch
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-sub)', marginTop: 2 }}>
              {killSwitch
                ? 'All trading is halted. No orders can be placed.'
                : 'Trading is enabled. Kill switch is inactive.'}
            </div>
          </div>
          <button
            onClick={toggleKillSwitch}
            style={{
              padding: '8px 20px', borderRadius: 'var(--radius-sm)',
              border: 'none', cursor: 'pointer',
              background: killSwitch ? 'var(--red)' : 'var(--green)',
              color: 'var(--text-inverse)', fontSize: 12, fontWeight: 700,
              fontFamily: 'var(--font-body)',
              transition: 'all 150ms ease',
            }}
          >
            {killSwitch ? 'Disable' : 'Enable'}
          </button>
        </div>

        {killSwitch && (
          <div style={{
            marginTop: 12, padding: '8px 12px',
            background: 'color-mix(in srgb, var(--red) 8%, transparent)', borderRadius: 'var(--radius-sm)',
            fontSize: 11, color: 'var(--text-red)', fontWeight: 600,
          }}>
            ⚠ Kill switch is ACTIVE — all order placement is blocked
          </div>
        )}
      </div>

      {/* Guardrails — live usage vs limits */}
      <div className="t-panel" style={{ padding: 0 }}>
        <div style={{
          padding: '8px 12px', borderBottom: '1px solid var(--border)',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        }}>
          <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--text)' }}>Guardrails · Live Status</span>
          <span style={{ fontSize: 9, color: 'var(--text-faint)' }}>auto-enforced on every order</span>
        </div>
        <div style={{ padding: 12, display: 'flex', flexDirection: 'column', gap: 12 }}>
          {([
            {
              label: 'Open positions', used: usage?.openPositions ?? null, cap: limits.max_open_positions,
              fmt: (u: number) => `${u} / ${limits.max_open_positions}`,
            },
            {
              label: 'Trades filled today', used: usage?.filledToday ?? null, cap: limits.max_daily_loss ? undefined : undefined,
              fmt: (u: number) => `${u}`,
            },
          ] as const).map(row => {
            const over = row.used != null && row.cap != null && row.used > row.cap
            return (
              <div key={row.label}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                  <span style={{ fontSize: 11 }}>{row.label}</span>
                  <span style={{
                    fontSize: 11, fontFamily: 'var(--font-mono)', fontWeight: 700,
                    color: over ? 'var(--red)' : 'var(--text)',
                  }}>
                    {row.used == null ? '—' : row.fmt(row.used)}
                    {row.cap != null && row.used != null ? ` / cap ${row.cap}` : ''}
                  </span>
                </div>
                {row.cap != null && row.used != null && (
                  <div style={{ height: 4, borderRadius: 2, background: 'var(--bg-tertiary)' }}>
                    <div style={{
                      height: 4, borderRadius: 2, width: `${Math.min(100, (row.used / Math.max(1, row.cap)) * 100)}%`,
                      background: over ? 'var(--red)' : 'var(--green)',
                    }} />
                  </div>
                )}
              </div>
            )
          })}
          <div style={{
            padding: '8px 10px', background: 'color-mix(in srgb, var(--violet) 6%, transparent)',
            borderRadius: 'var(--radius-sm)', fontSize: 11, color: 'var(--text-sub)',
          }}>
            🛡️ Every order passes the risk gate before reaching your broker: kill switch → daily loss → drawdown halt →
            position &amp; exposure caps. Breaches halt trading automatically — plus the one-tap emergency stop above.
          </div>
        </div>
      </div>

      {/* Risk Limits */}
      <div className="t-panel" style={{ padding: 0 }}>
        <div style={{
          padding: '8px 12px', borderBottom: '1px solid var(--border)',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        }}>
          <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--text)' }}>Risk Limits</span>
          <button className="t-btn t-btn-xs" onClick={() => { setEditing(!editing); if (!editing) setEditValues(limits) }}>
            {editing ? 'Cancel' : 'Edit'}
          </button>
        </div>
        <div style={{ padding: 12 }}>
          {editing ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <div>
                <label style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-sub)', display: 'block', marginBottom: 3 }}>Max Daily Loss (₹)</label>
                <input className="t-input" type="number" value={editValues.max_daily_loss} onChange={e => setEditValues(p => ({ ...p, max_daily_loss: Number(e.target.value) }))} />
              </div>
              <div>
                <label style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-sub)', display: 'block', marginBottom: 3 }}>Max Drawdown (%)</label>
                <input className="t-input" type="number" value={editValues.max_drawdown} onChange={e => setEditValues(p => ({ ...p, max_drawdown: Number(e.target.value) }))} step={0.1} min={0} max={100} />
              </div>
              <div>
                <label style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-sub)', display: 'block', marginBottom: 3 }}>Max Open Positions</label>
                <input className="t-input" type="number" value={editValues.max_open_positions} onChange={e => setEditValues(p => ({ ...p, max_open_positions: Number(e.target.value) }))} min={1} />
              </div>
              <button className="t-btn t-btn-primary" onClick={handleSaveLimits}>Save Limits</button>
            </div>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
              <div style={{
                padding: 12, background: 'var(--bg-tertiary)',
                borderRadius: 'var(--radius-sm)',
              }}>
                <div style={{ fontSize: 9, color: 'var(--text-faint)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em' }}>Max Daily Loss</div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 18, fontWeight: 700, color: 'var(--text)', marginTop: 4 }}>
                  {limits.max_daily_loss ? `₹${limits.max_daily_loss.toLocaleString()}` : '∞'}
                </div>
              </div>
              <div style={{
                padding: 12, background: 'var(--bg-tertiary)',
                borderRadius: 'var(--radius-sm)',
              }}>
                <div style={{ fontSize: 9, color: 'var(--text-faint)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em' }}>Max Drawdown</div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 18, fontWeight: 700, color: 'var(--text)', marginTop: 4 }}>
                  {limits.max_drawdown ? `${limits.max_drawdown}%` : '∞'}
                </div>
              </div>
              <div style={{
                padding: 12, background: 'var(--bg-tertiary)',
                borderRadius: 'var(--radius-sm)',
              }}>
                <div style={{ fontSize: 9, color: 'var(--text-faint)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em' }}>Max Positions</div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 18, fontWeight: 700, color: 'var(--text)', marginTop: 4 }}>
                  {limits.max_open_positions}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Info */}
      <div className="t-panel" style={{ padding: 12 }}>
        <div style={{ fontSize: 10, color: 'var(--text-faint)', fontWeight: 700, marginBottom: 6 }}>About Risk Controls</div>
        <div style={{ fontSize: 11, color: 'var(--text-sub)', lineHeight: 1.5 }}>
          <p style={{ margin: '0 0 6px' }}>
            <strong style={{ color: 'var(--text)' }}>Kill Switch</strong> — Immediately halts all trading. No orders can be placed until disabled.
          </p>
          <p style={{ margin: '0 0 6px' }}>
            <strong style={{ color: 'var(--text)' }}>Max Daily Loss</strong> — Automatic trading halt when daily unrealized loss exceeds this threshold.
          </p>
          <p style={{ margin: '0 0 6px' }}>
            <strong style={{ color: 'var(--text)' }}>Max Drawdown</strong> — Maximum peak-to-trough decline before automatic stop.
          </p>
          <p style={{ margin: 0 }}>
            <strong style={{ color: 'var(--text)' }}>Max Open Positions</strong> — Limits the number of concurrent open positions.
          </p>
        </div>
      </div>
    </div>
  )
}
