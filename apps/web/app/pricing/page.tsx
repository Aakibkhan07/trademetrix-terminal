'use client'

import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'
import { useRouter } from 'next/navigation'

interface Plan {
  id: string
  name: string
  tier: string
  price: number
  features: string[]
  most_popular: boolean
}

const PLAN_SAVINGS: Record<string, string> = {
  quarterly: 'Save ₹10,999',
  halfyearly: 'Save ₹23,500',
  yearly: 'Save ₹61,000',
}

export default function PricingPage() {
  const { user, tier: currentTier } = useAuth()
  const router = useRouter()
  const [plans, setPlans] = useState<Plan[]>([])
  const [loading, setLoading] = useState(true)
  const [subscribing, setSubscribing] = useState<string | null>(null)
  const [msg, setMsg] = useState('')

  useEffect(() => {
    api.subscriptions.plans()
      .then(data => setPlans((data as { plans: Plan[] }).plans || []))
      .catch(() => setMsg('Failed to load plans'))
      .finally(() => setLoading(false))
  }, [])

  const handleSubscribe = async (tier: string) => {
    if (!user) { router.push('/auth'); return }
    setSubscribing(tier)
    setMsg('')
    try {
      const data = await api.subscriptions.create(tier) as { short_url: string; key_id: string; subscription_id: string; tier: string }
      if (data.short_url) {
        window.open(data.short_url, '_blank')
        setMsg(`Redirecting to payment for ${data.tier} plan...`)
      }
    } catch (e: any) {
      setMsg(e?.message || 'Failed to create subscription')
    } finally {
      setSubscribing(null)
    }
  }

  const formatPrice = (paise: number) => {
    return new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(paise / 100)
  }

  const tierLabel = (tier: string) => {
    const map: Record<string, string> = { monthly: 'Monthly', quarterly: 'Quarterly', halfyearly: 'Half-Yearly', yearly: 'Yearly' }
    return map[tier] || tier
  }

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: 60 }}>
        <p className="t-faint">Loading plans...</p>
      </div>
    )
  }

  return (
    <div style={{ maxWidth: 1000, margin: '0 auto' }}>
      <div style={{ textAlign: 'center', marginBottom: 40 }}>
        <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 28, fontWeight: 700, margin: '0 0 8px' }}>
          Simple, Transparent Pricing
        </h1>
        <p className="t-faint" style={{ fontSize: 14, margin: 0 }}>
          No hidden fees. No surprises. Cancel anytime. Pick the plan that fits your trading style.
        </p>
      </div>

      {msg && (
        <div style={{
          padding: '10px 14px', borderRadius: 8, marginBottom: 20, fontSize: 13,
          background: 'color-mix(in srgb, var(--violet) 10%, transparent)',
          border: '1px solid color-mix(in srgb, var(--violet) 20%, transparent)',
          color: 'var(--text)',
          textAlign: 'center',
        }}>
          {msg}
        </div>
      )}

      {plans.length === 0 ? (
        <div className="t-panel" style={{ padding: 40, textAlign: 'center' }}>
          <p className="t-faint">No plans available at the moment.</p>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 16 }}>
          {plans.map(plan => {
            const isCurrent = currentTier === plan.tier
            const savings = PLAN_SAVINGS[plan.tier]
            return (
              <div key={plan.id} className="t-panel" style={{
                padding: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column',
                border: plan.most_popular ? '1px solid color-mix(in srgb, var(--violet) 40%, transparent)' : '1px solid color-mix(in srgb, var(--violet) 10%, transparent)',
                position: 'relative',
              }}>
                {plan.most_popular && (
                  <div style={{
                    position: 'absolute', top: 12, right: 12,
                    fontSize: 9, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em',
                    padding: '2px 8px', borderRadius: 4,
                    background: 'var(--gradient-primary)',
                    color: '#fff',
                  }}>
                    Most Popular
                  </div>
                )}
                <div style={{ padding: 24, textAlign: 'center' }}>
                  <h3 style={{ fontSize: 16, fontWeight: 600, margin: '0 0 4px' }}>
                    {plan.name}
                  </h3>
                  <div style={{ fontSize: 28, fontWeight: 700, margin: '12px 0 4px', fontFamily: 'var(--font-mono)' }}>
                    {formatPrice(plan.price)}
                  </div>
                  <div className="t-faint" style={{ fontSize: 11 }}>
                    {plan.tier === 'monthly' ? 'per month' : plan.tier === 'quarterly' ? 'per quarter' : plan.tier === 'halfyearly' ? 'per 6 months' : 'per year'}
                  </div>
                  {savings && (
                    <div style={{
                      marginTop: 6, padding: '2px 8px', borderRadius: 4, display: 'inline-block',
                      fontSize: 9, fontWeight: 600,
                      background: 'color-mix(in srgb, var(--green) 15%, transparent)',
                      color: 'var(--green)',
                    }}>
                      {savings}
                    </div>
                  )}
                </div>
                <div style={{ padding: '0 24px', flex: 1 }}>
                  <ul style={{
                    listStyle: 'none', padding: 0, margin: 0,
                    display: 'flex', flexDirection: 'column', gap: 8,
                  }}>
                    {(plan.features || []).map((f, i) => (
                      <li key={i} style={{
                        fontSize: 11, color: 'var(--text-sub)',
                        display: 'flex', alignItems: 'center', gap: 6,
                      }}>
                        <span style={{ color: 'var(--green)', fontSize: 12, flexShrink: 0 }}>✓</span>
                        {f}
                      </li>
                    ))}
                  </ul>
                </div>
                <div style={{ padding: 24 }}>
                  {isCurrent ? (
                    <button className="t-btn t-btn-sm" style={{ width: '100%', cursor: 'default' }} disabled>
                      Current Plan
                    </button>
                  ) : (
                    <button
                      className={`t-btn t-btn-sm ${plan.most_popular ? 't-btn-primary' : ''}`}
                      style={{ width: '100%' }}
                      onClick={() => handleSubscribe(plan.tier)}
                      disabled={subscribing === plan.tier}
                    >
                      {subscribing === plan.tier ? 'Processing...' : `Subscribe to ${tierLabel(plan.tier)}`}
                    </button>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Enterprise Section */}
      <div className="t-panel" style={{
        marginTop: 24, padding: 0, overflow: 'hidden',
        border: '1px solid color-mix(in srgb, var(--amber) 30%, transparent)',
      }}>
        <div style={{ padding: 24, textAlign: 'center' }}>
          <h3 style={{ fontSize: 16, fontWeight: 600, margin: '0 0 4px' }}>Enterprise — For Institutions</h3>
          <p className="t-faint" style={{ fontSize: 12, margin: '0 0 16px' }}>
            Custom plan for prop desks &amp; institutions. Dedicated infrastructure, colocated servers, white-label dashboard, custom strategy development, and dedicated support team.
          </p>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, justifyContent: 'center', marginBottom: 16 }}>
            {['Unlimited Strategies', 'Sub-5ms Latency', 'Colocated Servers', 'White-Label UI', 'Custom Indicators', 'SLA Guarantee', 'Dedicated Engineer', 'Bulk Pricing'].map(f => (
              <span key={f} style={{
                fontSize: 9, padding: '2px 8px', borderRadius: 4,
                background: 'color-mix(in srgb, var(--amber) 12%, transparent)',
                border: '1px solid color-mix(in srgb, var(--amber) 20%, transparent)',
                color: 'var(--amber)',
              }}>
                {f}
              </span>
            ))}
          </div>
          <p className="t-faint" style={{ fontSize: 11, margin: '0 0 12px' }}>
            Starting at ₹5,00,000/year · Custom pricing available
          </p>
          <a href="mailto:info@trademetrix.tech" className="t-btn t-btn-sm" style={{ fontSize: 10 }}>
            Contact Sales
          </a>
        </div>
      </div>

      <div className="t-panel" style={{ marginTop: 16, padding: 16, textAlign: 'center' }}>
        <p className="t-faint" style={{ margin: 0, fontSize: 11 }}>
          All plans include a 1-day free trial. Cancel anytime. Payments processed securely via Razorpay.
        </p>
      </div>
    </div>
  )
}
