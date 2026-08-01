'use client'

import { useAuth } from './auth-context'
import type { ReactNode } from 'react'

export type Tier = 'free' | 'starter' | 'pro' | 'enterprise'

export interface FeatureDef {
  key: string
  label: string
  description: string
  tiers: Tier[]
}

export const TIER_ORDER: Tier[] = ['free', 'starter', 'pro', 'enterprise']

export const FEATURES: FeatureDef[] = [
  { key: 'strategies', label: 'Active Strategies', description: 'Number of concurrent strategies', tiers: ['free', 'starter', 'pro', 'enterprise'] },
  { key: 'strategies_unlimited', label: 'Unlimited Strategies', description: 'Unlimited concurrent strategies', tiers: ['enterprise'] },
  { key: 'realtime_data', label: 'Real-time Market Data', description: 'Live market data feeds', tiers: ['starter', 'pro', 'enterprise'] },
  { key: 'backtesting', label: 'Backtesting Engine', description: 'Historical strategy backtesting', tiers: ['pro', 'enterprise'] },
  { key: 'multi_broker', label: 'Multi-Broker Support', description: 'Connect multiple brokers', tiers: ['pro', 'enterprise'] },
  { key: 'alerts', label: 'Price Alerts', description: 'Automated price alerts', tiers: ['free', 'starter', 'pro', 'enterprise'] },
  { key: 'ai_desk', label: 'AI Trading Desk', description: 'AI-powered trading assistant', tiers: ['starter', 'pro', 'enterprise'] },
  { key: 'journal', label: 'Trade Journal', description: 'Automated trade journaling', tiers: ['free', 'starter', 'pro', 'enterprise'] },
  { key: 'admin', label: 'Admin Dashboard', description: 'System administration', tiers: ['enterprise'] },
  { key: 'api_access', label: 'API Access', description: 'Programmatic API access', tiers: ['pro', 'enterprise'] },
  { key: 'priority_support', label: 'Priority Support', description: 'Priority customer support', tiers: ['enterprise'] },
  { key: 'white_label', label: 'White Label', description: 'Custom branding', tiers: ['enterprise'] },
  { key: 'risk_controls', label: 'Risk Controls', description: 'Advanced risk management', tiers: ['free', 'starter', 'pro', 'enterprise'] },
]

export const TIER_LIMITS: Record<Tier, { strategies: number; label: string; price: number }> = {
  free: { strategies: 1, label: 'Free', price: 0 },
  starter: { strategies: 3, label: 'Starter', price: 999 },
  pro: { strategies: 10, label: 'Pro', price: 2999 },
  enterprise: { strategies: 99, label: 'Enterprise', price: 0 },
}

export const TIER_COLORS: Record<Tier, { color: string; bg: string }> = {
  free: { color: '#9aa0a6', bg: 'rgba(154,160,166,0.12)' },
  starter: { color: '#00e5ff', bg: 'rgba(0,229,255,0.12)' },
  pro: { color: '#7c5cfc', bg: 'rgba(124,92,252,0.12)' },
  enterprise: { color: '#ffd600', bg: 'rgba(255,214,0,0.12)' },
}

export function hasFeature(tier: string, featureKey: string): boolean {
  const feature = FEATURES.find(f => f.key === featureKey)
  if (!feature) return false
  return feature.tiers.includes(tier as Tier)
}

export function useFeature(featureKey: string): boolean {
  const { tier } = useAuth()
  return hasFeature(tier, featureKey)
}

export function useTier(): Tier {
  const { tier } = useAuth()
  return (tier as Tier) || 'free'
}

export function FeatureGate({ feature, fallback, children }: { feature: string; fallback?: ReactNode; children: ReactNode }) {
  const allowed = useFeature(feature)
  if (allowed) return <>{children}</>
  if (fallback) return <>{fallback}</>
  return null
}

export function UpgradePrompt({ feature, current }: { feature: string; current?: Tier }) {
  const { tier } = useAuth()
  const ft = FEATURES.find(f => f.key === feature)
  if (!ft) return null
  const needed = ft.tiers[0]
  if (hasFeature(tier, feature)) return null
  const currIdx = TIER_ORDER.indexOf(tier as Tier)
  const needIdx = TIER_ORDER.indexOf(needed)
  if (currIdx >= needIdx) return null

  return (
    <div className="upgrade-prompt">
      <div className="upgrade-prompt-content">
        <span className="upgrade-prompt-icon">↑</span>
        <span className="upgrade-prompt-text">
          <strong>{ft.label}</strong> requires <span className={`t-badge-${needed}`}>{needed}</span> plan.
          {feature === 'backtesting' && ' Upgrade to Pro to run backtests.'}
          {feature === 'realtime_data' && ' Upgrade to Starter for real-time data.'}
          {feature === 'multi_broker' && ' Upgrade to Pro to connect multiple brokers.'}
          {feature === 'ai_desk' && ' Upgrade to Starter for AI trading assistant.'}
          {feature === 'api_access' && ' Upgrade to Pro for API access.'}
        </span>
        <a href="/pricing" className="t-btn t-btn-primary t-btn-sm">Upgrade</a>
      </div>
    </div>
  )
}
