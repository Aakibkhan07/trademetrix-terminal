'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import { useApi } from '@/lib/use-api'
import { useAuth } from '@/lib/auth-context'
import { AppVersion } from '@/components/app-version'

type MetricCardProps = {
  label: string
  value: string | number
  sub?: string
  color?: string
  dot?: string
}

function MetricCard({ label, value, sub, color, dot }: MetricCardProps) {
  return (
    <div className="t-panel" style={{ padding: '12px 14px', borderLeft: color ? `3px solid ${color}` : '3px solid var(--violet)' }}>
      <div style={{ fontSize: 9, fontWeight: 600, letterSpacing: '0.04em', color: 'var(--text-faint)', marginBottom: 4 }}>{label}</div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        {dot && <span style={{ width: 8, height: 8, borderRadius: '50%', background: dot, display: 'inline-block' }} />}
        <span style={{ fontSize: 22, fontWeight: 700, fontFamily: 'var(--font-mono)' }}>{value}</span>
      </div>
      {sub && <div style={{ fontSize: 9, color: 'var(--text-faint)', marginTop: 2 }}>{sub}</div>}
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 20 }}>
      <h2 style={{ fontFamily: 'Outfit', fontSize: 13, fontWeight: 600, margin: '0 0 10px', color: 'var(--text)' }}>{title}</h2>
      {children}
    </div>
  )
}

function Grid({ cols, children }: { cols?: number; children: React.ReactNode }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: `repeat(${cols || 4}, 1fr)`, gap: 8 }}>
      {children}
    </div>
  )
}

function FunnelBar({ label, count, total, pct }: { label: string; count: number; total: number; pct: number }) {
  const width = total > 0 ? (count / total) * 100 : 0
  return (
    <div style={{ marginBottom: 6 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, marginBottom: 2 }}>
        <span style={{ color: 'var(--text)' }}>{label}</span>
        <span style={{ color: 'var(--text-faint)', fontFamily: 'var(--font-mono)' }}>{count} ({pct}%)</span>
      </div>
      <div style={{ height: 6, background: 'var(--border)', borderRadius: 3, overflow: 'hidden' }}>
        <div style={{ width: `${Math.min(width, 100)}%`, height: '100%', background: 'var(--violet)', borderRadius: 3, transition: 'width 0.5s' }} />
      </div>
    </div>
  )
}

