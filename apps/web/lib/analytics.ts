'use client'

let sessionId: string | null = null

function getSessionId(): string {
  if (sessionId) return sessionId
  try {
    const stored = localStorage.getItem('tm_session_id')
    if (stored) {
      sessionId = stored
      return stored
    }
  } catch {}
  const id = `sess_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`
  sessionId = id
  try { localStorage.setItem('tm_session_id', id) } catch {}
  return id
}

function getUserId(): string {
  try {
    return localStorage.getItem('tm_user_id') || ''
  } catch { return '' }
}

export function setUserId(id: string) {
  try { localStorage.setItem('tm_user_id', id) } catch {}
}

export function track(event: string, properties?: Record<string, unknown>) {
  const payload = {
    event,
    properties: properties || {},
    session_id: getSessionId(),
    user_id: getUserId(),
    timestamp: new Date().toISOString(),
  }

  if (typeof navigator !== 'undefined' && navigator.sendBeacon) {
    navigator.sendBeacon('/api/v1/analytics/track', JSON.stringify(payload))
  } else {
    fetch('/api/v1/analytics/track', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      keepalive: true,
    }).catch(() => {})
  }
}

export function trackError(error: Error, context?: Record<string, unknown>) {
  track('error', {
    message: error.message,
    name: error.name,
    stack: error.stack?.slice(0, 500),
    ...context,
  })
}

export function getSessionEvents(): Record<string, number> {
  const counts: Record<string, number> = {}
  return counts
}
