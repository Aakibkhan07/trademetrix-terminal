# Next Week Priorities — Week 2026-W32 (2026-07-29 → 2026-08-05)

## Priority actions for next week
| Action | Evidence source (gate: analytics / feedback / ticket / metrics / security) | Priority |
|--------|-----------------------------------------------------------------------------|----------|
| ✅ DONE 2026-08-05 — `20260804_01600_risk_audit_log.sql` applied to prod (table + index + PostgREST reload verified; KNOWN_ISSUES #14 closed) | metrics/logs (02-crash) + KNOWN_ISSUES #14 | P1 |
| ✅ DONE 2026-08-05 — `is_auth` on every tracked event (client via auth-context + server authority in track-batch); `session.start`/`page.view` split begins W33 | analytics (06/07/08/10 reports — inflated numbers) | P1 |
| Throttle/exempt the `/alerts/` poller from the rate limiter (610 429s/7d) | metrics (01/04 performance, top 429 path) | P2 |
| Broker re-auth UX: token-expiry countdown + one-tap reconnect on `/brokers` | analytics (06-funnel 13% connect) + tickets (KNOWN_ISSUES #1) | P2 |
| Downgrade `async_safe_single ... None` to DEBUG/throttle (653×/48h noise) | logs (02-crash) | P2 |
| ✅ DONE 2026-08-05 — 9 E2E feedback artifacts marked `wontfix`; next: `test:true` flag or self-cleanup in the E2E runner | feedback (05/11 — 9 artifacts) | P3 |
| Cohort query key on user_id only (kill phantom anonymous cohorts) | analytics (08-retention table is session-inflated) | P3 |

## Mission alignment
- Paying customers: 0 paying (tiers unexercised) → goal: first 10 via the backtest/builder loop (38 runs/5 users is the on-ramp evidence)
- Beta user support: 2 needs_attention broker creds under watch; **0 P0/P1 bugs open** (both P1s shipped today); risk-audit trail now durable
- Production bugs: open P1s = 0; token re-auth cycle remains mitigated-but-open at P2 (broker UX action above)
- UX improvements: shipped this week = backtest interactive charts + Trade Intelligence (v1.6.1), risk-aware reports (v1.6.0), report page; verified 12/12–25/25 prod smokes

## Explicitly NOT doing
- No new features or modules (feature freeze 08-04 still in effect) — this week's roadmap input is zero feature requests (05/11).
- No onboarding redesign until W33–W34 auth-split funnel shows a real drop (06/07).
- No retention programs until two weeks of user_id-only cohorts exist (08).
- No multi-worker / horizontal scaling work (traffic is 2× W31 with headroom; 04).
