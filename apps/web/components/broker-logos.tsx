export function BrokerLogo({ broker, size = 32 }: { broker: string; size?: number }) {
  const props = { width: size, height: size, viewBox: "0 0 32 32", fill: "none", xmlns: "http://www.w3.org/2000/svg" }
  const s = { display: "inline-block", verticalAlign: "middle", lineHeight: 0 } as React.CSSProperties

  switch (broker) {
    case "zerodha":
      return <svg {...props} style={s}><rect x="1" y="1" width="30" height="30" rx="8" fill="#387ED1"/><path d="M22 22V8l-10 16h6V8" stroke="#fff" strokeWidth="2.8" strokeLinecap="round" strokeLinejoin="round"/></svg>
    case "angelone":
      return <svg {...props} style={s}><rect x="1" y="1" width="30" height="30" rx="7" fill="#E61E2A"/><path d="M8 24c0-8 16-8 16 0" stroke="#fff" strokeWidth="2.5" strokeLinecap="round" fill="none"/><path d="M12 20c0-6 8-6 8 0" stroke="#fff" strokeWidth="2" strokeLinecap="round" fill="none"/><circle cx="16" cy="10" r="3.5" fill="#fff"/></svg>
    case "upstox":
      return <svg {...props} style={s}><rect x="1" y="1" width="30" height="30" rx="8" fill="#00A886"/><path d="M8 24l8-18 8 18" stroke="#fff" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/><path d="M16 8h8" stroke="#fff" strokeWidth="2.5" strokeLinecap="round"/></svg>
    case "dhan":
      return <svg {...props} style={s}><rect x="1" y="1" width="30" height="30" rx="7" fill="#6C3FD1"/><path d="M9 8v16c4-4 12-4 14-8S13 12 9 8" stroke="#fff" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
    case "fyers":
      return <svg {...props} style={s}><rect x="1" y="1" width="30" height="30" rx="8" fill="#1A237E"/><path d="M20 8H8v4h10v4H8v4h12v4H8" stroke="#fff" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/><path d="M22 8v16" stroke="#fff" strokeWidth="3" strokeLinecap="round"/></svg>
    case "fivepaisa":
      return <svg {...props} style={s}><rect x="1" y="1" width="30" height="30" rx="8" fill="#E8523D"/><circle cx="16" cy="16" r="9" stroke="#fff" strokeWidth="2.2"/><text x="16" y="20" textAnchor="middle" fontSize="16" fontWeight="800" fill="#fff" fontFamily="Arial, sans-serif">5</text></svg>
    case "kotakneo":
      return <svg {...props} style={s}><rect x="1" y="1" width="30" height="30" rx="8" fill="#1B2A4A"/><path d="M9 10h5v12H9zM18 10h5v8h-5zM18 20h5v2h-5z" fill="#fff"/></svg>
    case "finvasia":
      return <svg {...props} style={s}><rect x="1" y="1" width="30" height="30" rx="8" fill="#E84393"/><circle cx="16" cy="10" r="3.5" fill="#fff"/><path d="M8 24c0-8 16-8 16 0" stroke="#fff" strokeWidth="2.5" strokeLinecap="round" fill="none"/></svg>
    case "flattrade":
      return <svg {...props} style={s}><rect x="1" y="1" width="30" height="30" rx="7" fill="#0088CC"/><path d="M8 10h16M8 16h14M8 22h16" stroke="#fff" strokeWidth="2.5" strokeLinecap="round"/></svg>
    case "aliceblue":
      return <svg {...props} style={s}><rect x="1" y="1" width="30" height="30" rx="7" fill="#2196F3"/><path d="M10 22c0-6 12-6 12 0" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" fill="none"/><path d="M13 18c0-3 6-3 6 0" stroke="#fff" strokeWidth="2" strokeLinecap="round" fill="none"/><circle cx="16" cy="9" r="3" fill="#fff"/></svg>
    default:
      return <svg {...props} style={s}><rect x="1" y="1" width="30" height="30" rx="8" fill="color-mix(in srgb, var(--violet) 12%, transparent)"/><text x="16" y="21" textAnchor="middle" fontSize="16" fontWeight="700" fill="var(--violet)" fontFamily="sans-serif">{broker[0].toUpperCase()}</text></svg>
  }
}
