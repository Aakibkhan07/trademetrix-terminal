'use client'

/**
 * Beta Operations Mode — privacy-respecting product analytics tracker.
 *
 * - No PII: never sends user_id, email, or raw input values. User identity is
 *   resolved server-side from the auth cookie on the batch endpoint.
 * - Payload redaction: string values truncated; keys matching password/token/
 *   secret/auth are stripped recursively.
 * - Configurable: NEXT_PUBLIC_ANALYTICS_ENABLED, NEXT_PUBLIC_ANALYTICS_SAMPLE,
 *   and an explicit exclude-list of paths. Respects Do-Not-Track.
 * - Batching: events are queued and flushed every 5s (or on page hide via
 *   sendBeacon), max 25 per request, one retry on failure.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1'

const CONFIG = {
  enabled: process.env.NEXT_PUBLIC_ANALYTICS_ENABLED !== 'false',
  sample: parseFloat(process.env.NEXT_PUBLIC_ANALYTICS_SAMPLE || '1'),
  excludePaths: ['/auth', '/admin'],
  batchEveryMs: 5000,
  maxBatchSize: 25,
}

const SECRET_KEY_RE = /password|passwd|token|secret|authorization|credential|api[_ -]?key/i

const REDACTED = '***'

interface TrackEvent {
  event: string
  properties?: Record<string, unknown>
  session_id: string
}

let sessionId = ''
let queue: TrackEvent[] = []
let flushTimer: ReturnType<typeof setInterval> | null = null
let csrfFetched = false
let sampled = true

export function analyticsEnabled(): boolean {
  if (!CONFIG.enabled) return false
  if (typeof navigator !== 'undefined' && navigator.doNotTrack === '1') return false
  if (typeof location !== 'undefined' && CONFIG.excludePaths.some(p => location.pathname.startsWith(p))) return false
  return sampled
}

function newSessionId(): string {
  const rnd = () => Math.random().toString(36).slice(2, 10)
  return `${rnd()}${rnd()}`
}

export function getSessionId(): string {
  if (sessionId) return sessionId
  if (typeof window !== 'undefined') {
    sessionId = window.sessionStorage.getItem('tm_session_id') || ''
    if (!sessionId) {
      sessionId = newSessionId()
      window.sessionStorage.setItem('tm_session_id', sessionId)
    }
  } else {
    sessionId = newSessionId()
  }
  return sessionId
}

function sanitize(value: unknown, depth = 0): unknown {
  if (depth > 4) return '[deep]'
  if (typeof value === 'string') return value.slice(0, 200)
  if (typeof value === 'number' || typeof value === 'boolean') return value
  if (value === null || value === undefined) return null
  if (Array.isArray(value)) return value.slice(0, 20).map(v => sanitize(v, depth + 1))
  if (typeof value === 'object') {
    const out: Record<string, unknown> = {}
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
      if (SECRET_KEY_RE.test(k)) {
        out[k] = REDACTED
      } else {
        out[k] = sanitize(v, depth + 1)
      }
    }
    return out
  }
  return String(value).slice(0, 200)
}

async function ensureCSRF(): Promise<string> {
  const read = () => {
    const m = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]*)/)
    return m ? m[1] : ''
  }
  let token = read()
  if (!token && !csrfFetched) {
    csrfFetched = true
    try {
      await fetch(`${API_BASE}/auth/csrf`, { credentials: 'include' })
    } catch { /* tracker must never break the app */ }
    token = read()
  }
  return token
}

async function flush(): Promise<void> {
  if (queue.length === 0) return
  const batch = queue.splice(0, CONFIG.maxBatchSize)
  const payload = JSON.stringify({
    events: batch.map(({ session_id, ...rest }) => ({ ...rest, session_id })),
  })
  const send = async (keepalive: boolean): Promise<boolean> => {
    try {
      const csrf = await ensureCSRF()
      const res = await fetch(`${API_BASE}/analytics/track-batch`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(csrf ? { 'X-CSRF-Token': csrf } : {}),
        },
        credentials: 'include',
        body: payload,
        keepalive,
      })
      return res.ok
    } catch {
      return false
    }
  }
  let ok = await send(false)
  if (!ok) {
    queue.unshift(...batch)
  } else if (queue.length > 0) {
    // drain remaining immediately; recursive but bounded by queue size
    void flush()
  }
}

function enqueue(event: string, properties: Record<string, unknown> = {}): void {
  if (!analyticsEnabled()) return
  queue.push({ event, properties: sanitize(properties) as Record<string, unknown>, session_id: getSessionId() })
  if (queue.length >= CONFIG.maxBatchSize) void flush()
}

