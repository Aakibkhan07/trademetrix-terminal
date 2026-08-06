'use client'

/** Route-level page loader — the app loading.tsx markup verbatim. */
export function PageLoading() {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      height: '100vh', background: 'var(--bg)',
    }}>
      <div style={{
        width: 24, height: 24, border: '2px solid var(--border)',
        borderTopColor: 'var(--cyan)',
        borderRadius: '50%',
        animation: 'spin 0.8s linear infinite',
      }} />
      <style>{'@keyframes spin { to { transform: rotate(360deg) } }'}</style>
    </div>
  )
}

/** Small button spinner (auth page submit state, verbatim). */
export function Spinner({ size = 14, border = '2px rgba(255,255,255,.3)', top = '#fff', speed = '0.6s' }: {
  size?: number
  border?: string
  top?: string
  speed?: string
}) {
  return (
    <span
      style={{
        display: 'inline-block', width: size, height: size,
        borderRadius: '50%', border, borderTopColor: top,
        animation: `spin ${speed} linear infinite`,
      }}
    />
  )
}

/** Inline "Loading..." text — the repeated `t-faint` loading label pattern. */
export function LoadingText({ label = 'Loading...', fontSize = 11, style }: {
  label?: string
  fontSize?: number
  style?: React.CSSProperties
}) {
  return <span style={{ fontSize, color: 'var(--text-faint)', ...style }}>{label}</span>
}
