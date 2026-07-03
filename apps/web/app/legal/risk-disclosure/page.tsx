'use client'

export default function RiskDisclosurePage() {
  return (
    <div style={{ maxWidth: 700, margin: '0 auto' }}>
      <h1 className="t-page-title">Risk Disclosure</h1>
      <p className="t-sub" style={{ fontSize: 13, marginBottom: 20 }}>Last updated: July 4, 2026</p>
      <div className="t-panel" style={{ padding: 20, fontSize: 12, lineHeight: 1.7 }}>
        <h3>Trading Risks</h3>
        <p>Financial trading involves significant risk. You should only trade with capital you can afford to lose.</p>
        <h3>Automated Trading</h3>
        <p>Automated strategies may behave unexpectedly during volatile markets. Always monitor live trading.</p>
        <h3>Leverage</h3>
        <p>Leverage amplifies both gains and losses. Ensure you understand margin requirements before trading.</p>
        <h3>Technical Risks</h3>
        <p>System failures, network latency, and data feed interruptions can affect trading execution.</p>
        <h3>Regulatory</h3>
        <p>It is your responsibility to ensure compliance with applicable laws and regulations in your jurisdiction.</p>
      </div>
    </div>
  )
}
