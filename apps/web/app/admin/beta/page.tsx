'use client'

import { useCallback, useEffect, useState } from 'react'
import { useAuth } from '@/lib/auth-context'
import { useToast } from '@/lib/use-toast'
import { api } from '@/lib/api'
import { EmptyState } from '@/components/empty-state'
import { EmptyNote } from '@/components/ui/empty-state'
import { KpiCard as UIKpiCard } from '@/components/ui/kpi-card'
import { SkeletonPanel } from '@/components/ui/skeleton'

type Overview = {
  dau: number
  wau: number
  mau: number
  total_users: number
  broker_users: number
  traded_users: number
  live_traded_users: number
  activation_rate: number
  retention_rate: number
  avg_session_seconds: number
  crash_free_rate: number
  crash_events_count: number
  total_sessions: number
  total_tracked_events: number
  total_tracked_users: number
  funnel: { step: string; label: string; count: number }[]
  daily_active_users: Record<string, number>
  event_counts: { event: string; count: number; users: number }[]
}

type FunnelRes = { steps: { step: string; users: number; cumulative: number }[] }
type RetentionRes = { cohorts: Record<string, number | string>[] }
type FeaturesRes = { features: { event: string; count: number; users: number }[] }
type SessionsRes = { sessions: { session_id: string; count: number; first: string; last: string; pages: string[] }[] }
type SessionEventsRes = { events: { event: string; properties: Record<string, unknown>; created_at: string }[]; count: number }
type CrashesRes = { crashes: { key: string; count: number; first: string; last: string; sessions: string[]; message: string }[]; total: number }
type FeedbackItem = {
  id: number
  user_email: string
  full_name: string
  category: string
  title: string
  description: string
  status: string
  metadata: Record<string, unknown> | null
  created_at?: string
}
type FeedbackRes = { feedback: FeedbackItem[]; count: number }

const TABS = ['Overview', 'Funnel', 'Retention', 'Features', 'Sessions', 'Crashes', 'Feedback'] as const
type Tab = (typeof TABS)[number]

export default function BetaDashboardPage() {
  const { isAdmin, loading: authLoading } = useAuth()

  if (authLoading) {
    return (
      <div>
        <h1 className="t-page-title">Beta Dashboard</h1>
        <div className="t-panel" style={{ padding: 20 }}>
          <div style={{ height: 12, width: '50%', background: 'rgba(139,92,246,0.08)', borderRadius: 4, marginBottom: 8 }} />
          <div style={{ height: 12, width: '70%', background: 'rgba(139,92,246,0.08)', borderRadius: 4 }} />
        </div>
      </div>
    )
  }

  if (!isAdmin) {
    return (
      <div>
        <h1 className="t-page-title">Beta Dashboard</h1>
        <div style={{ padding: '12px 16px', background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.2)', borderRadius: 8, color: 'var(--red)', fontSize: 13 }}>
          You do not have admin access.
        </div>
      </div>
    )
  }

  return <BetaDashboard />
}

function BetaDashboard() {
  const [tab, setTab] = useState<Tab>('Overview')
  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 className="t-page-title">Beta Dashboard</h1>
        <p className="t-sub" style={{ fontSize: 13 }}>
          Real-user evidence: product analytics, journey, funnel, retention, crashes, and feedback
        </p>
      </div>
      <div style={{ display: 'flex', gap: 0, marginBottom: 20, borderBottom: '1px solid rgba(139,92,246,0.15)', overflowX: 'auto' }}>
        {TABS.map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            style={{
              padding: '8px 14px', fontSize: 12, fontWeight: tab === t ? 600 : 400,
              background: 'none', border: 'none', borderBottom: tab === t ? '2px solid var(--violet)' : '2px solid transparent',
              color: tab === t ? 'var(--violet)' : 'var(--text-faint)', cursor: 'pointer', whiteSpace: 'nowrap',
              fontFamily: 'inherit',
            }}
          >
            {t}
          </button>
        ))}
      </div>
      {tab === 'Overview' && <OverviewSection />}
      {tab === 'Funnel' && <FunnelSection />}
      {tab === 'Retention' && <RetentionSection />}
      {tab === 'Features' && <FeaturesSection />}
      {tab === 'Sessions' && <SessionsSection />}
      {tab === 'Crashes' && <CrashesSection />}
      {tab === 'Feedback' && <FeedbackSection />}
    </div>
  )
}

