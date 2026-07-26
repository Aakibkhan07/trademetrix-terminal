export function BrokerLogo({ broker, size = 32 }: { broker: string; size?: number }) {
  const props = { width: size, height: size, viewBox: "0 0 32 32", fill: "none", xmlns: "http://www.w3.org/2000/svg" }
  const s = { display: "inline-block", verticalAlign: "middle", lineHeight: 0 } as React.CSSProperties

  switch (broker) {
    case "zerodha":
      return <svg {...props} style={s}><rect x="1" y="1" width="30" height="30" rx="8" fill="#387ED1"/><path d="M8 23V9l8 14V9" stroke="#fff" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"/></svg>
    case "angelone":
      return <svg {...props} style={s}><rect x="1" y="1" width="30" height="30" rx="8" fill="#F05D5E"/><path d="M16 8v16M8 16h16" stroke="#fff" strokeWidth="2.4" strokeLinecap="round"/><circle cx="16" cy="16" r="4" stroke="#fff" strokeWidth="2"/></svg>
    case "upstox":
      return <svg {...props} style={s}><rect x="1" y="1" width="30" height="30" rx="8" fill="#2DBD9B"/><path d="M10 22L16 8l6 14" stroke="#fff" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"/><path d="M13 18h6" stroke="#fff" strokeWidth="2" strokeLinecap="round"/></svg>
    case "dhan":
      return <svg {...props} style={s}><rect x="1" y="1" width="30" height="30" rx="8" fill="#6C3FD1"/><path d="M10 8v16l8-8H10" stroke="#fff" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"/><path d="M20 12v8" stroke="#fff" strokeWidth="2.4" strokeLinecap="round"/></svg>
    case "fyers":
      return <svg {...props} style={s}><rect x="1" y="1" width="30" height="30" rx="8" fill="#1A237E"/><path d="M8 8h10v4H12v4h6v4H8V8" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"/><path d="M22 8v16" stroke="#fff" strokeWidth="2.2" strokeLinecap="round"/></svg>
    case "fivepaisa":
      return <svg {...props} style={s}><rect x="1" y="1" width="30" height="30" rx="8" fill="#E8523D"/><circle cx="16" cy="16" r="8" stroke="#fff" strokeWidth="2"/><text x="16" y="20" textAnchor="middle" fontSize="15" fontWeight="700" fill="#fff" fontFamily="sans-serif">5</text></svg>
    case "kotakneo":
      return <svg {...props} style={s}><rect x="1" y="1" width="30" height="30" rx="8" fill="#324A8E"/><path d="M10 8h4v16h-4zM18 8h4v8h-4zM18 20h4v4h-4z" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
    case "finvasia":
      return <svg {...props} style={s}><rect x="1" y="1" width="30" height="30" rx="8" fill="#E84393"/><path d="M10 24C10 12 22 12 22 24" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" fill="none"/><circle cx="16" cy="10" r="3" stroke="#fff" strokeWidth="2" fill="none"/></svg>
    case "flattrade":
      return <svg {...props} style={s}><rect x="1" y="1" width="30" height="30" rx="8" fill="#00A3E0"/><path d="M8 10h16M8 16h12M8 22h16" stroke="#fff" strokeWidth="2.4" strokeLinecap="round"/></svg>
    case "aliceblue":
      return <svg {...props} style={s}><rect x="1" y="1" width="30" height="30" rx="8" fill="#2196F3"/><path d="M16 8c-4 0-7 3-7 7s3 7 7 7" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" fill="none"/><path d="M16 12c-2 0-3 1.5-3 3s1 3 3 3" stroke="#fff" strokeWidth="2" strokeLinecap="round" fill="none"/><circle cx="22" cy="22" r="3" fill="rgba(255,255,255,0.3)"/></svg>
    default:
      return <svg {...props} style={s}><rect x="1" y="1" width="30" height="30" rx="8" fill="color-mix(in srgb, var(--violet) 12%, transparent)"/><text x="16" y="21" textAnchor="middle" fontSize="16" fontWeight="700" fill="var(--violet)" fontFamily="sans-serif">{broker[0].toUpperCase()}</text></svg>
  }
}
