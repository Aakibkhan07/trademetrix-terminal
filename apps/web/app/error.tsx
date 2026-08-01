'use client'

import { useEffect } from 'react'

export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error)
  }, [error])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '60vh', gap: 12, padding: 24, textAlign: 'center' }}>
      <div style={{ fontSize: 32 }}>⚠️</div>
      <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 700, color: 'var(--text)', margin: 0 }}>
        Something went wrong
      </h1>
      <p style={{ fontSize: 12, color: 'var(--text-sub)', margin: 0, maxWidth: 420 }}>
        The page hit an unexpected error. Your data is safe — try reloading this view.
      </p>
      <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
        <button
          onClick={reset}
          style={{
            padding: '8px 16px', borderRadius: 'var(--radius-md)',
            background: 'var(--gradient-primary)', border: 'none',
            color: '#fff', fontSize: 12, fontWeight: 700, cursor: 'pointer',
          }}
        >
          Try again
        </button>
        <a href="/dashboard" style={{
          padding: '8px 16px', borderRadius: 'var(--radius-md)',
          background: 'var(--bg-tertiary)', border: '1px solid var(--border)',
          color: 'var(--text)', fontSize: 12, fontWeight: 700, textDecoration: 'none',
          display: 'inline-flex', alignItems: 'center',
        }}>
          Back to Dashboard
        </a>
      </div>
      {process.env.NODE_ENV === 'development' && (
        <pre style={{ fontSize: 10, color: 'var(--text-faint)', maxWidth: 640, overflow: 'auto', textAlign: 'left', marginTop: 8 }}>
          {error.message}
        </pre>
      )}
    </div>
  )
}
