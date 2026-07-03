'use client'

import { useState } from 'react'
import { useToast } from '@/lib/use-toast'
import { EmptyState } from '@/components/empty-state'

const CATEGORIES = [
  { key: 'getting-started', title: 'Getting Started', desc: 'Setup your account, connect brokers, and make your first trade', icon: '1' },
  { key: 'trading', title: 'Trading', desc: 'Place orders, manage positions, and understand order types', icon: 'O' },
  { key: 'strategies', title: 'Strategies', desc: 'Create, backtest, and deploy automated trading strategies', icon: 'S' },
  { key: 'brokers', title: 'Brokers', desc: 'Connect and manage your broker accounts', icon: 'B' },
  { key: 'risk', title: 'Risk Management', desc: 'Configure kill switches, drawdown limits, and circuit breakers', icon: 'R' },
  { key: 'account', title: 'Account & Billing', desc: 'Manage your subscription, billing, and account settings', icon: 'U' },
]

const VIDEOS = [
  { title: 'Quick Start Guide', duration: '3:45', desc: 'Get up and running in under 5 minutes' },
  { title: 'Advanced Order Types', duration: '8:20', desc: 'Limit, stop-loss, bracket, and more' },
  { title: 'Strategy Backtesting', duration: '12:10', desc: 'Build and test your first strategy' },
]

const DOCS = [
  { title: 'API Reference', desc: 'Complete API documentation for developers' },
  { title: 'Webhook Guide', desc: 'Integrate TradingView alerts and external signals' },
  { title: 'Security Best Practices', desc: 'Keep your account and API keys secure' },
]

export default function HelpPage() {
  const { toast } = useToast()
  const [search, setSearch] = useState('')

  return (
    <div style={{ maxWidth: 800, margin: '0 auto' }}>
      <div style={{ marginBottom: 24 }}>
        <h1 className="t-page-title">Help Center</h1>
        <p className="t-sub" style={{ fontSize: 13 }}>Documentation, guides, and support</p>
      </div>

      <div className="t-panel" style={{ padding: 16, marginBottom: 24 }}>
        <input className="t-input" value={search} onChange={e => setSearch(e.target.value)} placeholder="Search help articles..." style={{ width: '100%', fontSize: 13 }} />
      </div>

      <h2 style={{ fontFamily: 'Outfit', fontSize: 14, margin: '0 0 12px', color: '#f0f0f5' }}>Categories</h2>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 10, marginBottom: 24 }}>
        {CATEGORIES.filter(c => c.title.toLowerCase().includes(search.toLowerCase())).map(cat => (
          <button key={cat.key} className="t-panel" onClick={() => toast('info', `${cat.title} help section coming soon`)} style={{ padding: 16, cursor: 'pointer', textAlign: 'left', border: 'none', fontFamily: 'inherit', width: '100%' }}>
            <div style={{ width: 36, height: 36, borderRadius: '50%', background: 'rgba(139,92,246,0.12)', color: 'var(--violet)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 16, fontWeight: 700, marginBottom: 10 }}>{cat.icon}</div>
            <h3 style={{ margin: '0 0 4px', fontSize: 13, fontWeight: 600, color: 'var(--text)' }}>{cat.title}</h3>
            <p style={{ margin: 0, fontSize: 11, color: 'var(--text-faint)' }}>{cat.desc}</p>
          </button>
        ))}
      </div>

      <h2 style={{ fontFamily: 'Outfit', fontSize: 14, margin: '0 0 12px', color: '#f0f0f5' }}>Video Tutorials</h2>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 10, marginBottom: 24 }}>
        {VIDEOS.map(v => (
          <button key={v.title} className="t-panel" onClick={() => toast('info', `Video: ${v.title}`)} style={{ padding: 16, cursor: 'pointer', textAlign: 'left', border: 'none', fontFamily: 'inherit', width: '100%' }}>
            <div style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--violet)', marginBottom: 6 }}>{v.duration}</div>
            <h3 style={{ margin: '0 0 4px', fontSize: 13, fontWeight: 600 }}>{v.title}</h3>
            <p style={{ margin: 0, fontSize: 11, color: 'var(--text-faint)' }}>{v.desc}</p>
          </button>
        ))}
      </div>

      <h2 style={{ fontFamily: 'Outfit', fontSize: 14, margin: '0 0 12px', color: '#f0f0f5' }}>Documentation</h2>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 24 }}>
        {DOCS.map(d => (
          <button key={d.title} className="t-panel" onClick={() => toast('info', `Opening ${d.title} docs`)} style={{ padding: 14, cursor: 'pointer', textAlign: 'left', border: 'none', fontFamily: 'inherit', width: '100%' }}>
            <h3 style={{ margin: '0 0 4px', fontSize: 13, fontWeight: 600 }}>{d.title}</h3>
            <p style={{ margin: 0, fontSize: 11, color: 'var(--text-faint)' }}>{d.desc}</p>
          </button>
        ))}
      </div>

      <div className="t-panel" style={{ padding: 16, textAlign: 'center' }}>
        <p style={{ fontSize: 13, color: 'var(--text-sub)', margin: '0 0 12px' }}>Need more help? Contact our support team.</p>
        <button className="t-btn t-btn-primary" onClick={() => toast('success', 'Support ticket opened')} style={{ fontSize: 11 }}>Contact Support</button>
      </div>
    </div>
  )
}