function useLoad<T>(fn: () => Promise<T>, deps: unknown[]): { data: T | null; loading: boolean; error: string; reload: () => void } {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [nonce, setNonce] = useState(0)
  useEffect(() => {
    let alive = true
    setLoading(true)
    setError('')
    fn()
      .then(d => { if (alive) setData(d) })
      .catch(() => { if (alive) setError('Failed to load. Try again.') })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce])
  const reload = useCallback(() => setNonce(n => n + 1), [])
  return { data, loading, error, reload }
}

const fmtNum = (n: number) => n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n)

function KpiCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return <UIKpiCard label={label} value={value} sub={sub} variant="beta" />
}

function Bar({ pct, color = 'var(--violet)' }: { pct: number; color?: string }) {
  return (
    <div style={{ background: 'rgba(139,92,246,0.1)', borderRadius: 3, height: 8, overflow: 'hidden' }}>
      <div style={{ background: color, height: '100%', borderRadius: 3, width: `${Math.min(100, pct)}%` }} />
    </div>
  )
}

function OverviewSection() {
  const { data } = useLoad<Overview>(() => api.get<Overview>('/admin/analytics/overview'), [])
  if (!data) return <LoadState />
  const funnel = data.funnel
  const maxCount = Math.max(1, ...funnel.map(f => f.count))
  const dauSeries = Object.entries(data.daily_active_users).slice(0, 14).reverse()
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        <KpiCard label="DAU" value={fmtNum(data.dau)} />
        <KpiCard label="WAU" value={fmtNum(data.wau)} />
        <KpiCard label="MAU" value={fmtNum(data.mau)} />
        <KpiCard label="Activation" value={`${data.activation_rate}%`} sub="traded / signed up" />
        <KpiCard label="Retention" value={`${data.retention_rate}%`} sub="WAU / MAU" />
        <KpiCard label="Avg Session" value={data.avg_session_seconds ? `${Math.round(data.avg_session_seconds)}s` : '—'} />
        <KpiCard label="Crash Free" value={`${data.crash_free_rate}%`} sub={`${data.crash_events_count} crash events`} />
        <KpiCard label="Tracked" value={fmtNum(data.total_tracked_events)} sub={`${fmtNum(data.total_tracked_users)} users · ${fmtNum(data.total_sessions)} sessions`} />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 16 }}>
        <div className="t-panel" style={{ padding: 16 }}>
          <h3 style={{ fontFamily: 'Outfit', fontSize: 13, margin: '0 0 12px', color: '#f0f0f5' }}>Activation Funnel</h3>
          {funnel.map(f => (
            <div key={f.step} style={{ marginBottom: 10 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, marginBottom: 4 }}>
                <span>{f.label}</span>
                <span style={{ color: 'var(--text-faint)' }}>{fmtNum(f.count)}</span>
              </div>
              <Bar pct={(f.count / maxCount) * 100} color={f.step === 'live_traded' ? '#22c55e' : undefined} />
            </div>
          ))}
        </div>

        <div className="t-panel" style={{ padding: 16 }}>
          <h3 style={{ fontFamily: 'Outfit', fontSize: 13, margin: '0 0 12px', color: '#f0f0f5' }}>Daily Active Users (14d)</h3>
          {dauSeries.length === 0 ? (
            <EmptyNote>No tracked activity yet — the tracker starts collecting once web traffic flows.</EmptyNote>
          ) : (
            <div style={{ display: 'flex', alignItems: 'flex-end', gap: 4, height: 120 }}>
              {dauSeries.map(([day, n]) => (
                <div key={day} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
                  <div style={{ fontSize: 9, color: 'var(--text-faint)' }}>{n}</div>
                  <div style={{ width: '100%', background: 'rgba(139,92,246,0.12)', borderRadius: '3px 3px 0 0' }}>
                    <div style={{ background: 'var(--violet)', width: '100%', height: `${Math.max(3, (n / Math.max(1, ...dauSeries.map(([, v]) => v))) * 90)}px`, borderRadius: '3px 3px 0 0' }} />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="t-panel" style={{ padding: 16 }}>
          <h3 style={{ fontFamily: 'Outfit', fontSize: 13, margin: '0 0 12px', color: '#f0f0f5' }}>Most Tracked Events (15)</h3>
          {data.event_counts.length === 0 ? (
            <EmptyNote>No events yet.</EmptyNote>
          ) : (
            data.event_counts.map(f => (
              <div key={f.event} style={{ marginBottom: 8 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, marginBottom: 3 }}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10 }}>{f.event}</span>
                  <span style={{ color: 'var(--text-faint)' }}>{fmtNum(f.count)} · {f.users}u</span>
                </div>
                <Bar pct={(f.count / Math.max(1, data.event_counts[0].count)) * 100} color="#22d3ee" />
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}

function FunnelSection() {
  const [days, setDays] = useState(30)
  const [steps, setSteps] = useState('signup,broker.connected,strategy.created,backtest.run,order.placed')
  const [query, setQuery] = useState('signup,broker.connected,strategy.created,backtest.run,order.placed')
  const { data } = useLoad<FunnelRes>(() => api.get<FunnelRes>(`/admin/analytics/funnel?days=${days}&steps=${encodeURIComponent(query)}`), [days, query])
  return (
    <div>
      <div style={{ display: 'flex', gap: 8, marginBottom: 16, alignItems: 'flex-end', flexWrap: 'wrap' }}>
        <div>
          <label className="t-label" style={{ fontSize: 10, marginBottom: 4, display: 'block' }}>Days</label>
          <input className="t-input" type="number" min={1} max={90} value={days} onChange={e => setDays(Math.max(1, Math.min(90, parseInt(e.target.value) || 30)))} style={{ width: 80, fontSize: 12 }} />
        </div>
        <div style={{ flex: 1, minWidth: 280 }}>
          <label className="t-label" style={{ fontSize: 10, marginBottom: 4, display: 'block' }}>Steps (comma-separated)</label>
          <input className="t-input" value={steps} onChange={e => setSteps(e.target.value)} style={{ width: '100%', fontSize: 12 }} />
        </div>
        <button className="t-btn t-btn-primary t-btn-sm" onClick={() => setQuery(steps)} style={{ fontSize: 11 }}>Apply</button>
      </div>
      {!data ? <LoadState /> : (
        <div className="t-panel" style={{ padding: 16 }}>
          {data.steps.length === 0 ? (
            <EmptyNote>No events for these steps in the window.</EmptyNote>
          ) : (
            data.steps.map((s, i) => {
              const prev = i === 0 ? data.steps[0].users : data.steps[i - 1].users
              const drop = i === 0 ? 0 : prev === 0 ? 0 : Math.round((1 - s.users / prev) * 100)
              return (
                <div key={s.step} style={{ marginBottom: 12 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, marginBottom: 4 }}>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10 }}>{s.step}</span>
                    <span>
                      <span style={{ fontWeight: 700 }}>{fmtNum(s.users)}</span>
                      <span style={{ color: 'var(--text-faint)' }}> users · cumulative {fmtNum(s.cumulative)}</span>
                      {drop > 0 && <span style={{ color: 'var(--red)', marginLeft: 6 }}>−{drop}%</span>}
                    </span>
                  </div>
                  <Bar pct={(s.users / Math.max(1, data.steps[0].users)) * 100} />
                </div>
              )
            })
          )}
        </div>
      )}
    </div>
  )
}

function RetentionSection() {
  const [weeks, setWeeks] = useState(8)
  const { data } = useLoad<RetentionRes>(() => api.get<RetentionRes>(`/admin/analytics/retention?weeks=${weeks}`), [weeks])
  return (
    <div>
      <div style={{ display: 'flex', gap: 8, marginBottom: 16, alignItems: 'flex-end' }}>
        <div>
          <label className="t-label" style={{ fontSize: 10, marginBottom: 4, display: 'block' }}>Weeks</label>
          <input className="t-input" type="number" min={1} max={26} value={weeks} onChange={e => setWeeks(Math.max(1, Math.min(26, parseInt(e.target.value) || 8)))} style={{ width: 80, fontSize: 12 }} />
        </div>
      </div>
      {!data ? <LoadState /> : (
        <div className="t-panel" style={{ padding: 16, overflowX: 'auto' }}>
          {data.cohorts.length === 0 ? (
            <EmptyNote>No cohorts yet — needs at least one tracked session.</EmptyNote>
          ) : (
            <table className="t-table" style={{ fontSize: 10, borderCollapse: 'collapse' }}>
              <thead>
                <tr>
                  <th style={{ padding: '6px 10px', textAlign: 'left', color: 'var(--text-faint)' }}>COHORT</th>
                  <th style={{ padding: '6px 10px', textAlign: 'right', color: 'var(--text-faint)' }}>USERS</th>
                  {data.cohorts[0] && Object.keys(data.cohorts[0]).filter(k => k.startsWith('w')).map(k => (
                    <th key={k} style={{ padding: '6px 10px', textAlign: 'right', color: 'var(--text-faint)' }}>{k.toUpperCase()}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.cohorts.map(c => (
                  <tr key={String(c.cohort)} style={{ borderBottom: '1px solid rgba(139,92,246,0.06)' }}>
                    <td style={{ padding: '6px 10px', fontFamily: 'var(--font-mono)', fontSize: 10 }}>{String(c.cohort)}</td>
                    <td style={{ padding: '6px 10px', textAlign: 'right', fontWeight: 600 }}>{String(c.users)}</td>
                    {Object.entries(c).filter(([k]) => k.startsWith('w')).map(([k, v]) => {
                      const pct = Number(v)
                      return (
                        <td key={k} style={{ padding: '6px 10px', textAlign: 'right' }}>
                          <span style={{
                            color: pct >= 50 ? '#22c55e' : pct >= 20 ? '#f59e0b' : 'var(--text-faint)',
                            background: pct >= 50 ? 'rgba(34,197,94,0.12)' : pct >= 20 ? 'rgba(245,158,11,0.12)' : 'transparent',
                            borderRadius: 4, padding: '2px 6px',
                          }}>{pct}%</span>
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  )
}

function FeaturesSection() {
  const [days, setDays] = useState(30)
  const { data } = useLoad<FeaturesRes>(() => api.get<FeaturesRes>(`/admin/analytics/features?days=${days}`), [days])
  if (!data) return <LoadState />
  if (data.features.length === 0) {
    return <div className="t-panel" style={{ padding: 16 }}><EmptyNote>No events tracked yet.</EmptyNote></div>
  }
  const max = data.features[0].count
  return (
    <div>
      <div style={{ display: 'flex', gap: 8, marginBottom: 16, alignItems: 'flex-end' }}>
        <div>
          <label className="t-label" style={{ fontSize: 10, marginBottom: 4, display: 'block' }}>Days</label>
          <input className="t-input" type="number" min={1} max={90} value={days} onChange={e => setDays(Math.max(1, Math.min(90, parseInt(e.target.value) || 30)))} style={{ width: 80, fontSize: 12 }} />
        </div>
      </div>
      <div className="t-panel" style={{ padding: 16 }}>
        {data.features.map(f => (
          <div key={f.event} style={{ marginBottom: 10 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, marginBottom: 3 }}>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10 }}>{f.event}</span>
              <span style={{ color: 'var(--text-faint)' }}>{fmtNum(f.count)} events · {fmtNum(f.users)} users</span>
            </div>
            <Bar pct={(f.count / max) * 100} color="#22d3ee" />
          </div>
        ))}
      </div>
    </div>
  )
}

function SessionsSection() {
  const [selected, setSelected] = useState<string>('')
  const { data } = useLoad<SessionsRes>(() => api.get<SessionsRes>('/admin/analytics/sessions?limit=50&days=14'), [])
  const { data: replay, loading: replayLoading } = useLoad<SessionEventsRes>(
    () => selected ? api.get<SessionEventsRes>(`/admin/analytics/sessions/${encodeURIComponent(selected)}/events`) : Promise.resolve({ events: [], count: 0 }),
    [selected],
  )
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(380px, 1fr))', gap: 16, alignItems: 'start' }}>
      <div className="t-panel" style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{ padding: '10px 14px', borderBottom: '1px solid var(--border)', fontSize: 12, fontWeight: 600 }}>Sessions (14d)</div>
        {!data || data.sessions.length === 0 ? (
          <div style={{ padding: 20 }}><EmptyNote>No tracked sessions yet.</EmptyNote></div>
        ) : (
          <div style={{ maxHeight: 560, overflow: 'auto' }}>
            {data.sessions.map(s => (
              <button
                key={s.session_id}
                onClick={() => setSelected(s.session_id)}
                style={{
                  display: 'block', width: '100%', textAlign: 'left', background: selected === s.session_id ? 'rgba(139,92,246,0.08)' : 'none',
                  border: 'none', borderBottom: '1px solid rgba(139,92,246,0.06)', padding: '10px 14px', cursor: 'pointer', fontFamily: 'inherit',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, fontFamily: 'var(--font-mono)', color: 'var(--text-faint)' }}>
                  <span>{s.session_id}</span>
                  <span>{s.count} events</span>
                </div>
                <div style={{ fontSize: 10, color: 'var(--text-faint)', marginTop: 2 }}>{s.first?.slice(0, 19)} → {s.last?.slice(0, 19)}</div>
                <div style={{ fontSize: 10, marginTop: 4, color: '#22d3ee', fontFamily: 'var(--font-mono)' }}>
                  {(s.pages || []).slice(0, 5).join(' · ') || '—'}
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
      <div className="t-panel" style={{ padding: 16 }}>
        <h3 style={{ fontFamily: 'Outfit', fontSize: 13, margin: '0 0 12px', color: '#f0f0f5' }}>Session Replay {selected ? '' : '— select a session'}</h3>
        {replayLoading && <LoadState />}
        {!replayLoading && replay && replay.count === 0 && selected && (
          <EmptyNote>No events for this session.</EmptyNote>
        )}
        {!replayLoading && replay && replay.count > 0 && (
          <div style={{ maxHeight: 560, overflow: 'auto', display: 'flex', flexDirection: 'column', gap: 6 }}>
            {replay.events.map((e, i) => (
              <div key={i} style={{ fontSize: 10, borderLeft: '2px solid rgba(139,92,246,0.3)', paddingLeft: 10, fontFamily: 'var(--font-mono)' }}>
                <div style={{ color: 'var(--text-faint)' }}>{String(e.created_at).slice(11, 19)}</div>
                <div style={{ color: '#f0f0f5', fontWeight: 600, marginTop: 2 }}>{e.event}</div>
                {Object.entries(e.properties || {}).slice(0, 6).map(([k, v]) => (
                  <div key={k} style={{ color: 'var(--text-faint)', marginTop: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 520 }}>
                    <span style={{ color: '#22d3ee' }}>{k}:</span> {JSON.stringify(v)}
                  </div>
                ))}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function CrashesSection() {
  const [days, setDays] = useState(30)
  const { data } = useLoad<CrashesRes>(() => api.get<CrashesRes>(`/admin/analytics/crashes?days=${days}`), [days])
  return (
    <div>
      <div style={{ display: 'flex', gap: 8, marginBottom: 16, alignItems: 'flex-end' }}>
        <div>
          <label className="t-label" style={{ fontSize: 10, marginBottom: 4, display: 'block' }}>Days</label>
          <input className="t-input" type="number" min={1} max={90} value={days} onChange={e => setDays(Math.max(1, Math.min(90, parseInt(e.target.value) || 30)))} style={{ width: 80, fontSize: 12 }} />
        </div>
      </div>
      {!data ? <LoadState /> : data.crashes.length === 0 ? (
        <div className="t-panel" style={{ padding: 16 }}><EmptyNote>No crash events tracked. Total crash events: {data.total}</EmptyNote></div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {data.crashes.map(c => (
            <div key={c.key} className="t-panel" style={{ padding: 14 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 600 }}>{c.key.slice(0, 60)}</span>
                <span style={{ fontSize: 11, color: 'var(--red)', fontWeight: 700 }}>{c.count}×</span>
              </div>
              {c.message && <div style={{ fontSize: 11, color: 'var(--text-faint)', marginBottom: 6 }}>{c.message}</div>}
              <div style={{ fontSize: 10, color: 'var(--text-faint)', fontFamily: 'var(--font-mono)' }}>
                {c.first?.slice(0, 19)} → {c.last?.slice(0, 19)} · {c.sessions.length} affected session(s)
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function FeedbackSection() {
  const { toast } = useToast()
  const [filter, setFilter] = useState('')
  const { data, loading, error, reload } = useLoad<FeedbackRes>(() => api.get<FeedbackRes>(`/admin/feedback${filter ? `?status=${filter}` : ''}`), [filter])
  const [updating, setUpdating] = useState<number | null>(null)

  const update = async (id: number, status: string) => {
    setUpdating(id)
    try {
      await api.patch(`/admin/feedback/${id}`, { status })
      toast('success', `Marked ${status}`)
      reload()
    } catch {
      toast('error', 'Failed to update')
    } finally {
      setUpdating(null)
    }
  }

  const categories = ['', 'bug', 'feature', 'nps', 'report']
  return (
    <div>
      <div style={{ display: 'flex', gap: 4, marginBottom: 16, flexWrap: 'wrap' }}>
        {['', 'new', 'triaged', 'resolved', 'wontfix'].map(s => (
          <button key={s} onClick={() => setFilter(s)} style={{
            padding: '5px 12px', fontSize: 11, borderRadius: 6, cursor: 'pointer', fontFamily: 'inherit',
            background: filter === s ? 'var(--violet)' : 'rgba(139,92,246,0.08)',
            color: filter === s ? '#fff' : 'var(--text-faint)', border: 'none',
          }}>{s === '' ? 'All' : s}</button>
        ))}
      </div>
      {loading && <LoadState />}
      {error && <div style={{ padding: 16, fontSize: 12, color: 'var(--red)' }}>{error}</div>}
      {!loading && !error && (!data || data.count === 0) && (
        <EmptyState icon="!" title="No feedback yet" description="Feedback submitted from the Feedback button will appear here." />
      )}
      {!loading && !error && data && data.count > 0 && (
        <div className="t-panel" style={{ padding: 0, overflow: 'hidden' }}>
          <table className="t-table" style={{ fontSize: 11, width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid rgba(139,92,246,0.12)' }}>
                <th style={{ padding: '8px 12px', textAlign: 'left', color: 'var(--text-faint)', fontSize: 9 }}>CATEGORY</th>
                <th style={{ padding: '8px 12px', textAlign: 'left', color: 'var(--text-faint)', fontSize: 9 }}>TITLE</th>
                <th style={{ padding: '8px 12px', textAlign: 'left', color: 'var(--text-faint)', fontSize: 9 }}>FROM</th>
                <th style={{ padding: '8px 12px', textAlign: 'center', color: 'var(--text-faint)', fontSize: 9 }}>STATUS</th>
                <th style={{ padding: '8px 12px', textAlign: 'right', color: 'var(--text-faint)', fontSize: 9 }}>ACTION</th>
              </tr>
            </thead>
            <tbody>
              {data.feedback.map(f => (
                <tr key={f.id} style={{ borderBottom: '1px solid rgba(139,92,246,0.06)' }}>
                  <td style={{ padding: '8px 12px' }}>
                    <span style={{ fontSize: 9, fontWeight: 600, textTransform: 'uppercase', color: '#22d3ee' }}>{f.category}</span>
                  </td>
                  <td style={{ padding: '8px 12px', maxWidth: 340 }}>
                    <div style={{ fontWeight: 600, color: '#f0f0f5' }}>{f.title || '—'}</div>
                    {f.description && <div style={{ fontSize: 10, color: 'var(--text-faint)', marginTop: 2, maxHeight: 32, overflow: 'hidden' }}>{f.description}</div>}
                  </td>
                  <td style={{ padding: '8px 12px', fontSize: 10, color: 'var(--text-faint)' }}>{f.full_name || f.user_email || 'anonymous'}</td>
                  <td style={{ padding: '8px 12px', textAlign: 'center' }}>
                    <span style={{
                      display: 'inline-block', padding: '2px 8px', borderRadius: 4, fontSize: 9, fontWeight: 600,
                      background: f.status === 'resolved' ? 'rgba(34,197,94,0.15)' : f.status === 'triaged' ? 'rgba(245,158,11,0.15)' : f.status === 'wontfix' ? 'rgba(239,68,68,0.15)' : 'rgba(139,92,246,0.15)',
                      color: f.status === 'resolved' ? '#22c55e' : f.status === 'triaged' ? '#f59e0b' : f.status === 'wontfix' ? 'var(--red)' : 'var(--violet)',
                    }}>{f.status}</span>
                  </td>
                  <td style={{ padding: '8px 12px', textAlign: 'right' }}>
                    <select
                      className="t-input"
                      value={f.status}
                      disabled={updating === f.id}
                      onChange={e => update(f.id, e.target.value)}
                      style={{ fontSize: 10, padding: '3px 6px', width: 100 }}
                    >
                      {categories.slice(1).map(c => <option key={c} value={c}>{c}</option>)}
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function LoadState() {
  return <SkeletonPanel />
}
