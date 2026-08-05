# Weekly Activation Report — Week 2026-W32 (2026-07-29 → 2026-08-05)

## Activation stages (all-time: stage | users)
total_users | 31;broker_connected|4;traded|2;live_traded|1

## Daily active tracked users (7d: date | users)
2026-08-01 | 6;2026-08-02|16;2026-08-03|3;2026-08-04|49;2026-08-05|10

## Analysis
- All-time activation: 31 accounts → 4 broker connections (13%) → 2 traders (6%) → 1 live trade (3%). No change vs W31 on a per-stage basis (+5 accounts, still 4 connected, 2 traded, 1 live).
- **Signups are not converting at the broker step; nothing else has stalled.** 38 backtest runs by 5 users and 20 builder strategies show the product loop without a broker is healthy — activation that requires "place a trade" is bottlenecked entirely at broker connection.
- Daily tracked users are inflated on 08-04 (49) by the deploy/smoke day and are mixed anonymous+signed-in. Honest barometer: **3 signed-in users in the last 7 days**, 12 signed-in ever.
- 2 of 4 credential rows remain `needs_attention` (Fyers token expiry cycle); the token-incident week (expired ~08-01, revalidated 08-04) sits exactly inside the measurement window.

## Recommendations
- Split DAU/activation by auth status in the tracker (one boolean property) — W33 onward.
- Treat "broker re-auth" (the 2 needs_attention rows + KNOWN_ISSUES #1) as the only activation change justified by data this week.
- Track "first backtest" as an activation event (5 users this week — bigger than broker activation; evidence it is the true current on-ramp).
