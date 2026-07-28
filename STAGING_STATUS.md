# Staging Validation Status

| # | Workflow | Status | Notes |
|---|----------|--------|-------|
| 1 | Angel One Broker Login | ⏳ BLOCKED | Needs real Angel One credentials |
| 2 | Dhan Broker Login | ⏳ BLOCKED | Needs real Dhan OAuth credentials |
| 3 | Fyers Broker Login | ✅ VERIFIED | OAuth flow complete, token valid, engine running |
| 4 | Live Market Data | ✅ VERIFIED | Yahoo Finance fallback, Latency 214-281ms |
| 5 | Option Chain | ✅ VERIFIED | Mock generator, Greeks included |
| 6 | BUY Market Order | ⏳ BLOCKED | Needs active broker connection with funds |
| 7 | SELL Market Order | ⏳ BLOCKED | Needs active broker connection with positions |
| 8 | LIMIT Order | ⏳ BLOCKED | Needs active broker connection with funds |
| 9 | Modify Order | ⏳ BLOCKED | Needs active broker connection |
| 10 | Cancel Order | ⏳ BLOCKED | Needs active broker connection |
| 11 | Positions | ✅ VERIFIED | Endpoint returns 200 (empty: no open positions) |
| 12 | Holdings | ✅ VERIFIED | Endpoint returns 200 (empty: no delivery holdings) |
| 13 | Funds | ✅ VERIFIED | Endpoint returns 200 (zero balance account) |
| 14 | Strategy Execution | ⏳ BLOCKED | Needs active broker connection with funds |
| 15 | Auto Trading | ⏳ BLOCKED | Needs active broker connection with funds |
| 16 | Multi-Account Trading | ⏳ BLOCKED | Needs additional broker connections |
| 17 | Kill Switch | ✅ VERIFIED | Global + per-user, Redis-backed |
| 18 | Server Restart Recovery | ✅ VERIFIED | Graceful shutdown, orders reconciled |
| 19 | Broker Reconnect | ✅ VERIFIED | Engine auto-authenticates from stored token |
| 20 | Token Refresh | ⏳ MANUAL | Fyers tokens expire ~24h, no refresh_token mechanism |
| 21 | End-to-End Live Trading Validation | ⏳ BLOCKED | Needs broker with funds and market hours |

## Connected
- **Fyers**: App ID `PKL4EMD8ML-200`, token valid until ~2026-07-29T07:30Z, `token_status=valid`, broker active

## Blocked By
- **Angel One credentials**: Client Code, Password, App Key
- **Dhan OAuth credentials**: Client ID, Client Secret
- **Upstox OAuth credentials**: API Key, API Secret
- **Zerodha OAuth credentials**: API Key, API Secret
- **Funded broker account**: Fyers account has zero balance — funds/positions endpoints return valid empty responses
