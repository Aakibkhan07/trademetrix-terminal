'use client'

import type { CSSProperties, ReactNode } from 'react'

export type BadgeVariant = 'cyan' | 'green' | 'red' | 'amber' | 'violet' | 'sub' | 'yellow'

/**
 * Status pill — emits `t-badge t-badge-{variant}` (design system `styles/components.css`).
 * `yellow` is emitted verbatim for parity (no .t-badge-yellow rule exists; renders as the
 * base pill, identical to current behavior).
 */
export function Badge({ variant, className, style, children }: {
  variant?: BadgeVariant
  className?: string
  style?: CSSProperties
  children: ReactNode
}) {
  return (
    <span className={variant ? `t-badge t-badge-${variant}` : className || 't-badge'} style={style}>
      {children}
    </span>
  )
}

/** Status dot — emits `t-dot t-dot-{variant}` (+ optional pulse). */
export function Dot({ variant = 'green', pulse, style, className }: {
  variant?: 'green' | 'red' | 'cyan' | 'amber' | 'violet' | 'sub'
  pulse?: boolean
  style?: CSSProperties
  className?: string
}) {
  return <span className={[`t-dot t-dot-${variant}`, pulse ? 't-dot-pulse' : '', className].filter(Boolean).join(' ') || undefined} style={style} />
}

/** Interactive chip — emits `t-chip` (+ `t-chip-warn` / `active`). */
export function Chip({ warn, active, className, style, children, ...rest }: {
  warn?: boolean
  active?: boolean
  className?: string
  style?: CSSProperties
  children: ReactNode
} & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      className={['t-chip', warn ? 't-chip-warn' : '', active ? 'active' : '', className].filter(Boolean).join(' ') || undefined}
      style={style}
      {...rest}
    >
      {children}
    </button>
  )
}

const ORDER_STATUS: Record<string, BadgeVariant> = {
  FILLED: 'green',
  REJECTED: 'red',
  CANCELLED: 'amber',
  PENDING: 'cyan',
  OPEN: 'cyan',
  PARTIALLY_FILLED: 'amber',
  EXPIRED: 'sub',
}

/** Order-status pill using the canonical terminal mapping (FILLED/PENDING/OPEN/REJECTED/...). */
export function OrderStatusBadge({ status, style, className }: { status: string; style?: CSSProperties; className?: string }) {
  return <Badge variant={ORDER_STATUS[status] || 'sub'} style={style} className={className}>{status}</Badge>
}

/** Instrument-type pill (OPT → violet, FUT → cyan, else green). */
export function InstrumentTypeBadge({ type, style, className }: { type: string; style?: CSSProperties; className?: string }) {
  const v: BadgeVariant = type === 'OPT' ? 'violet' : type === 'FUT' ? 'cyan' : 'green'
  return <Badge variant={v} style={style} className={className}>{type || 'EQ'}</Badge>
}

const TIER: Record<string, BadgeVariant> = { free: 'green', starter: 'cyan', pro: 'violet', enterprise: 'amber' }

/** Tier/plan pill (free/starter/pro/enterprise). */
export function TierBadge({ tier, style, className }: { tier: string; style?: CSSProperties; className?: string }) {
  return <Badge variant={TIER[tier] || 'sub'} style={style} className={className}>{tier}</Badge>
}

const TIER_PILL: Record<string, (freeText: string, borderMix: string) => { bg: string; text: string; border: string }> = {
  free: (freeText, borderMix) => ({ bg: 'color-mix(in srgb, var(--text-sub) 15%, transparent)', text: freeText, border: `color-mix(in srgb, var(--text-sub) ${borderMix}, transparent)` }),
  starter: (_f, borderMix) => ({ bg: 'color-mix(in srgb, var(--cyan) 15%, transparent)', text: 'var(--cyan)', border: `color-mix(in srgb, var(--cyan) ${borderMix}, transparent)` }),
  pro: (_f, borderMix) => ({ bg: 'color-mix(in srgb, var(--violet) 15%, transparent)', text: 'var(--violet)', border: `color-mix(in srgb, var(--violet) ${borderMix}, transparent)` }),
  enterprise: (_f, borderMix) => ({ bg: 'color-mix(in srgb, var(--red) 15%, transparent)', text: 'var(--red)', border: `color-mix(in srgb, var(--red) ${borderMix}, transparent)` }),
}

/** Inline tier pill (color-mix backgrounds). Free text color and border mix are overridable. */
export function TierPill({ tier, small, freeText = 'var(--text-sub)', borderMix = '20%', style, className }: {
  tier: string
  small?: boolean
  freeText?: string
  borderMix?: string
  style?: CSSProperties
  className?: string
}) {
  const c = TIER_PILL[tier] || TIER_PILL.free
  const pal = c(freeText, borderMix)
  return (
    <span className={className} style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      padding: small ? '1px 6px' : '2px 8px',
      borderRadius: 4, fontSize: small ? 8 : 9, fontWeight: 500,
      background: pal.bg, color: pal.text,
      border: `1px solid ${pal.border}`,
      textTransform: 'capitalize',
      ...style,
    }}>
      {tier}
    </span>
  )
}
