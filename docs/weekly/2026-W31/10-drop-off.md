# Weekly User Drop-Off Report — Week 2026-W31 (2026-07-25 → 2026-08-01)

## Session stats (7d)
- sessions7d|0; bounce_sessions|0; avg_events_per_session|— (no events yet — tracker ships this week)

## Crash signatures (7d: key | count)
None (client-side; server-side crash evidence below)

Server-side stability evidence (7d, from Prometheus + API logs — the drop-off causes users actually hit):
- 5xx responses: 87 (all 503) out of ~49,860 requests (0.17%).
- 4xx: 1,199 — dominated by 429 rate-limits (653, ~7% of 4xx; 93/day) and 401 (470; unauthenticated dashboard probes).
- Exception volume ≈932–936 in API logs; signatures: "Token refresh failed" 192×, CircuitBreakerError 84× (breaker broker_fyers OPEN), async_safe_single NoneType 48×, "access token has expired" 29×.
- p95 latency: API 0.333s, edge (Caddy) 1.188s. Zero container restarts.
- Fyers token state: 3 of 4 credentials needs_attention (expired 2026-08-01 00:30 UTC); open issue #2.

## Analysis
- The single biggest drop-off risk this week is external: the Fyers token expiry makes broker connection and live orders fail for every affected user, and produces most 503s and breaker trips.
- 429s (653/week ≈ 93/day) hit API pollers; likely invisible to users but worth confirming against the session event stream in W32.
- No client-side crash data yet; api_error events (server 5xx) start recording with the Beta Ops release.

## Recommendations
- Fix #2 (Fyers re-auth) before interpreting any W32 funnel drop-off at the broker step.
- After tracker ships, cross-reference 429 bursts with session counts to prove or disprove user-visible impact (#5).
