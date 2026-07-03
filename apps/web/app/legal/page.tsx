'use client'

import Link from 'next/link'

const PAGES = [
  { href: '/legal/privacy', title: 'Privacy Policy', desc: 'How we collect, use, and protect your data' },
  { href: '/legal/terms', title: 'Terms of Service', desc: 'Rules and guidelines for using the platform' },
  { href: '/legal/disclaimer', title: 'Disclaimer', desc: 'Limitations of liability and risk acknowledgment' },
  { href: '/legal/risk-disclosure', title: 'Risk Disclosure', desc: 'Important information about trading risks' },
  { href: '/legal/refund', title: 'Refund Policy', desc: 'Our refund and cancellation policy' },
]

export default function LegalPage() {
  return (
    <div style={{ maxWidth: 700, margin: '0 auto' }}>
      <div style={{ marginBottom: 24 }}>
        <h1 className="t-page-title">Legal</h1>
        <p className="t-sub" style={{ fontSize: 13 }}>Legal documents and policies</p>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {PAGES.map(p => (
          <Link key={p.href} href={p.href} className="t-panel" style={{ padding: 16, textDecoration: 'none', display: 'block' }}>
            <h2 style={{ margin: '0 0 4px', fontSize: 15, fontWeight: 600, color: 'var(--text)' }}>{p.title}</h2>
            <p style={{ margin: 0, fontSize: 12, color: 'var(--text-faint)' }}>{p.desc}</p>
          </Link>
        ))}
      </div>
    </div>
  )
}
