'use client'

import { useState, useEffect } from 'react'
import { useAuth } from '@/lib/auth-context'
import { useToast } from '@/lib/use-toast'
import { useRouter } from 'next/navigation'
import { api } from '@/lib/api'

const PLANS = [
  { tier: 'free', name: 'Free', price: { monthly: 0, yearly: 0 }, desc: 'Get started with basic trading tools', features: ['Paper trading', 'Basic market data', '1 strategy', 'Standard support'], cta: 'Get Started', popular: false },
  { tier: 'starter', name: 'Starter', price: { monthly: 999, yearly: 9999 }, desc: 'For active traders', features: ['All Free features', 'Live trading', '5 strategies', 'Advanced market data', 'Email support'], cta: 'Start Free Trial', popular: false },
  { tier: 'pro', name: 'Pro', price: { monthly: 2499, yearly: 24999 }, desc: 'For professional traders', features: ['All Starter features', 'Unlimited strategies', 'Real-time data streams', 'Strategy backtesting', 'Priority support', 'API access'], cta: 'Start Free Trial', popular: true },
  { tier: 'enterprise', name: 'Enterprise', price: { monthly: 9999, yearly: 99999 }, desc: 'For institutions and teams', features: ['All Pro features', 'Dedicated infrastructure', 'Custom integrations', 'SLA guarantee', 'Account manager', 'Bulk user management'], cta: 'Contact Sales', popular: false },
]

interface PlanInfo {
  id: string; name: string; tier: string; price: number
  features: string[]; most_popular: boolean
}

const FAQS = [
  { q: 'Can I switch plans anytime?', a: 'Yes, you can upgrade or downgrade at any time. Changes take effect immediately.' },
  { q: 'Is there a free trial?', a: 'All subscription plans include a 1-day free trial. No card required upfront.' },
  { q: 'What payment methods are accepted?', a: 'We accept Razorpay (UPI, cards, netbanking).' },
  { q: 'Can I cancel anytime?', a: 'Yes, cancel anytime. Your access continues until the end of the billing period.' },
]

function PriceDisplay({ amount }: { amount: number }) {
  if (amount === 0) return <span style={{ fontSize: 32, fontWeight: 700, fontFamily: 'var(--font-mono)' }}>Free</span>
  return (
    <span>
      <span style={{ fontSize: 14, color: 'var(--text-faint)' }}>₹</span>
      <span style={{ fontSize: 32, fontWeight: 700, fontFamily: 'var(--font-mono)' }}>{amount.toLocaleString('en-IN')}</span>
    </span>
  )
}

