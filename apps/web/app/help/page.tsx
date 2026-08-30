'use client'

import { useState } from 'react'
import { useToast } from '@/lib/use-toast'
import { EmptyState } from '@/components/empty-state'
import { ErrorMessage } from '@/components/error-message'
import { SkeletonGrid } from '@/components/skeleton'

const CATEGORIES = [
  { title: 'Getting Started', icon: '🚀', desc: 'New to TradeMetrix? Start here.', color: 'var(--cyan)' },
  { title: 'Trading', icon: '📊', desc: 'Orders, executions, and live trading.', color: 'var(--violet)' },
  { title: 'Brokers', icon: '🏦', desc: 'Connect and manage your brokers.', color: 'var(--amber)' },
  { title: 'Strategies', icon: '⚙️', desc: 'Build, test, and deploy strategies.', color: 'var(--green)' },
  { title: 'Billing', icon: '💳', desc: 'Plans, payments, and invoices.', color: 'var(--pink)' },
  { title: 'Account', icon: '👤', desc: 'Profile, security, and preferences.', color: 'var(--orange)' },
]

const FAQS = [
  { q: 'How do I connect my broker?', a: 'Navigate to the Brokers page, select your broker, and follow the OAuth or API key setup flow. Your credentials are encrypted at rest.' },
  { q: 'What is paper trading?', a: 'Paper trading lets you simulate trades with virtual funds in real market conditions. It is available on all plans and is a great way to test strategies risk-free.' },
  { q: 'How many strategies can I run?', a: 'The number of concurrent strategies depends on your plan: Free (1), Starter (3), Pro (10), and Enterprise (unlimited).' },
  { q: 'How do I cancel an order?', a: 'Open the Trade page, find the open order in the orders table, and click the Cancel button next to it. You can also cancel all open orders at once using the kill switch.' },
  { q: 'What is the kill switch?', a: 'The kill switch instantly cancels all open orders and closes all positions across all connected brokers. It is available on the Risk page for emergency use.' },
  { q: 'How do I upgrade my plan?', a: 'Go to Settings > Subscription to view available plans and upgrade. Changes take effect immediately and are prorated.' },
  { q: 'What data is available?', a: 'We provide real-time and historical data for stocks, indices, ETFs, crypto, and forex. Data availability depends on your subscription tier.' },
  { q: 'Is my API key secure?', a: 'Yes. API keys are encrypted at rest using AES-256 and are never logged or exposed to other users. We follow industry-standard security practices.' },
]

const VIDEOS = [
  { title: 'Setting Up Your First Strategy', duration: '4:32', icon: '▶️' },
  { title: 'Connecting a Broker', duration: '3:15', icon: '▶️' },
  { title: 'Using the Kill Switch', duration: '2:08', icon: '▶️' },
  { title: 'Backtesting Your Strategy', duration: '5:47', icon: '▶️' },
  { title: 'Understanding Risk Metrics', duration: '6:01', icon: '▶️' },
]

const DOCS_LINKS = [
  { title: 'API Reference', desc: 'Full API documentation for developers' },
  { title: 'Strategy SDK', desc: 'Build custom strategies with our SDK' },
  { title: 'Webhook Guide', desc: 'Integrate with external systems via webhooks' },
  { title: 'Data Feeds', desc: 'Available market data feeds and schemas' },
]

