# Weekly Customer Feedback Summary — Week 2026-W31 (2026-07-25 → 2026-08-01)

## New user reports this week
- None received. **No feedback channel exists** (no in-app feedback, no support inbox, no analytics), so user reports cannot arrive by product design. The only external channel is the public GitHub tracker (no issues filed this week).

## Themes
- **Theme 1 — Observation gap (derived from zero reports)**: we cannot see users, so we cannot classify user-reported issues. Every "report" this week is instead derived from telemetry: broker credential states (3/4 broken), recurring `safe_query` warnings, 429/401 volume, and log exception signatures. This is not a substitute for user reports.
- **Theme 2 — Fyers expiry is the week's dominant user-facing event**: the only funded account cannot trade (token expired 2026-08-01 00:30 UTC); 3/4 stored credentials require attention. Any beta user hitting this would be blocked with no in-app explanation.
- **Theme 3 — Silent operational noise**: `async_safe_single` NoneType warnings (~28/day) recur with no diagnosable context.

## Classification summary
| Priority | Open | Resolved |
|----------|------|----------|
| P0 | 0 | 0 |
| P1 | 2 ([#2](https://github.com/Aakibkhan07/trademetrix-terminal/issues/2) Fyers re-auth blocking live trading; [#3](https://github.com/Aakibkhan07/trademetrix-terminal/issues/3) no feedback channel) | 0 |
| P2 | 2 ([#4](https://github.com/Aakibkhan07/trademetrix-terminal/issues/4) safe_query NoneType; [#5](https://github.com/Aakibkhan07/trademetrix-terminal/issues/5) 429s during polling) | 0 |
| P3 | 1 ([#6](https://github.com/Aakibkhan07/trademetrix-terminal/issues/6) dormant accounts / onboarding) | 0 |

## Recommendations
1. **Stand up the feedback path this week** (P1 for the observation program): support address + minimal in-app "Report a problem" (URL + recent action + free text). Until this exists, Founder Mode's mandate — classify *user-reported* issues — cannot be executed; everything is telemetry-derived.
2. **Classify inbound reports into GitHub issues with P0–P3 labels** from this week forward (triage protocol in `FOUNDER_MODE.md`).
3. No product-feature recommendations this week: with zero user reports and zero non-founder usage, any feature suggestion would be invented, not observed. The only grounded improvements are the telemetry-observed fixes listed in the other four reports.
