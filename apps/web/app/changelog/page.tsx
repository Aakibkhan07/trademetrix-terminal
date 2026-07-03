'use client'

const CHANGES = [
  { date: '2026-07-04', version: 'v0.1.0-rc1', title: 'Release Candidate 1', items: ['Beta Operations layer: admin support, beta invites, status page', 'Security hardening: middleware, CSP, Redis auth, .env.vault removed', 'Full product audit with LaunchCertification.md'] },
  { date: '2026-07-01', version: 'v0.1.0-beta', title: 'Commercial Launch', items: ['Onboarding wizard (6 steps)', 'Pricing page (4 tiers)', 'Profile page (6 tabs)', 'Help Center, Changelog, Feedback, Analytics', 'Legal pages (privacy, terms, risk, etc.)'] },
  { date: '2026-06-28', version: 'v0.1.0-alpha', title: 'Beta Launch', items: ['Skeleton loading states across all pages', 'EmptyState and ErrorMessage components', 'Toast notifications', 'Aria labels, skip-to-content', 'Nav kill switch and signout'] },
  { date: '2026-06-20', version: 'v0.0.1', title: 'Initial Release', items: ['Dashboard with KPI cards', 'Trading terminal with order entry', 'Portfolio positions and orders', 'Market data streaming', 'Strategy management', 'Broker integration', 'Backtesting engine'] },
]

export default function ChangelogPage() {
  return (
    <div style={{ maxWidth: 700, margin: '0 auto' }}>
      <div style={{ marginBottom: 24 }}>
        <h1 className="t-page-title">Changelog</h1>
        <p className="t-sub" style={{ fontSize: 13 }}>Release history for TradeMetrix Terminal</p>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {CHANGES.map((release, i) => (
          <div key={i} className="t-panel" style={{ padding: 16 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
              <div>
                <h2 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: 'var(--text)' }}>{release.title}</h2>
                <span style={{ fontSize: 11, color: 'var(--text-faint)', fontFamily: 'var(--font-mono)' }}>{release.version}</span>
              </div>
              <span style={{ fontSize: 10, color: 'var(--text-faint)', whiteSpace: 'nowrap' }}>{release.date}</span>
            </div>
            <ul style={{ margin: 0, paddingLeft: 16, fontSize: 12, color: 'var(--text-sub)', display: 'flex', flexDirection: 'column', gap: 4 }}>
              {release.items.map((item, j) => <li key={j}>{item}</li>)}
            </ul>
          </div>
        ))}
      </div>
    </div>
  )
}
