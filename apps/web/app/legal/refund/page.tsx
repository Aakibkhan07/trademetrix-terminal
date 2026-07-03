'use client'

export default function RefundPage() {
  return (
    <div style={{ maxWidth: 700, margin: '0 auto' }}>
      <h1 className="t-page-title">Refund Policy</h1>
      <p className="t-sub" style={{ fontSize: 13, marginBottom: 20 }}>Last updated: July 4, 2026</p>
      <div className="t-panel" style={{ padding: 20, fontSize: 12, lineHeight: 1.7 }}>
        <h3>Free Trial</h3>
        <p>Starter and Pro plans include a 14-day free trial. You will not be charged during the trial period.</p>
        <h3>Cancellation</h3>
        <p>Cancel anytime from your account settings. Your access continues until the end of the current billing period.</p>
        <h3>Refunds</h3>
        <p>We do not offer pro-rated refunds for partial billing periods. If you cancel mid-cycle, you retain access until the next billing date.</p>
        <h3>Enterprise</h3>
        <p>Enterprise plan refunds are handled per the terms of your service agreement.</p>
        <h3>Contact</h3>
        <p>For billing inquiries: billing@trademetrix.tech</p>
      </div>
    </div>
  )
}
