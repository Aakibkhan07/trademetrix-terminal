export default function Logo({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="logo-bg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#8b5cf6"/>
          <stop offset="100%" stopColor="#22d3ee"/>
        </linearGradient>
        <linearGradient id="logo-line" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#a78bfa"/>
          <stop offset="100%" stopColor="#2dd4bf"/>
        </linearGradient>
      </defs>
      <rect x="1" y="1" width="30" height="30" rx="8" fill="url(#logo-bg)" opacity="0.12"/>
      <rect x="1" y="1" width="30" height="30" rx="8" stroke="url(#logo-bg)" strokeWidth="1.5"/>
      <rect x="9.5" y="8" width="3" height="10" rx="0.8" fill="url(#logo-line)" opacity="0.7"/>
      <rect x="14.5" y="6" width="3" height="16" rx="0.8" fill="url(#logo-line)"/>
      <rect x="19.5" y="11" width="3" height="8" rx="0.8" fill="url(#logo-line)" opacity="0.7"/>
      <path d="M7 23l4-5 5 2 7-9" stroke="#2dd4bf" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" opacity="0.8"/>
      <circle cx="23" cy="11" r="2" fill="#2dd4bf" opacity="0.8"/>
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
