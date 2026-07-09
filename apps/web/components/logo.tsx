export default function Logo({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none">
      <rect x="2" y="2" width="28" height="28" rx="6" stroke="url(--gradient-primary)" strokeWidth="1.5" />
      <text x="16" y="20" textAnchor="middle" fontSize="13" fontWeight="700" fill="var(--cyan)" fontFamily="var(--font-display)">
        TM
      </text>
      <path d="M6 24 L12 16 L18 18 L26 8" stroke="var(--green)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="26" cy="8" r="1.5" fill="var(--green)" />
    </svg>
  )
}

export function LogoText({ size = 18 }: { size?: number }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
      <Logo size={size} />
      <span style={{
        fontFamily: 'var(--font-display)',
        fontSize: size - 4,
        fontWeight: 700,
        background: 'var(--gradient-primary)',
        WebkitBackgroundClip: 'text',
        WebkitTextFillColor: 'transparent',
        letterSpacing: '-0.02em',
      }}>
        TradeMetrix
      </span>
    </span>
  )
}
