import Link from 'next/link'

export default function LandingPage() {
  return (
    <div style={{
      minHeight: '100vh', background: '#0a0a0f', color: '#c0c0d0',
      fontFamily: 'var(--font-body)',
      display: 'flex', flexDirection: 'column',
    }}>
      <header style={{
        height: 56, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '0 24px', borderBottom: '1px solid rgba(139,92,246,0.15)',
      }}>
        <Link href="/" style={{
          display: 'flex', alignItems: 'center', gap: 8, textDecoration: 'none',
          fontFamily: 'Outfit, sans-serif', fontSize: 16, fontWeight: 700,
          background: 'linear-gradient(135deg, #00e5ff, #7c5cfc)',
          WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent',
        }}>
          TradeMetrix
        </Link>
        <nav style={{ display: 'flex', gap: 16, alignItems: 'center' }}>
          <Link href="/portal" style={{
            fontSize: 12, fontWeight: 600, color: '#8888a0', textDecoration: 'none',
            letterSpacing: '0.03em', transition: 'color 0.15s',
          }}>Client Portal</Link>
          <Link href="/auth" style={{
            fontSize: 12, fontWeight: 600, color: '#8888a0', textDecoration: 'none',
            letterSpacing: '0.03em', transition: 'color 0.15s',
          }}>Sign In</Link>
          <Link href="/portal" style={{
            fontSize: 11, fontWeight: 700, letterSpacing: '0.04em',
            padding: '8px 18px', borderRadius: 6, textDecoration: 'none',
            background: 'linear-gradient(135deg, #00e5ff, #7c5cfc)',
            color: '#000', transition: 'opacity 0.15s',
          }}>Get Started</Link>
        </nav>
      </header>

      <main style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '60px 24px', textAlign: 'center' }}>
        <div style={{ maxWidth: 720 }}>
          <div style={{
            display: 'inline-block', padding: '4px 12px', borderRadius: 20, fontSize: 10,
            fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase',
            background: 'rgba(0,229,255,0.08)', color: '#00e5ff',
            border: '1px solid rgba(0,229,255,0.12)', marginBottom: 24,
          }}>Multi-Broker Algorithmic Trading Platform</div>

          <h1 style={{
            fontSize: 44, fontWeight: 700, lineHeight: 1.15, margin: '0 0 16px',
            fontFamily: 'Outfit, sans-serif', color: '#fff',
          }}>
            Trade across{' '}
            <span style={{ background: 'linear-gradient(135deg, #00e5ff, #7c5cfc)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
              10+ brokers
            </span>
            {' '}with one terminal
          </h1>

          <p style={{ fontSize: 15, lineHeight: 1.6, color: '#8888a0', maxWidth: 520, margin: '0 auto 32px' }}>
            Automated trading strategies, real-time market data, AI-powered analytics,
            and risk management — all in one place. Connect your broker and start trading.
          </p>

          <div style={{ display: 'flex', gap: 12, justifyContent: 'center', flexWrap: 'wrap' }}>
            <Link href="/portal" style={{
              padding: '12px 28px', borderRadius: 8, fontSize: 13, fontWeight: 700,
              letterSpacing: '0.03em', textDecoration: 'none',
              background: 'linear-gradient(135deg, #00e5ff, #7c5cfc)',
              color: '#000', transition: 'opacity 0.15s',
            }}>Launch Client Portal</Link>
            <Link href="/auth" style={{
              padding: '12px 28px', borderRadius: 8, fontSize: 13, fontWeight: 600,
              letterSpacing: '0.03em', textDecoration: 'none',
              border: '1px solid rgba(139,92,246,0.3)', color: '#c0c0d0',
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
              border: '1px solid rgba(139,92,246,0.1)',
              background: 'linear-gradient(135deg, rgba(139,92,246,0.04), rgba(0,229,255,0.02))',
            }}>
              <div style={{
                width: 32, height: 32, borderRadius: 8, display: 'flex', alignItems: 'center',
                justifyContent: 'center', fontSize: 13, fontWeight: 700, marginBottom: 10,
                background: 'var(--gradient-primary)', color: '#000',
              }}>{c.emoji}</div>
              <h3 style={{ fontSize: 14, fontWeight: 700, margin: '0 0 4px', color: '#fff' }}>{c.title}</h3>
              <p style={{ fontSize: 11, lineHeight: 1.5, color: '#777790', margin: 0 }}>{c.desc}</p>
            </div>
          ))}
        </div>

        <div style={{
          marginTop: 80, padding: '32px', borderRadius: 12, width: '100%', maxWidth: 600,
          border: '1px solid rgba(0,229,255,0.1)',
          background: 'linear-gradient(135deg, rgba(0,229,255,0.04), rgba(124,92,252,0.04))',
        }}>
          <h2 style={{ fontSize: 18, fontWeight: 700, margin: '0 0 8px', color: '#fff' }}>
            Get started in 2 minutes
          </h2>
          <p style={{ fontSize: 12, lineHeight: 1.5, color: '#8888a0', margin: '0 0 20px' }}>
            Create your account, connect your broker, and start trading with automated strategies.
            No credit card required.
          </p>
          <Link href="/portal" style={{
            display: 'inline-block', padding: '10px 24px', borderRadius: 6, fontSize: 12,
            fontWeight: 700, letterSpacing: '0.03em', textDecoration: 'none',
            background: 'linear-gradient(135deg, #00e5ff, #7c5cfc)',
            color: '#000',
          }}>Create Free Account</Link>
        </div>
      </main>

      <footer style={{
        height: 48, display: 'flex', alignItems: 'center', justifyContent: 'center',
        borderTop: '1px solid rgba(139,92,246,0.1)', fontSize: 10, color: '#555570',
        fontFamily: 'var(--font-mono)',
      }}>
        TradeMetrix Terminal &copy; 2026
      </footer>
    </div>
  )
}
