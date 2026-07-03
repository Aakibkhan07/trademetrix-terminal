'use client'

export default function DisclaimerPage() {
  return (
    <div style={{ maxWidth: 700, margin: '0 auto' }}>
      <h1 className="t-page-title">Disclaimer</h1>
      <p className="t-sub" style={{ fontSize: 13, marginBottom: 20 }}>Last updated: July 4, 2026</p>
      <div className="t-panel" style={{ padding: 20, fontSize: 12, lineHeight: 1.7 }}>
        <h3>No Financial Advice</h3>
        <p>TradeMetrix Terminal is a technology platform. We do not provide financial, investment, or trading advice.</p>
        <h3>Risk of Loss</h3>
        <p>Trading stocks, options, and derivatives carries substantial risk. You may lose more than your initial investment.</p>
        <h3>No Guarantees</h3>
        <p>We do not guarantee profitability, strategy performance, or system availability during market hours.</p>
        <h3>Third-Party Services</h3>
        <p>Broker integrations depend on third-party APIs. We are not responsible for broker outages or data delays.</p>
      </div>
    </div>
  )
}
