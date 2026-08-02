'use client'

import { useState, useEffect, useCallback, type ReactNode } from 'react'
import { API_BASE } from '@/lib/api'
import { SkeletonCard } from '@/components/skeleton'

type ComponentStatus = 'operational' | 'down' | 'degraded'

interface Component {
  name: string
  status: ComponentStatus
  lastChecked: string
}

interface HealthPayload {
  status?: string
  service?: string
  version?: string
  uptime_seconds?: number
}

interface MetricsPayload {
  status?: string
  system?: {
    uptime_seconds?: number
    cpu_percent?: number
    memory_rss_bytes?: number
    threads?: number
    open_fds?: number
  }
  requests?: {
    total?: number
    errors?: number
    error_rate?: number
    avg_latency_ms?: number
  }
}

function formatUptime(seconds: number): string {
  const d = Math.floor(seconds / 86400)
  const h = Math.floor((seconds % 86400) / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (d > 0) return `${d}d ${h}h ${m}m`
  if (h > 0) return `${h}h ${m}m`
  return `${m}m`
}

function StatusDot({ status }: { status: ComponentStatus }) {
  const color = status === 'operational' ? 'var(--green)' : status === 'down' ? 'var(--red)' : 'var(--amber)'
  return (
    <span style={{
      display: 'inline-block', width: 10, height: 10, borderRadius: '50%',
      background: color, marginRight: 6,
    }} />
  )
}

function StatusBadge({ children, color }: { children: ReactNode; color: string }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      padding: '2px 8px', borderRadius: 4, fontSize: 9, fontWeight: 600,
      background: `${color}20`, color,
    }}>
      {children}
    </span>
  )
}

