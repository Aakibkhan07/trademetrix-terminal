export default function Logo({ size = 28 }: { size?: number }) {
  return (
    <img src="/logo.jpg" alt="TradeMetrix" width={size} height={size} style={{ borderRadius: 6, objectFit: 'contain' }} />
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