export default function FounderDashboard() {
  const { isAdmin, loading: authLoading } = useAuth()
  const [refreshKey, setRefreshKey] = useState(0)
  const [healthMetrics, setHealthMetrics] = useState<Record<string, unknown> | null>(null)
  const [prometheusHealth, setPrometheusHealth] = useState<string>('—')
  const [grafanaHealth, setGrafanaHealth] = useState<string>('—')
  const [latencyMs, setLatencyMs] = useState<number | null>(null)
  const [now, setNow] = useState(new Date().toLocaleString())
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const { data: statsData } = useApi<any>(`/admin/stats?_=${refreshKey}`)
  const { data: analyticsData } = useApi<any>(`/admin/analytics/overview?_=${refreshKey}`)
  const { data: brokersData } = useApi<{ brokers: any[] }>(`/admin/brokers?_=${refreshKey}`)
  const { data: activeBrokersData } = useApi<{ active_broker_count: number; oauthed_count: number }>(`/admin/active-brokers?_=${refreshKey}`)
  const { data: ordersData } = useApi<{ orders: any[]; count: number }>(`/admin/orders?limit=5000&_=${refreshKey}`)
  const { data: paperData } = useApi<{ orders: any[]; count: number }>(`/admin/orders?is_paper=true&limit=5000&_=${refreshKey}`)
  const { data: liveOrdersData } = useApi<{ orders: any[]; count: number }>(`/admin/orders?is_paper=false&limit=5000&_=${refreshKey}`)
  const { data: auditData } = useApi<{ entries: any[]; count: number }>(`/admin/audit-log?limit=500&_=${refreshKey}`)
  const { data: runsData } = useApi<{ runs: any[] }>(`/engine/runs?_=${refreshKey}`)

  const fetchExternalHealth = useCallback(async () => {
    try {
      const start = performance.now()
      const res = await fetch('/api/v1/health/live')
      setLatencyMs(Math.round(performance.now() - start))
      if (res.ok) {
        try {
          const metricsRes = await fetch('/api/v1/health/metrics')
          if (metricsRes.ok) setHealthMetrics(await metricsRes.json())
        } catch {}
      }
    } catch {}

    try {
      const res = await fetch('http://localhost:9090/-/healthy', { signal: AbortSignal.timeout(3000) })
      setPrometheusHealth(res.ok ? 'OK' : 'error')
    } catch {
      setPrometheusHealth('unreachable')
    }

    try {
      const res = await fetch('http://localhost:3000/api/health', { signal: AbortSignal.timeout(3000) })
      setGrafanaHealth(res.ok ? 'OK' : 'error')
    } catch {
      setGrafanaHealth('unreachable')
    }
  }, [])

  useEffect(() => {
    fetchExternalHealth()
    intervalRef.current = setInterval(() => {
      setRefreshKey(k => k + 1)
      setNow(new Date().toLocaleString())
      fetchExternalHealth()
    }, 5000)
    return () => { if (intervalRef.current) clearInterval(intervalRef.current) }
  }, [fetchExternalHealth])

  if (authLoading) {
    return <div style={{ padding: 20 }}><div className="t-panel" style={{ padding: 20, height: 400 }} /></div>
  }
  if (!isAdmin) {
    return (
      <div style={{ padding: '40px 20px', textAlign: 'center' }}>
        <h1 className="t-page-title">Founder Dashboard</h1>
        <div style={{ padding: '12px 16px', background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.2)', borderRadius: 8, color: '#ef4444', fontSize: 13, display: 'inline-block' }}>
          Admin access required
        </div>
      </div>
    )
  }

  const a = analyticsData || {}
  const stats = statsData
  const brokers = brokersData?.brokers || []
  const orders = ordersData?.orders || []
  const paperOrders = paperData?.orders || []
  const liveOrders = liveOrdersData?.orders || []
  const auditEntries = auditData?.entries || []
  const runs = runsData?.runs || []

  const today = new Date().toISOString().slice(0, 10)
  const ordersToday = orders.filter((o: any) => o.created_at?.startsWith(today)).length
  const runningRuns = runs.filter((r: any) => r.status === 'running' || r.status === 'active')
  const backtestRuns = runs.filter((r: any) => r.mode === 'backtest' || r.type === 'backtest' || r.status === 'backtest')
  const brokerTypes = brokers.reduce((acc: Record<string, number>, b: any) => {
    acc[b.broker] = (acc[b.broker] || 0) + 1
    return acc
  }, {})
  const activeBrokers = activeBrokersData?.active_broker_count ?? 0
  const oauthedBrokers = activeBrokersData?.oauthed_count ?? 0

  const riskRejections = auditEntries.filter((e: any) => e.action?.toLowerCase().includes('risk') || e.action?.toLowerCase().includes('reject')).length
  const errorEntries = auditEntries.filter((e: any) => e.action?.toLowerCase().includes('error') || e.action?.toLowerCase().includes('fail'))
  const errorRate = auditEntries.length > 0 ? ((errorEntries.length / auditEntries.length) * 100).toFixed(1) : '0.0'

  const metrics = healthMetrics as Record<string, any> | null
  const cpu = metrics?.system_cpu_percent ?? metrics?.cpu_percent ?? null
  const memUsed = metrics?.system_memory_used ?? null
  const memTotal = metrics?.system_memory_total ?? null
  const memPct = metrics?.system_memory_percent ?? (memUsed && memTotal ? ((memUsed / memTotal) * 100).toFixed(1) : null)
  const wsConnections = metrics?.websocket_connections ?? null
  const redisActive = metrics?.redis_active ?? null
  const redisUsage = metrics?.redis_used_memory_human ?? null
  const apiRpm = metrics?.requests_per_minute ?? null

  const dau = a.dau ?? '—'
  const wau = a.wau ?? '—'
  const mau = a.mau ?? '—'
  const activationRate = a.activation_rate ?? '—'
  const retentionRate = a.retention_rate ?? '—'
  const crashFreeRate = a.crash_free_rate ?? '—'
  const avgSessionSec = a.avg_session_seconds ?? '—'
  const funnel = a.funnel || []
  const totalFunnelUsers = funnel[0]?.count || 0
  const crashEventCount = a.crash_events_count ?? 0
  const totalSessions = a.total_sessions ?? 0

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 20 }}>
        <div>
          <h1 className="t-page-title" style={{ margin: 0, fontSize: 18 }}>Founder Dashboard</h1>
          <p className="t-sub" style={{ fontSize: 11, margin: '2px 0 0' }}>
            Real-time platform overview · refreshed 5s ago · {now} · <AppVersion />
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 9, color: 'var(--text-faint)' }}>API:</span>
          <span style={{
            width: 8, height: 8, borderRadius: '50%', display: 'inline-block',
            background: latencyMs !== null ? '#22c55e' : '#ef4444',
          }} />
          <span style={{ fontSize: 10, fontFamily: 'var(--font-mono)', color: 'var(--text-sub)' }}>
            {latencyMs !== null ? `${latencyMs}ms` : '—'}
          </span>
        </div>
      </div>

      <Section title="Active Users">
        <Grid>
          <MetricCard label="DAU (Daily)" value={dau} sub="unique users today" color="var(--cyan)" />
          <MetricCard label="WAU (Weekly)" value={wau} sub="unique users last 7d" color="var(--green)" />
          <MetricCard label="MAU (Monthly)" value={mau} sub="unique users last 30d" color="var(--amber)" />
          <MetricCard label="Total Users" value={a.total_users ?? stats?.total_users ?? '—'} color="var(--violet)" />
        </Grid>
      </Section>

      <Section title="Activation & Retention">
        <Grid cols={4}>
          <MetricCard label="Activation Rate" value={typeof activationRate === 'number' ? `${activationRate}%` : activationRate} sub="users who placed ≥1 trade" color="var(--cyan)" />
          <MetricCard label="Retention (W/M)" value={typeof retentionRate === 'number' ? `${retentionRate}%` : retentionRate} sub="WAU / MAU" color="var(--green)" />
          <MetricCard label="Crash-Free Sessions" value={typeof crashFreeRate === 'number' ? `${crashFreeRate}%` : crashFreeRate} sub={`${crashEventCount} crashes in ${totalSessions} sessions`} color={typeof crashFreeRate === 'number' && crashFreeRate > 99 ? 'var(--green)' : 'var(--amber)'} />
          <MetricCard label="Avg Session" value={typeof avgSessionSec === 'number' ? `${Math.round(avgSessionSec)}s` : avgSessionSec} color="var(--violet)" />
        </Grid>
      </Section>

      <Section title="Funnel">
        <div className="t-panel" style={{ padding: 16 }}>
          {funnel.length > 0 ? funnel.map((step: any, i: number) => (
            <FunnelBar
              key={step.step}
              label={`${i + 1}. ${step.label}`}
              count={step.count}
              total={totalFunnelUsers}
              pct={totalFunnelUsers > 0 ? Math.round((step.count / totalFunnelUsers) * 100) : 0}
            />
          )) : (
            <div style={{ fontSize: 11, color: 'var(--text-faint)', textAlign: 'center', padding: 12 }}>
              Funnel data available once users start flowing through the platform.
            </div>
          )}
        </div>
      </Section>

      <Section title="Users">
        <Grid>
          <MetricCard label="Online Now" value={a.tracked_users ?? '—'} sub="tracked in analytics" color="var(--amber)" dot="var(--green)" />
          <MetricCard label="Broker Connected" value={a.broker_users ?? '—'} color="var(--cyan)" />
          <MetricCard label="Assigned Strategy" value={a.assigned_users ?? '—'} color="var(--green)" />
          <MetricCard label="Traded" value={a.traded_users ?? '—'} sub={`${a.live_traded_users ?? 0} live`} color="var(--violet)" />
        </Grid>
      </Section>

      <Section title="Orders & Trades">
        <Grid>
          <MetricCard label="Orders Today" value={ordersToday} color="var(--cyan)" />
          <MetricCard label="Paper Trades" value={paperOrders.length} sub="total paper" color="var(--green)" />
          <MetricCard label="Live Trades" value={liveOrders.length} sub="total live" color="var(--amber)" />
          <MetricCard label="Risk Rejections" value={riskRejections} sub="in recent audit log" color="var(--red)" />
        </Grid>
      </Section>

      <Section title="Strategies & Backtests">
        <Grid>
          <MetricCard label="Total Strategies" value={stats?.total_strategies ?? '—'} color="var(--violet)" />
          <MetricCard label="Running" value={runningRuns.length} color="var(--green)" dot={runningRuns.length > 0 ? '#22c55e' : '#8888a0'} />
          <MetricCard label="Active Assignments" value={stats?.active_assignments ?? '—'} color="var(--amber)" />
          <MetricCard label="Backtests" value={backtestRuns.length} color="var(--cyan)" />
        </Grid>
      </Section>

      <Section title="Brokers">
        <Grid cols={brokerTypes.length > 0 ? Math.min(Object.keys(brokerTypes).length, 4) : 1}>
          {Object.keys(brokerTypes).length === 0 ? (
            <MetricCard label="Broker Connections" value={activeBrokers} sub={`${oauthedBrokers} oauthed`} color="var(--cyan)" />
          ) : (
            <>
              <MetricCard label="Connected" value={activeBrokers} sub={`${oauthedBrokers} oauthed`} color="var(--green)" dot={activeBrokers > 0 ? '#22c55e' : '#ef4444'} />
              {Object.entries(brokerTypes).slice(0, 3).map(([type, count]) => (
                <MetricCard key={type} label={type} value={count} color="var(--violet)" />
              ))}
            </>
          )}
        </Grid>
      </Section>

      <Section title="System">
        <Grid>
          <MetricCard label="CPU" value={cpu !== null ? `${cpu}%` : '—'} color="var(--cyan)" />
          <MetricCard label="RAM" value={memPct !== null ? `${memPct}%` : '—'} sub={memUsed ? `${(memUsed / 1024 / 1024).toFixed(0)} MB` : undefined} color="var(--green)" />
          <MetricCard label="API Latency" value={latencyMs !== null ? `${latencyMs}ms` : '—'} color="var(--violet)" />
          <MetricCard label="WebSocket" value={wsConnections !== null ? wsConnections : '—'} color="var(--amber)" />
        </Grid>
      </Section>

      <Section title="Monitoring & Infrastructure">
        <Grid>
          <MetricCard label="Prometheus" value={prometheusHealth} color={prometheusHealth === 'OK' ? 'var(--green)' : 'var(--red)'} dot={prometheusHealth === 'OK' ? '#22c55e' : '#ef4444'} />
          <MetricCard label="Grafana" value={grafanaHealth} color={grafanaHealth === 'OK' ? 'var(--green)' : 'var(--red)'} dot={grafanaHealth === 'OK' ? '#22c55e' : '#ef4444'} />
          <MetricCard label="Redis" value={redisActive === true ? 'connected' : redisActive === false ? 'disconnected' : '—'} color={redisActive === true ? 'var(--green)' : 'var(--red)'} dot={redisActive === true ? '#22c55e' : '#ef4444'} />
          <MetricCard label="Redis Memory" value={redisUsage || '—'} color="var(--cyan)" />
        </Grid>
      </Section>

      <Section title="Operational">
        <Grid>
          <MetricCard label="Error Rate" value={auditEntries.length > 0 ? `${errorRate}%` : '—'} sub={`${errorEntries.length}/${auditEntries.length} entries`} color={parseFloat(errorRate) > 5 ? 'var(--red)' : 'var(--green)'} />
          <MetricCard label="API Requests/min" value={apiRpm !== null ? apiRpm : '—'} color="var(--cyan)" />
          <MetricCard label="Tracked Events" value={a.total_tracked_events ?? '—'} sub={`${a.total_tracked_users ?? 0} users`} color="var(--violet)" />
          <MetricCard label="App Version" value={<span style={{ fontSize: 11 }}><AppVersion /></span> as any} color="var(--amber)" />
        </Grid>
      </Section>

      <div style={{ fontSize: 9, color: 'var(--text-faint)', textAlign: 'center', padding: '20px 0', borderTop: '1px solid var(--border)' }}>
        Auto-refreshes every 5 seconds · Data from existing API endpoints + analytics events · Version: <AppVersion />
      </div>
    </div>
  )
}