export default function StatusPage() {
  const [components, setComponents] = useState<Component[]>([])
  const [loading, setLoading] = useState(true)
  const [lastChecked, setLastChecked] = useState<string | null>(null)
  const [health, setHealth] = useState<HealthPayload | null>(null)
  const [metrics, setMetrics] = useState<MetricsPayload | null>(null)

  const checkComponents = useCallback(async () => {
    const results: Component[] = []
    const now = new Date().toLocaleTimeString()

    try {
      const healthRes = await fetch(`${API_BASE}/health`)
      const healthData: HealthPayload = await healthRes.json()
      setHealth(healthData)
      results.push({ name: 'API Server', status: healthRes.ok && healthData.status === 'ok' ? 'operational' : 'down', lastChecked: now })
    } catch {
      setHealth(null)
      results.push({ name: 'API Server', status: 'down', lastChecked: now })
    }

    results.push({ name: 'Web App', status: 'operational', lastChecked: now })

    try {
      const readyRes = await fetch(`${API_BASE}/health/ready`)
      const readyData = await readyRes.json()
      const dbOk = readyData?.dependencies?.database === true
      results.push({ name: 'Database', status: dbOk ? 'operational' : 'degraded', lastChecked: now })
      const cacheOk = readyData?.dependencies?.cache === true
      results.push({ name: 'Cache (Redis)', status: cacheOk ? 'operational' : 'degraded', lastChecked: now })
    } catch {
      results.push({ name: 'Database', status: 'down', lastChecked: now })
      results.push({ name: 'Cache (Redis)', status: 'down', lastChecked: now })
    }

    try {
      const meRes = await fetch(`${API_BASE}/auth/me`)
      if (meRes.ok) {
        const ws = new EventSource(`${API_BASE}/events/stream`)
        await new Promise<void>((resolve, reject) => {
          ws.onopen = () => { ws.close(); resolve() }
          ws.onerror = () => { ws.close(); reject() }
          setTimeout(() => { ws.close(); reject() }, 3000)
        })
        results.push({ name: 'Event Stream (WebSocket)', status: 'operational', lastChecked: now })
      } else {
        results.push({ name: 'Event Stream (WebSocket)', status: 'operational', lastChecked: now })
      }
    } catch {
      results.push({ name: 'Event Stream (WebSocket)', status: 'down', lastChecked: now })
    }

    try {
      const metricsRes = await fetch(`${API_BASE}/health/metrics`)
      if (metricsRes.ok) {
        const metricsData: MetricsPayload = await metricsRes.json()
        setMetrics(metricsData)
      }
    } catch {
      setMetrics(null)
    }

    setComponents(results)
    setLastChecked(now)
    setLoading(false)
  }, [])

  useEffect(() => {
    checkComponents()
    const int = setInterval(() => { checkComponents() }, 60000)
    return () => clearInterval(int)
  }, [checkComponents])

  const allOperational = components.length > 0 && components.every(c => c.status === 'operational')

  const sys = metrics?.system
  const req = metrics?.requests

  return (
    <div style={{ maxWidth: 800, margin: '0 auto', padding: '24px 16px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 24 }}>
        <div>
          <h1 className="t-page-title" style={{ margin: 0 }}>System Status</h1>
          <p className="t-sub" style={{ fontSize: 12, margin: '4px 0 0' }}>
            {lastChecked ? `Last checked: ${lastChecked} · refreshes automatically` : 'Checking live health...'}
          </p>
        </div>
        <StatusBadge color={allOperational ? 'var(--green)' : 'var(--red)'}>
          <span style={{
            display: 'inline-block', width: 6, height: 6, borderRadius: '50%',
            background: allOperational ? 'var(--green)' : 'var(--red)',
          }} />
          {allOperational ? 'All Systems Operational' : 'Issues Detected'}
        </StatusBadge>
      </div>

      <h2 style={{ fontFamily: 'var(--font-display)', fontSize: 14, margin: '0 0 12px', color: 'var(--text)' }}>System Components</h2>
      {loading ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 24 }}>
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 24 }}>
          {components.map(c => (
            <div key={c.name} className="t-panel" style={{ padding: '12px 16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <StatusDot status={c.status} />
                <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)' }}>{c.name}</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{
                  fontSize: 11, fontWeight: 500,
                  color: c.status === 'operational' ? 'var(--green)' : c.status === 'down' ? 'var(--red)' : 'var(--amber)',
                }}>
                  {c.status === 'operational' ? 'Operational' : c.status === 'down' ? 'Down' : 'Degraded'}
                </span>
                <span style={{ fontSize: 9, color: 'var(--text-faint)' }}>{c.lastChecked}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      <h2 style={{ fontFamily: 'var(--font-display)', fontSize: 14, margin: '0 0 12px', color: 'var(--text)' }}>Service Details</h2>
      <div className="t-panel" style={{ padding: 16, marginBottom: 24 }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 12 }}>
          <div>
            <div style={{ fontSize: 9, color: 'var(--text-sub)', fontWeight: 600, letterSpacing: '0.03em', marginBottom: 4 }}>SERVICE</div>
            <div style={{ fontSize: 14, fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--text)' }}>{health?.service || '—'}</div>
          </div>
          <div>
            <div style={{ fontSize: 9, color: 'var(--text-sub)', fontWeight: 600, letterSpacing: '0.03em', marginBottom: 4 }}>VERSION</div>
            <div style={{ fontSize: 14, fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--text)' }}>{health?.version || '—'}</div>
          </div>
          <div>
            <div style={{ fontSize: 9, color: 'var(--text-sub)', fontWeight: 600, letterSpacing: '0.03em', marginBottom: 4 }}>API UPTIME</div>
            <div style={{ fontSize: 14, fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--green)' }}>
              {health?.uptime_seconds ? formatUptime(health.uptime_seconds) : '—'}
            </div>
          </div>
          <div>
            <div style={{ fontSize: 9, color: 'var(--text-sub)', fontWeight: 600, letterSpacing: '0.03em', marginBottom: 4 }}>CPU</div>
            <div style={{ fontSize: 14, fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--text)' }}>
              {sys?.cpu_percent != null ? `${sys.cpu_percent.toFixed(1)}%` : '—'}
            </div>
          </div>
          <div>
            <div style={{ fontSize: 9, color: 'var(--text-sub)', fontWeight: 600, letterSpacing: '0.03em', marginBottom: 4 }}>MEMORY</div>
            <div style={{ fontSize: 14, fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--text)' }}>
              {sys?.memory_rss_bytes ? `${(sys.memory_rss_bytes / 1024 / 1024).toFixed(0)} MB` : '—'}
            </div>
          </div>
          {req && (
            <div>
              <div style={{ fontSize: 9, color: 'var(--text-sub)', fontWeight: 600, letterSpacing: '0.03em', marginBottom: 4 }}>REQUESTS / ERRORS</div>
              <div style={{ fontSize: 14, fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--text)' }}>
                {req.total?.toLocaleString() ?? '—'} / {(req.errors ?? 0).toLocaleString()}
              </div>
            </div>
          )}
        </div>
      </div>

      <h2 style={{ fontFamily: 'var(--font-display)', fontSize: 14, margin: '0 0 12px', color: 'var(--text)' }}>Maintenance</h2>
      <div className="t-panel" style={{ padding: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{
            display: 'inline-block', width: 10, height: 10, borderRadius: '50%',
            background: 'var(--green)',
          }} />
          <span style={{ fontSize: 13, color: 'var(--text)' }}>No scheduled maintenance — deploy updates appear in the Changelog.</span>
        </div>
      </div>
    </div>
  )
}
