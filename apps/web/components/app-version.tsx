'use client'

const VERSION = process.env.NEXT_PUBLIC_APP_VERSION || '0.0.0'

export function AppVersion() {
  return <span style={{ fontSize: 9, color: 'var(--text-faint)', fontFamily: 'var(--font-mono)' }}>v{VERSION}</span>
}

export function getAppVersion(): string {
  return VERSION
}
