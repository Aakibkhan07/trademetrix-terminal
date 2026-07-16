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

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: 60 }}>
        <p className="t-faint">Loading plans...</p>
      </div>
    )
  }

  return (
    <div style={{ maxWidth: 800, margin: '0 auto' }}>
      <div style={{ textAlign: 'center', marginBottom: 40 }}>
        <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 28, fontWeight: 700, margin: '0 0 8px' }}>
          Choose Your Plan
        </h1>
        <p className="t-faint" style={{ fontSize: 14, margin: 0 }}>
          Unlock advanced features and higher limits
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
        <div className="t-grid" style={{
          gridTemplateColumns: `repeat(${Math.min(plans.length, 4)}, 1fr)`,
          gap: 16,
        }}>
          {plans.map(plan => {
            const isCurrent = currentTier === plan.tier
            return (
              <div key={plan.id} className="t-panel" style={{
                padding: 0, overflow: 'hidden',
                border: plan.most_popular ? '1px solid color-mix(in srgb, var(--violet) 40%, transparent)' : undefined,
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
                    Popular
                  </div>
                )}
                <div style={{ padding: 20, textAlign: 'center' }}>
                  <h3 style={{ fontFamily: 'var(--font-display)', fontSize: 16, fontWeight: 600, margin: '0 0 4px' }}>
                    {plan.name}
                  </h3>
                  <div style={{ fontSize: 28, fontWeight: 700, margin: '12px 0 4px', fontFamily: 'var(--font-mono)' }}>
                    {formatPrice(plan.price)}
                  </div>
                  <div className="t-faint" style={{ fontSize: 11 }}>one-time payment</div>
                </div>
                <div style={{ padding: '0 20px 20px' }}>
                  <ul style={{
                    listStyle: 'none', padding: 0, margin: 0,
                    display: 'flex', flexDirection: 'column', gap: 6,
                  }}>
                    {(plan.features || []).map((f, i) => (
                      <li key={i} style={{
                        fontSize: 11, color: 'var(--text-sub)',
                        display: 'flex', alignItems: 'center', gap: 6,
                      }}>
                        <span style={{ color: 'var(--green)', fontSize: 12 }}>✓</span>
                        {f}
                      </li>
                    ))}
                  </ul>
                </div>
                <div style={{ padding: '0 20px 20px' }}>
                  {isCurrent ? (
                    <button className="t-btn t-btn-sm" style={{ width: '100%' }} disabled>
                      Current Plan
                    </button>
                  ) : (
                    <button
                      className={`t-btn t-btn-sm ${plan.most_popular ? 't-btn-primary' : 't-btn-ghost'}`}
                      style={{ width: '100%' }}
                      onClick={() => handleSubscribe(plan.tier)}
                      disabled={subscribing === plan.tier}
                    >
                      {subscribing === plan.tier ? 'Processing...' : 'Subscribe'}
                    </button>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}

      <div className="t-panel" style={{ marginTop: 24, padding: 16, textAlign: 'center' }}>
        <p className="t-faint" style={{ margin: 0, fontSize: 11 }}>
          All plans include a 1-day free trial. Cancel anytime. Payments processed securely via Razorpay.
        </p>
      </div>
    </div>
  )
}
