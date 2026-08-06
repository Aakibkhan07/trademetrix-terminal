import Link from 'next/link'
import Logo from '@/components/logo'

const footerColumnTitle: React.CSSProperties = {
  fontSize: 10, fontWeight: 700, letterSpacing: '0.05em', textTransform: 'uppercase',
  color: 'var(--text-sub)', marginBottom: 10,
}
const footerLink: React.CSSProperties = { color: 'var(--text-faint)', textDecoration: 'none' }
const footerColumn: React.CSSProperties = { display: 'flex', flexDirection: 'column', gap: 6 }

export default function LandingPage() {
  return (
    <div style={{
      minHeight: '100vh', background: 'var(--bg)', color: 'var(--text)',
      fontFamily: 'var(--font-body)',
      display: 'flex', flexDirection: 'column',
    }}>
      <header style={{
        height: 56, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '0 24px', borderBottom: '1px solid color-mix(in srgb, var(--violet) 15%, transparent)',
      }}>
        <Link href="/" style={{
          display: 'flex', alignItems: 'center', gap: 8, textDecoration: 'none',
          fontFamily: 'var(--font-display)', fontSize: 16, fontWeight: 700,
          background: 'var(--gradient-primary)',
          WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent',
        }}>
          <Logo size={22} />
          TradeMetrix
        </Link>
        <nav style={{ display: 'flex', gap: 16, alignItems: 'center' }}>
          <Link href="/pricing" style={{
            fontSize: 12, fontWeight: 600, color: 'var(--text-sub)', textDecoration: 'none',
            letterSpacing: '0.03em', transition: 'color 0.15s',
          }}>Pricing</Link>
          <Link href="/status" style={{
            fontSize: 12, fontWeight: 600, color: 'var(--text-sub)', textDecoration: 'none',
            letterSpacing: '0.03em', transition: 'color 0.15s',
          }}>System Status</Link>
          <Link href="/live" style={{
            fontSize: 12, fontWeight: 600, color: 'var(--text-sub)', textDecoration: 'none',
            letterSpacing: '0.03em', transition: 'color 0.15s',
          }}>Dashboard</Link>
          <Link href="/auth" style={{
            fontSize: 12, fontWeight: 600, color: 'var(--text-sub)', textDecoration: 'none',
            letterSpacing: '0.03em', transition: 'color 0.15s',
          }}>Sign In</Link>
          <Link href="/live" style={{
            fontSize: 11, fontWeight: 700, letterSpacing: '0.04em',
            padding: '8px 18px', borderRadius: 6, textDecoration: 'none',
            background: 'var(--gradient-primary)',
            color: 'var(--text-inverse)', transition: 'opacity 0.15s',
          }}>Get Started</Link>
        </nav>
      </header>

      <main style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '60px 24px', textAlign: 'center' }}>
        <div style={{ maxWidth: 720 }}>
          <div style={{
            display: 'inline-block', padding: '4px 12px', borderRadius: 20, fontSize: 10,
            fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase',
            background: 'color-mix(in srgb, var(--cyan) 8%, transparent)', color: 'var(--cyan)',
            border: '1px solid color-mix(in srgb, var(--cyan) 12%, transparent)', marginBottom: 24,
          }}>Multi-Broker Algorithmic Trading Platform</div>

          <h1 style={{
            fontSize: 44, fontWeight: 700, lineHeight: 1.15, margin: '0 0 16px',
            fontFamily: 'var(--font-display)', color: 'var(--text-inverse)',
          }}>
            Trade across{' '}
            <span style={{ background: 'var(--gradient-primary)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
              10+ brokers
            </span>
            {' '}with one terminal
          </h1>

          <p style={{ fontSize: 15, lineHeight: 1.6, color: 'var(--text-sub)', maxWidth: 520, margin: '0 auto 32px' }}>
            Automated trading strategies, real-time market data, AI-powered analytics,
            and risk management — all in one place. Connect your broker and start trading.
          </p>

          <div style={{ display: 'flex', gap: 12, justifyContent: 'center', flexWrap: 'wrap' }}>
            <Link href="/live" style={{
              padding: '12px 28px', borderRadius: 8, fontSize: 13, fontWeight: 700,
              letterSpacing: '0.03em', textDecoration: 'none',
              background: 'var(--gradient-primary)',
              color: 'var(--text-inverse)', transition: 'opacity 0.15s',
            }}>Launch Live Dashboard</Link>
            <Link href="/auth" style={{
              padding: '12px 28px', borderRadius: 8, fontSize: 13, fontWeight: 600,
              letterSpacing: '0.03em', textDecoration: 'none',
              border: '1px solid color-mix(in srgb, var(--violet) 30%, transparent)', color: 'var(--text)',
              transition: 'border-color 0.15s',
            }}>Open Terminal</Link>
          </div>
        </div>

        <div style={{
          marginTop: 80, display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
          gap: 16, width: '100%', maxWidth: 800,
        }}>
          {[
            { emoji: 'B', title: '10+ Brokers', desc: 'Fyers, Zerodha, Angel One, Dhan, Upstox, 5Paisa & more' },
            { emoji: 'S', title: '8 Strategies', desc: 'Trend Rider, MACD Cross, VWAP Band, ORB Pro & more' },
            { emoji: 'A', title: 'AI Trading Desk', desc: 'Gemini-powered analysis and trade suggestions' },
            { emoji: 'R', title: 'Risk Controls', desc: 'Kill switch, daily loss limits, drawdown protection' },
          ].map(c => (
            <div key={c.title} style={{
              padding: '20px', borderRadius: 10, textAlign: 'left',
              border: '1px solid color-mix(in srgb, var(--violet) 10%, transparent)',
              background: 'linear-gradient(135deg, color-mix(in srgb, var(--violet) 4%, transparent), color-mix(in srgb, var(--cyan) 2%, transparent))',
            }}>
              <div style={{
                width: 32, height: 32, borderRadius: 8, display: 'flex', alignItems: 'center',
                justifyContent: 'center', fontSize: 13, fontWeight: 700, marginBottom: 10,
                background: 'var(--gradient-primary)', color: 'var(--text-inverse)',
              }}>{c.emoji}</div>
              <h3 style={{ fontSize: 14, fontWeight: 700, margin: '0 0 4px', color: 'var(--text-inverse)' }}>{c.title}</h3>
              <p style={{ fontSize: 11, lineHeight: 1.5, color: 'var(--text-faint)', margin: 0 }}>{c.desc}</p>
            </div>
          ))}
        </div>

        <div style={{
          marginTop: 80, padding: '32px', borderRadius: 12, width: '100%', maxWidth: 600,
          border: '1px solid color-mix(in srgb, var(--cyan) 10%, transparent)',
          background: 'linear-gradient(135deg, color-mix(in srgb, var(--cyan) 4%, transparent), color-mix(in srgb, var(--violet) 4%, transparent))',
        }}>
          <h2 style={{ fontSize: 18, fontWeight: 700, margin: '0 0 8px', color: 'var(--text-inverse)' }}>
            Get started in 2 minutes
          </h2>
          <p style={{ fontSize: 12, lineHeight: 1.5, color: 'var(--text-sub)', margin: '0 0 20px' }}>
            Create your account, connect your broker, and start trading with automated strategies.
            No credit card required.
          </p>
          <Link href="/live" style={{
            display: 'inline-block', padding: '10px 24px', borderRadius: 6, fontSize: 12,
            fontWeight: 700, letterSpacing: '0.03em', textDecoration: 'none',
            background: 'var(--gradient-primary)',
            color: 'var(--text-inverse)',
          }}>Create Free Account</Link>
        </div>
      </main>

      <footer style={{
        padding: '32px 24px 20px', borderTop: '1px solid color-mix(in srgb, var(--violet) 10%, transparent)',
        fontSize: 11, color: 'var(--text-faint)', fontFamily: 'var(--font-body)',
        display: 'flex', flexDirection: 'column', gap: 24,
      }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 24, maxWidth: 900, width: '100%', margin: '0 auto' }}>
          <div>
            <div style={footerColumnTitle}>Product</div>
            <div style={footerColumn}>
              <Link href="/pricing" style={footerLink}>Pricing</Link>
              <Link href="/live" style={footerLink}>Dashboard</Link>
              <Link href="/auth" style={footerLink}>Open Terminal</Link>
            </div>
          </div>
          <div>
            <div style={footerColumnTitle}>Resources</div>
            <div style={footerColumn}>
              <Link href="/status" style={footerLink}>System Status</Link>
              <Link href="/help" style={footerLink}>Documentation</Link>
              <Link href="/feedback" style={footerLink}>Contact / Feedback</Link>
            </div>
          </div>
          <div>
            <div style={footerColumnTitle}>Legal</div>
            <div style={footerColumn}>
              <Link href="/legal/privacy" style={footerLink}>Privacy Policy</Link>
              <Link href="/legal/terms" style={footerLink}>Terms of Service</Link>
              <Link href="/legal/risk-disclosure" style={footerLink}>Risk Disclosure</Link>
              <Link href="/legal/disclaimer" style={footerLink}>Disclaimer</Link>
            </div>
          </div>
        </div>
        <div style={{ textAlign: 'center', fontSize: 10, fontFamily: 'var(--font-mono)', color: 'var(--text-faint)' }}>
          TradeMetrix Terminal {'\u00A9'} 2026 · Trading involves substantial risk. Trade responsibly.
        </div>
      </footer>
    </div>
  )
}
