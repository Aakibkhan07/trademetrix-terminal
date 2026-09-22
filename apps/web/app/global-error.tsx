'use client'

export default function GlobalError({ error }: { error: Error & { digest?: string } }) {
  return (
    <html>
      <body>
        <div style={{ padding: '40px 20px', textAlign: 'center', fontFamily: 'system-ui' }}>
          <h1 style={{ fontSize: 'var(--text-xl)', fontWeight: 600, marginBottom: 'var(--space-sm)' }}>Something went wrong</h1>
          <p style={{ fontSize: 'var(--text-sm)', color: 'var(--text-sub)' }}>An unexpected error occurred. Our team has been notified.</p>
          <button
          onClick={() => window.location.reload()}
          style={{
            marginTop: 'var(--space-md)', padding: 'var(--space-xs) var(--space-md)', fontSize: 'var(--text-xs)', borderRadius: 6, border: '1px solid var(--border)',
            background: 'var(--panel-2)', color: 'var(--text)', cursor: 'pointer',
          }}
          >
            Reload page
          </button>
        </div>
      </body>
    </html>
  )
}