export default function HelpPage() {
  const { toast } = useToast()
  const [search, setSearch] = useState('')
  const [openFaq, setOpenFaq] = useState<number | null>(null)

  const filteredFaqs = FAQS.filter(
    f =>
      f.q.toLowerCase().includes(search.toLowerCase()) ||
      f.a.toLowerCase().includes(search.toLowerCase())
  )

  const filteredCategories = CATEGORIES.filter(
    c =>
      c.title.toLowerCase().includes(search.toLowerCase()) ||
      c.desc.toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24, maxWidth: 860 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, flexWrap: 'wrap' }}>
        <div>
          <h1 className="t-page-title" style={{ fontFamily: 'var(--font-display)', fontSize: 22, fontWeight: 700, letterSpacing: '-0.02em' }}>Help Center — Platform Kaise Use Karein</h1>
          <p className="t-page-subtitle" style={{ marginTop: 4 }}>7 steps me start — broker se live tak, Hinglish me</p>
        </div>
        <button className="t-btn" onClick={() => window.print()}>Print Guide</button>
      </div>

      {/* QUICK START GUIDE — in-app, no GitHub */}
      <div className="t-panel" style={{ borderLeft: '3px solid var(--cyan)' }}>
        <div className="t-panel-header" style={{ padding: '12px 16px' }}>
          <h3 className="t-panel-title" style={{ fontSize: 13, letterSpacing: '0.08em' }}>QUICK START — 7 STEPS</h3>
          <span className="t-badge t-badge-cyan" style={{ fontSize: 9 }}>2 MIN ME START</span>
        </div>
        <div className="t-panel-body" style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 14, fontSize: 12, lineHeight: 1.65, color: 'var(--text-sub)' }}>
          {[
            { n: '1', t: 'Account Banao (30 sec)', d: 'ai.trademetrix.tech/auth → Sign Up → email/password → verify → auto /live pe pahunch jaoge. Problem ho toh isi page pe Feedback bhejo.' },
            { n: '2', t: 'Broker Connect (2 min) — sabse zaroori', d: 'Fyers/Zerodha/Dhan/Upstox: /brokers → Connect → apna API Key/Secret dalo → Allow karo → Active + Token valid dikhega. Angel/Kotak: Client Code + Password + API Key + TOTP Secret dalo → Active. Token roz expire hota hai (SEBI) — subah Re-auth dabao, Telegram pe T-60min alert aayega. Aapka Secret encrypted vault me save hota hai, .env me nahi.' },
            { n: '3', t: 'Paper Trading se Start (Risk 0)', d: '/live ya /paper pe NIFTY/BANKNIFTY → Quick Trade → Buy 1 lot → Paper mode me FILLED dikhega, real paisa nahi katega. /positions pe Paper P&L live dekho.' },
            { n: '4', t: 'Strategy Banao', d: '/strategies/builder → + New Strategy → NIFTY + Weekly + 09:15-15:15 → Legs jodo (Buy CE + Sell PE) → right me Payoff Lab me MAX PROFIT/Breakeven dekho → Save → Activity me Paper deploy.' },
            { n: '5', t: 'Backtest — Kaunsi Profitable Hai?', d: '/backtest → NIFTY 365d 1d → Leaderboard → Rank All 10 Now → net P&L se sort, #1 👑 sabse profitable. Builder wali bhi same engine se chalti hai, Deploy to Paper 1 click.' },
            { n: '6', t: 'Live Pe Jao (Ready Ho Toh)', d: 'Paper pe 1 week test ke baad /go-live → LIVE toggle → Confirm + daily loss limit → /live cockpit pe Market OPEN + Stream live. Risk pe Kill Switch hamesha ready.' },
            { n: '7', t: 'Daily Report + Mobile', d: '/reports/daily → aaj ka P&L/Win/Trades → Print/PDF. Roz 18:00 IST pe Email+Telegram auto (keys already VPS me hain). Phone pe Add to Home Screen karo — PWA app ban jayega.' },
          ].map(s => (
            <div key={s.n} style={{ display: 'flex', gap: 12, padding: '10px 12px', border: '1px solid var(--border)', borderRadius: 10, background: 'color-mix(in srgb, var(--panel) 96%, transparent)' }}>
              <div style={{ width: 28, height: 28, borderRadius: '50%', background: 'var(--gradient-primary)', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 12, flexShrink: 0 }}>{s.n}</div>
              <div>
                <div style={{ fontWeight: 700, color: 'var(--text)', fontSize: 12 }}>{s.t}</div>
                <div style={{ marginTop: 2 }}>{s.d}</div>
              </div>
            </div>
          ))}
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 4 }}>
            <a href="/brokers" className="t-btn t-btn-primary" style={{ textDecoration: 'none', fontSize: 11 }}>Go to Brokers →</a>
            <a href="/strategies/builder" className="t-btn" style={{ textDecoration: 'none', fontSize: 11 }}>Build Strategy →</a>
            <a href="/reports/daily" className="t-btn" style={{ textDecoration: 'none', fontSize: 11 }}>Daily Report →</a>
          </div>
        </div>
      </div>

      {/* Search */}
      <div className="t-panel" style={{ padding: 0 }}>
        <div className="t-panel-body" style={{ padding: '16px 20px' }}>
          <input
            className="t-input"
            placeholder="Search for help..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            style={{ width: '100%' }}
          />
        </div>
      </div>

      {/* Categories */}
      <div className="t-grid-auto" style={{ gap: 12 }}>
        {filteredCategories.length > 0 ? (
          filteredCategories.map(cat => (
            <div
              key={cat.title}
              className="t-panel"
              style={{ cursor: 'pointer', transition: 'border-color .15s' }}
              onClick={() => toast('info', `${cat.title} help section coming soon`)}
            >
              <div className="t-panel-body" style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                <div
                  style={{
                    width: 40, height: 40, borderRadius: 10,
                    background: `${cat.color}20`, display: 'flex',
                    alignItems: 'center', justifyContent: 'center', fontSize: 18,
                  }}
                >
                  {cat.icon}
                </div>
                <div>
                  <div style={{ fontSize: 14, fontWeight: 700 }}>{cat.title}</div>
                  <div className="t-faint" style={{ fontSize: 11 }}>{cat.desc}</div>
                </div>
              </div>
            </div>
          ))
        ) : (
          <EmptyState title="No results found" description="Try a different search term." />
        )}
      </div>

      {/* FAQ */}
      <div className="t-panel" style={{ padding: 0 }}>
        <div className="t-panel-header">
          <h3 className="t-panel-title">Frequently Asked Questions</h3>
        </div>
        <div className="t-panel-body" style={{ padding: 0 }}>
          {filteredFaqs.map((faq, i) => (
            <div key={i} style={{ borderBottom: i < filteredFaqs.length - 1 ? '1px solid var(--border)' : 'none' }}>
              <button
                onClick={() => setOpenFaq(openFaq === i ? null : i)}
                style={{
                  width: '100%', display: 'flex', justifyContent: 'space-between',
                  alignItems: 'center', padding: '14px 20px', background: 'none',
                  border: 'none', cursor: 'pointer', color: 'inherit',
                  fontFamily: 'inherit', fontSize: 13, fontWeight: 600, textAlign: 'left',
                }}
              >
                <span>{faq.q}</span>
                <span style={{
                  transform: openFaq === i ? 'rotate(180deg)' : 'rotate(0deg)',
                  transition: 'transform .2s', fontSize: 12, color: 'var(--faint)',
                }}>
                  ▼
                </span>
              </button>
              {openFaq === i && (
                <div style={{ padding: '0 20px 14px', fontSize: 12, color: 'var(--faint)', lineHeight: 1.6 }}>
                  {faq.a}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Video Tutorials */}
      <div className="t-panel" style={{ padding: 0 }}>
        <div className="t-panel-header">
          <h3 className="t-panel-title">Video Tutorials</h3>
          <span className="t-badge t-badge-sub">{VIDEOS.length} videos</span>
        </div>
        <div className="t-panel-body">
          <div className="t-grid-auto" style={{ gap: 10 }}>
            {VIDEOS.map(video => (
              <div
                key={video.title}
                className="t-panel"
                style={{ cursor: 'pointer', padding: '12px 14px', background: 'var(--panel-2)' }}
                onClick={() => toast('info', `Video: ${video.title}`)}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <div style={{
                    width: 36, height: 36, borderRadius: 8,
                    background: 'var(--gradient-primary)', display: 'flex',
                    alignItems: 'center', justifyContent: 'center', fontSize: 14,
                  }}>
                    {video.icon}
                  </div>
                  <div>
                    <div style={{ fontSize: 12, fontWeight: 600 }}>{video.title}</div>
                    <div className="t-faint" style={{ fontSize: 10 }}>{video.duration}</div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Documentation */}
      <div className="t-panel" style={{ padding: 0 }}>
        <div className="t-panel-header">
          <h3 className="t-panel-title">Documentation</h3>
        </div>
        <div className="t-panel-body">
          <div className="t-grid-2" style={{ gap: 10 }}>
            {DOCS_LINKS.map(doc => (
              <div
                key={doc.title}
                className="t-panel"
                style={{ cursor: 'pointer', padding: '12px 14px', background: 'var(--panel-2)' }}
                onClick={() => toast('info', `Opening ${doc.title} docs`)}
              >
                <div style={{ fontSize: 13, fontWeight: 600 }}>{doc.title}</div>
                <div className="t-faint" style={{ fontSize: 11, marginTop: 2 }}>{doc.desc}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Contact Support */}
      <div className="t-panel" style={{ padding: 0, textAlign: 'center' }}>
        <div className="t-panel-body" style={{ padding: '28px 20px' }}>
          <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 6 }}>Still need help?</div>
          <p className="t-faint" style={{ fontSize: 12, margin: '0 0 16px' }}>
            Our support team is here to help you.
          </p>
          <button className="t-btn t-btn-primary" onClick={() => toast('success', 'Support ticket opened')}>
            Contact Support
          </button>
        </div>
      </div>
    </div>
  )
}
