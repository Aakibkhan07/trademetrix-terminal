
export default function TermsPage() {
  return (
    <div style={{ maxWidth: 700, margin: '0 auto' }}>
      <h1 className="t-page-title">Terms of Service</h1>
      <p className="t-sub" style={{ fontSize: 13, marginBottom: 20 }}>Last updated: July 4, 2026</p>
      <div className="t-panel" style={{ padding: 20, fontSize: 12, lineHeight: 1.7 }}>
        <h3>Acceptance</h3>
        <p>By using TradeMetrix Terminal, you agree to these terms. If you do not agree, do not use the platform.</p>
        <h3>Eligibility</h3>
        <p>You must be 18+ and have the legal capacity to trade financial instruments in your jurisdiction.</p>
        <h3>Account</h3>
        <p>You are responsible for maintaining account security. Notify us immediately of unauthorized access.</p>
        <h3>Prohibited Use</h3>
        <p>Do not use the platform for illegal activities, market manipulation, or to breach exchange rules.</p>
        <h3>Limitation of Liability</h3>
        <p>TradeMetrix is a tool. Trading involves risk. We are not liable for trading losses or decisions.</p>
      </div>
    </div>
  )
}
