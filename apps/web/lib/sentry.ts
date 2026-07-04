const SENTRY_DSN = process.env.NEXT_PUBLIC_SENTRY_DSN || ''

export function initSentry() {
}

export function captureError(_error: unknown, _context?: Record<string, unknown>) {
}

export function setSentryUser(_userId: string, _email?: string) {
}
