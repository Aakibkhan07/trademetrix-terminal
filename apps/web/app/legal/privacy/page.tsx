'use client'

export default function PrivacyPage() {
  return (
    <div style={{ maxWidth: 700, margin: '0 auto' }}>
      <h1 className="t-page-title">Privacy Policy</h1>
      <p className="t-sub" style={{ fontSize: 13, marginBottom: 20 }}>Last updated: July 4, 2026</p>
      <div className="t-panel" style={{ padding: 20, fontSize: 12, lineHeight: 1.7 }}>
        <p>TradeMetrix Terminal (&quot;we&quot;, &quot;our&quot;, or &quot;us&quot;) is committed to protecting your privacy.</p>
        <h3>Information We Collect</h3>
        <p>We collect information you provide: email address, name, phone number, and broker connection details. We collect usage data: trading activity, strategy configurations, and platform interactions.</p>
        <h3>How We Use Your Data</h3>
        <p>To provide and improve trading services, process transactions, send notifications, and comply with legal obligations.</p>
        <h3>Data Sharing</h3>
        <p>We do not sell your personal data. We may share with service providers (cloud hosting, analytics) who are bound by data processing agreements.</p>
        <h3>Security</h3>
        <p>We use encryption at rest and in transit. Broker credentials are encrypted with Fernet symmetric encryption.</p>
        <h3>Your Rights</h3>
        <p>You can access, correct, or delete your data by contacting support@trademetrix.tech.</p>
      </div>
    </div>
  )
}
