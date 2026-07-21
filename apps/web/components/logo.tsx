export default function Logo({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="1.5" y="1.5" width="29" height="29" rx="7" stroke="url(--gradient-primary)" strokeWidth="1.8" />
      <path d="M9 10.5h14M16 10.5v12" stroke="var(--cyan)" strokeWidth="2.4" strokeLinecap="round" />
      <path d="M15 16l2.5 3.5 2.5-3.5" stroke="var(--cyan)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M6 24l4-5 5 2 7-9" stroke="var(--green)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="22" cy="12" r="1.5" fill="var(--green)" />
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
