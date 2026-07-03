import * as Sentry from '@sentry/nextjs'

const SENTRY_DSN = process.env.NEXT_PUBLIC_SENTRY_DSN || ''

Sentry.init({
  dsn: SENTRY_DSN || undefined,
  environment: process.env.NEXT_PUBLIC_APP_ENV || 'development',
  release: process.env.NEXT_PUBLIC_APP_VERSION || '0.0.0',
  tracesSampleRate: 0.1,
  enabled: !!SENTRY_DSN,
})
