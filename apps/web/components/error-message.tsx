'use client'

export function ErrorMessage({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="t-panel" style={{ padding: 24, textAlign: 'center' }}>
      <p style={{ fontSize: 13, color: '#ef4444', margin: '0 0 12px' }}>{message}</p>
      {onRetry && (
        <button className="t-btn t-btn-sm" onClick={onRetry} style={{ fontSize: 11 }}>
          Retry
        </button>
      )}
    </div>
  )
}
