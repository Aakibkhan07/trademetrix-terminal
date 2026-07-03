import * as Sentry from '@sentry/nextjs'

const SENTRY_DSN = process.env.NEXT_PUBLIC_SENTRY_DSN || ''

export function initSentry() {
  if (!SENTRY_DSN) return
  if (typeof window === 'undefined') return
  if ((window as any).__sentry_initted) return
  Sentry.init({
    dsn: SENTRY_DSN,
    environment: process.env.NEXT_PUBLIC_APP_ENV || 'development',
    release: process.env.NEXT_PUBLIC_APP_VERSION || '0.0.0',
    tracesSampleRate: 0.1,
  });
  (window as any).__sentry_initted = true
}

export function captureError(error: unknown, context?: Record<string, unknown>) {
  if (!SENTRY_DSN) return
  Sentry.captureException(error, { extra: context })
}

export function setSentryUser(userId: string, email?: string) {
  if (!SENTRY_DSN) return
  Sentry.setUser({ id: userId, email })
}