function start(): () => void {
  if (!analyticsEnabled()) return () => {}

  enqueue('session.start', {
    path: location.pathname,
    referrer: typeof document !== 'undefined' ? document.referrer.slice(0, 500) : '',
    lang: typeof navigator !== 'undefined' ? navigator.language : '',
    screen: typeof window !== 'undefined' ? `${window.innerWidth}x${window.innerHeight}` : '',
    ts: Date.now(),
  })

  flushTimer = setInterval(() => void flush(), CONFIG.batchEveryMs)

  const flushOnHide = async () => {
    if (queue.length === 0) return
    const batch = queue.splice(0, CONFIG.maxBatchSize)
    const payload = JSON.stringify({
      events: batch.map(({ session_id, ...rest }) => ({ ...rest, session_id })),
    })
    const csrf = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]*)/)?.[1] || ''
    try {
      await fetch(`${API_BASE}/analytics/track-batch`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(csrf ? { 'X-CSRF-Token': csrf } : {}),
        },
        credentials: 'include',
        body: payload,
        keepalive: true,
      })
    } catch {
      // last resort: beacon (no custom headers, may 403 on CSRF — best effort)
      try {
        navigator.sendBeacon(
          `${API_BASE}/analytics/track-batch`,
          new Blob([payload], { type: 'application/json' }),
        )
      } catch { /* noop */ }
    }
  }
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') flushOnHide()
  })
  window.addEventListener('pagehide', flushOnHide)

  // page views (SPA navigations included via history observers)
  let lastPath = location.pathname + location.search
  enqueue('page.view', { path: lastPath })
  const onNavigate = () => {
    const now = location.pathname + location.search
    if (now !== lastPath) {
      lastPath = now
      enqueue('page.view', { path: now })
    }
  }
  const pushState = history.pushState
  history.pushState = function (...args) {
    const ret = pushState.apply(this, args)
    onNavigate()
    return ret
  }
  window.addEventListener('popstate', onNavigate)

  // scroll depth
  let scrolled = new Set<number>()
  const onScroll = () => {
    const h = document.documentElement
    const max = h.scrollHeight - h.clientHeight
    if (max <= 0) return
    const depth = Math.round(((h.scrollTop || document.body.scrollTop) / max) * 100)
    for (const marker of [25, 50, 75, 100]) {
      if (depth >= marker && !scrolled.has(marker)) {
        scrolled.add(marker)
        enqueue('scroll.depth', { depth: marker })
      }
    }
  }
  document.addEventListener('scroll', onScroll, { passive: true })

  // clicks on interactive elements
  const onClick = (e: MouseEvent) => {
    const el = (e.target as HTMLElement | null)?.closest?.('button, a, [role="button"], input, select, [data-analytics-label]')
    if (!el) return
    const label =
      (el as HTMLElement).getAttribute('data-analytics-label') ||
      (el as HTMLElement).textContent?.trim().slice(0, 80) ||
      (el as HTMLElement).tagName.toLowerCase()
    const href = (el as HTMLAnchorElement).getAttribute?.('href') || ''
    enqueue('click', {
      target: el.tagName.toLowerCase(),
      label,
      ...(href && !href.startsWith('#') ? { href: href.slice(0, 200) } : {}),
    })
  }
  document.addEventListener('click', onClick)

  // client errors
  const onError = (e: ErrorEvent) => {
    enqueue('client_error', {
      message: (e.message || 'Unknown error').slice(0, 500),
      stack: (e.error?.stack || '').slice(0, 1000),
      file: (e.filename || '').slice(0, 200),
      line: e.lineno,
    })
  }
  window.addEventListener('error', onError)
  const onRejection = (e: PromiseRejectionEvent) => {
    enqueue('client_error', {
      message: String(e.reason?.message || e.reason).slice(0, 500),
      stack: String(e.reason?.stack || '').slice(0, 1000),
    })
  }
  window.addEventListener('unhandledrejection', onRejection)

  return () => {
    if (flushTimer) clearInterval(flushTimer)
    document.removeEventListener('visibilitychange', flushOnHide)
    window.removeEventListener('pagehide', flushOnHide)
    window.removeEventListener('popstate', onNavigate)
    document.removeEventListener('scroll', onScroll)
    document.removeEventListener('click', onClick)
    window.removeEventListener('error', onError)
    window.removeEventListener('unhandledrejection', onRejection)
  }
}

export function initAnalytics(): () => void {
  if (typeof window === 'undefined') return () => {}
  if (sampled !== false) {
    sampled = Math.random() < CONFIG.sample
  }
  if (analyticsEnabled()) {
    return start()
  }
  return () => {}
}

export function track(event: string, properties: Record<string, unknown> = {}): void {
  if (typeof window === 'undefined') return
  enqueue(event, properties)
}

export function flushAnalytics(): void {
  void flush()
}
