'use client'

import { useCallback, useState } from 'react'
import { api } from '@/lib/api'
import { useLiveData } from './use-live-data'
import { WidgetFrame } from './widget-frame'
import { Dialog } from '@/components/ui/dialog'
import { Dot } from '@/components/ui/badge'
import type { RuntimeHealth } from './types'

/**
 * Trading Controls — the operational kill-switch panel. Emergency Stop (per
 * user, fires the system kill switch + halts running strategies) and Pause All
 * live HERE, never in the app header. Runtime diagnostics sit below in a
 * collapsible block that admins see expanded by default.
 */
export function TradingControls({ offline, isAdmin, marketClosed }: {
  offline: boolean
  isAdmin: boolean
  marketClosed: boolean
}) {
  const [emergency, setEmergency] = useState(false)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [pausing, setPausing] = useState(false)
  const [busy, setBusy] = useState<'emergency' | 'release' | null>(null)
  const [showDiagnostics, setShowDiagnostics] = useState(isAdmin)
  const [pausedMessage, setPausedMessage] = useState('')

  const { data: health, loading, error } = useLiveData<RuntimeHealth>(
    useCallback(async () => (await api.runtime.health()) as RuntimeHealth, []),
    { intervalMs: 10_000, enabled: !offline },
  )

  const doEmergency = async () => {
    setConfirmOpen(false)
    setBusy('emergency')
    try {
      await api.runtime.emergencyStop()
      setEmergency(true)
    } finally {
      setBusy(null)
    }
  }

  const doRelease = async () => {
    setBusy('release')
    try {
      await api.runtime.release()
      setEmergency(false)
    } finally {
      setBusy(null)
    }
  }

  const pauseAll = async () => {
    setPausing(true)
    setPausedMessage('')
    try {
      const res = await api.runtime.pauseAll() as { status?: string; halted?: string[] }
      setPausedMessage(res.status === 'paused' ? `Paused ${res.halted?.length ?? 0} running strateg${(res.halted?.length ?? 0) === 1 ? 'y' : 'ies'}` : 'Nothing to pause')
    } finally {
      setPausing(false)
    }
  }

  const brokerStates = health?.broker_states || {}

  return (
    <WidgetFrame
      title="Trading Controls"
      offline={offline}
      marketClosed={marketClosed}
      loading={loading}
      error={error}
      empty={false}
      subtitle={health ? `${health.runtime_state}` : undefined}
    >
      {emergency && (
        <div style={{ background: 'var(--danger-bg, color-mix(in srgb, var(--red) 12%, transparent))', border: '1px solid var(--red)', borderRadius: 6, padding: 10, marginBottom: 8 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Dot variant="red" pulse />
            <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-red)', flex: 1 }}>Emergency stop engaged</span>
            <button type="button" className="t-btn t-btn-xs t-btn-ghost" onClick={doRelease} disabled={busy === 'release'} style={{ fontSize: 10 }}>
              {busy === 'release' ? '…' : 'Release'}
            </button>
          </div>
        </div>
      )}

      <div style={{ display: 'grid', gap: 8 }}>
        <button
          type="button"
          className="t-btn t-btn-danger"
          style={{ fontWeight: 700 }}
          onClick={() => setConfirmOpen(true)}
          disabled={busy === 'emergency'}
        >
          {busy === 'emergency' ? 'Stopping…' : 'Emergency Stop'}
        </button>
        <button type="button" className="t-btn t-btn-sm t-btn-ghost" onClick={pauseAll} disabled={pausing}>
          {pausing ? 'Pausing…' : 'Pause All Strategies'}
        </button>
        {pausedMessage && <p className="t-faint" style={{ margin: '4px 2px 0', fontSize: 11 }}>{pausedMessage}</p>}
      </div>

      <div style={{ marginTop: 10 }}>
        <button
          type="button"
          className="t-btn t-btn-xs t-btn-ghost"
          onClick={() => setShowDiagnostics(o => !o)}
          style={{ fontSize: 10, opacity: 0.85 }}
        >
          {showDiagnostics ? '▾' : '▸'} Runtime diagnostics {health ? `(${health.strategies_total})` : ''}
        </button>

        {showDiagnostics && health && (
          <div style={{ marginTop: 8, display: 'grid', gap: 6, fontSize: 11 }}>
            <Row label="Runtime" value={health.runtime_state || health.status} />
            <Row label="Strategies" value={`${health.strategies_running} running / ${health.strategies_total} total`} />
            {Object.keys(health.strategies_by_state || {}).length > 0 && (
              <Row label="By state" value={Object.entries(health.strategies_by_state).map(([s, n]) => `${s} ${n}`).join(', ')} />
            )}
            <Row label="Scheduler" value={health.scheduler_active ? 'active' : 'idle'} />
            {Object.keys(brokerStates).length > 0 && (
              <div>
                <div className="t-faint" style={{ marginBottom: 4 }}>Brokers</div>
                {Object.entries(brokerStates).map(([broker, state]) => (
                  <div key={broker} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '2px 0' }}>
                    <Dot variant={state === 'connected' ? 'green' : state === 'disconnected' ? 'red' : 'amber'} pulse={state === 'connected'} />
                    <span style={{ textTransform: 'capitalize' }}>{broker}</span>
                    <span className="t-faint" style={{ marginLeft: 'auto' }}>{state}</span>
                  </div>
                ))}
              </div>
            )}
            {health.metrics && typeof health.metrics === 'object' && (
              <div style={{ color: 'var(--text-faint)', fontSize: 10 }}>
                errors: {JSON.stringify((health.metrics as Record<string, unknown>).errors ?? 'n/a')}
              </div>
            )}
          </div>
        )}
      </div>

      <Dialog onClose={() => setConfirmOpen(false)} open={confirmOpen} maxWidth={380} title={<h3 style={{ margin: 0, fontSize: 14 }}>Trigger emergency stop?</h3>}>
        <p style={{ fontSize: 12, color: 'var(--text-sub)' }}>
          Halts all running strategies and arms the system kill switch. Trades will be blocked until you release it.
        </p>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 12 }}>
          <button type="button" className="t-btn t-btn-ghost" onClick={() => setConfirmOpen(false)}>Cancel</button>
          <button type="button" className="t-btn t-btn-danger" onClick={doEmergency}>Emergency Stop</button>
        </div>
      </Dialog>
    </WidgetFrame>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
      <span className="t-faint">{label}</span>
      <span style={{ fontWeight: 600, textAlign: 'right' }}>{value}</span>
    </div>
  )
}