export default function PricingPage() {
  const [yearly, setYearly] = useState(false)
  const { user } = useAuth()
  const { toast } = useToast()
  const router = useRouter()
  const [subPlans, setSubPlans] = useState<PlanInfo[]>([])
  const [subscribing, setSubscribing] = useState<string | null>(null)

  useEffect(() => {
    api.subscriptions.plans().then(d => setSubPlans(d.plans || [])).catch(() => {})
  }, [])

  const handleCta = (plan: typeof PLANS[0]) => {
    if (!user) { router.push('/auth?redirect=/pricing'); return }
    if (plan.tier === 'free') { router.push('/dashboard'); return }
    if (plan.tier === 'enterprise') { toast('info', 'Contact sales: enterprise@trademetrix.tech'); return }
    toast('info', `${plan.name} plan — payment integration coming soon`)
  }

  const handleSubscribe = async (planId: string) => {
    if (!user) { router.push('/auth?redirect=/pricing'); return }
    setSubscribing(planId)
    try {
      const res = await api.subscriptions.create(planId)
      const script = document.createElement('script')
      script.src = 'https://checkout.razorpay.com/v1/checkout.js'
      script.onload = () => {
        const rzp = new (window as any).Razorpay({
          key_id: res.key_id,
          subscription_id: res.subscription_id,
          callback_url: `${window.location.origin}/pricing?success=true`,
          redirect: true,
        })
        rzp.open()
      }
      document.body.appendChild(script)
    } catch (e: unknown) {
      toast('error', e instanceof Error ? e.message : 'Subscription failed')
    } finally {
      setSubscribing(null)
    }
  }

  return (
    <div style={{ maxWidth: 1000, margin: '0 auto', padding: '24px 16px' }}>
      {/* Legacy Plans */}
      <div style={{ textAlign: 'center', marginBottom: 32 }}>
        <h1 className="t-page-title" style={{ margin: '0 0 8px' }}>Pricing</h1>
        <p className="t-sub" style={{ fontSize: 13 }}>Choose the plan that fits your trading needs</p>
        <div style={{ display: 'inline-flex', alignItems: 'center', gap: 10, marginTop: 16, padding: '4px', background: 'var(--panel)', borderRadius: 8 }}>
          <button onClick={() => setYearly(false)} style={{ padding: '6px 14px', borderRadius: 6, background: !yearly ? 'var(--violet)' : 'transparent', color: !yearly ? '#fff' : 'var(--text)', border: 'none', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit', fontWeight: 600 }}>Monthly</button>
          <button onClick={() => setYearly(true)} style={{ padding: '6px 14px', borderRadius: 6, background: yearly ? 'var(--violet)' : 'transparent', color: yearly ? '#fff' : 'var(--text)', border: 'none', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit', fontWeight: 600 }}>Yearly <span style={{ fontSize: 9, opacity: 0.8 }}>(save ~15%)</span></button>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12, marginBottom: 40 }}>
        {PLANS.map(plan => (
          <div key={plan.tier} className="t-panel" style={{ padding: 0, overflow: 'hidden', position: 'relative', border: plan.popular ? '1px solid rgba(139,92,246,0.4)' : '1px solid var(--border)' }}>
            {plan.popular && <div style={{ background: 'var(--violet)', color: '#fff', fontSize: 9, fontWeight: 700, textAlign: 'center', padding: '3px 0', letterSpacing: '0.05em' }}>MOST POPULAR</div>}
            <div style={{ padding: 20 }}>
              <h2 style={{ margin: '0 0 4px', fontSize: 16, fontWeight: 700 }}>{plan.name}</h2>
              <p style={{ margin: '0 0 16px', fontSize: 11, color: 'var(--text-faint)' }}>{plan.desc}</p>
              <div style={{ marginBottom: 16 }}>
                <PriceDisplay amount={yearly ? plan.price.yearly : plan.price.monthly} />
                {plan.price.monthly > 0 && <span style={{ fontSize: 11, color: 'var(--text-faint)', marginLeft: 4 }}>/{yearly ? 'yr' : 'mo'}</span>}
              </div>
              <button className="t-btn" onClick={() => handleCta(plan)} style={{ width: '100%', fontSize: 11, padding: '8px', background: plan.popular ? 'var(--violet)' : 'var(--panel)', color: plan.popular ? '#fff' : 'var(--text)', border: plan.popular ? 'none' : '1px solid var(--border)', marginBottom: 16 }}>{plan.cta}</button>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {plan.features.map((f, i) => <div key={i} style={{ fontSize: 11, color: 'var(--text-sub)', display: 'flex', alignItems: 'center', gap: 6 }}><span style={{ color: '#22c55e', fontSize: 12 }}>&#10003;</span>{f}</div>)}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Subscription Plans */}
      <div style={{ borderTop: '1px solid var(--border)', paddingTop: 32, marginBottom: 40 }}>
        <h2 style={{ fontFamily: 'Outfit', fontSize: 18, textAlign: 'center', margin: '0 0 8px', color: '#f0f0f5' }}>Subscription Plans</h2>
        <p className="t-sub" style={{ fontSize: 12, textAlign: 'center', margin: '0 auto 20px', maxWidth: 500 }}>
          Recurring billing where your plan IS your tier. 1-day free trial, no card required upfront.
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12 }}>
          {subPlans.map(p => (
            <div key={p.id} className="t-panel" style={{ padding: 0, overflow: 'hidden', position: 'relative', border: p.most_popular ? '1px solid rgba(34,211,238,0.4)' : '1px solid var(--border)' }}>
              {p.most_popular && <div style={{ background: 'var(--cyan)', color: '#08090c', fontSize: 9, fontWeight: 700, textAlign: 'center', padding: '3px 0', letterSpacing: '0.05em' }}>MOST POPULAR</div>}
              <div style={{ padding: 20 }}>
                <h2 style={{ margin: '0 0 4px', fontSize: 15, fontWeight: 700 }}>{p.name}</h2>
                <div style={{ marginBottom: 12 }}>
                  <span style={{ fontSize: 11, color: 'var(--text-faint)' }}>&#x20B9; </span>
                  <span style={{ fontSize: 28, fontWeight: 700, fontFamily: 'var(--font-mono)' }}>{p.price.toLocaleString('en-IN')}</span>
                  <span style={{ fontSize: 11, color: 'var(--text-faint)', marginLeft: 4 }}>/{p.id === 'yearly' ? 'yr' : p.id === 'halfyearly' ? '6mo' : p.id === 'quarterly' ? '3mo' : 'mo'}</span>
                </div>
                <button className="t-btn" onClick={() => handleSubscribe(p.id)} disabled={subscribing === p.id} style={{ width: '100%', fontSize: 11, padding: '8px', background: p.most_popular ? 'var(--cyan)' : 'var(--panel)', color: p.most_popular ? '#08090c' : 'var(--text)', border: p.most_popular ? 'none' : '1px solid var(--border)', marginBottom: 12, fontWeight: 600 }}>
                  {subscribing === p.id ? 'Opening...' : 'Subscribe'}
                </button>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                  {p.features.map((f, i) => <div key={i} style={{ fontSize: 11, color: 'var(--text-sub)', display: 'flex', alignItems: 'center', gap: 6 }}><span style={{ color: '#22d3ee', fontSize: 12 }}>&#10003;</span>{f}</div>)}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* FAQ */}
      <h2 style={{ fontFamily: 'Outfit', fontSize: 16, textAlign: 'center', margin: '0 0 20px', color: '#f0f0f5' }}>Frequently Asked Questions</h2>
      <div style={{ maxWidth: 600, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 8 }}>
        {FAQS.map((faq, i) => (
          <details key={i} className="t-panel" style={{ padding: 14, cursor: 'pointer' }}>
            <summary style={{ fontSize: 13, fontWeight: 600, cursor: 'pointer' }}>{faq.q}</summary>
            <p style={{ fontSize: 12, color: 'var(--text-sub)', margin: '8px 0 0' }}>{faq.a}</p>
          </details>
        ))}
      </div>
    </div>
  )
}
