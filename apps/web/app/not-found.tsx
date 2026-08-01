import Link from 'next/link'

export default function NotFound() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '60vh', gap: 12, padding: 24, textAlign: 'center' }}>
      <div style={{ fontSize: 32 }}>🧭</div>
      <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 700, color: 'var(--text)', margin: 0 }}>
        Page not found
      </h1>
      <p style={{ fontSize: 12, color: 'var(--text-sub)', margin: 0, maxWidth: 420 }}>
        The page you&apos;re looking for doesn&apos;t exist or has moved.
      </p>
      <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
        <Link href="/dashboard" style={{
          padding: '8px 16px', borderRadius: 'var(--radius-md)',
          background: 'var(--gradient-primary)', border: 'none',
          color: '#fff', fontSize: 12, fontWeight: 700, textDecoration: 'none',
          display: 'inline-flex', alignItems: 'center',
        }}>
          Back to Dashboard
        </Link>
      </div>
    </div>
  )
}
