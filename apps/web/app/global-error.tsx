'use client'

import * as Sentry from '@sentry/nextjs'
import { useEffect } from 'react'

export default function GlobalError({ error }: { error: Error & { digest?: string } }) {
  useEffect(() => {
    Sentry.captureException(error)
  }, [error])

  return (
    <html>
      <body>
        <div style={{ padding: '40px 20px', textAlign: 'center', fontFamily: 'system-ui' }}>
          <h1 style={{ fontSize: 18, fontWeight: 600, marginBottom: 8 }}>Something went wrong</h1>
          <p style={{ fontSize: 13, color: 'gray' }}>An unexpected error occurred. Our team has been notified.</p>
          <button
            onClick={() => window.location.reload()}
            style={{
              marginTop: 16, padding: '8px 20px', fontSize: 13, borderRadius: 6, border: '1px solid #ccc',
              background: 'white', cursor: 'pointer',
            }}
          >
            Reload page
          </button>
        </div>
      </body>
    </html>
  )
}
