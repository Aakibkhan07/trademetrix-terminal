# Founder Mode — TradeMetrix v1.0 (GA)

TradeMetrix v1.0 is **feature complete**. No new product modules.

Operating mode: **observe real users → classify every reported issue → publish weekly evidence-based reports → recommend improvements from observed behavior only.**

## Issue Classification (mandatory for every beta user report)

| Priority | Definition | SLA | Examples |
|----------|-----------|-----|----------|
| **P0** | Money-losing defect, data loss, security breach, platform down, order execution incorrect | Fix immediately (24 h), hot-patch | Wrong fill prices, double orders, credentials leak, total outage |
| **P1** | Blocks a real user's core workflow; major feature broken; persistent crashes; no reasonable workaround | Fix in next release (≤ 2 weeks) | Live trading blocked by broker token expiry, strategy can't deploy, backtest always fails |
| **P2** | Usability defect, minor bug, edge case affecting some users; workaround exists | Scheduled (≤ 1 month) | Recurring harmless warnings masking failures, confusing error message, slow page |
| **P3** | Cosmetic, nice-to-have, internal-only noise | Backlog | TzCache warnings, tooltip copy, icon inconsistency |

Rules:
- Every user-reported issue gets a GitHub issue with a `P0`–`P3` label, then is worked per SLA.
- Evidence over opinion: no fix ships without observed behavior behind it.
- **Usability > functionality**: when a choice exists, prefer the change that reduces user friction/cognitive load, not the one that adds power.

## Weekly cadence (every Friday, ISO week)

1. **Observe** — pull data: Prometheus (7d metrics), Supabase (user activity), API logs (exceptions/restarts), GitHub issues, support channel.
2. **Triage** — classify all new reports; verify P0/P1 against live data.
3. **Report** — publish 5 reports under `docs/weekly/<YYYY-Wnn>/`:
   - `01-product-health.md` — adoption, activity, top issues, RAG status
   - `02-crash-report.md` — crashes, restarts, exceptions, top exception signatures
   - `03-ux-report.md` — observed behavior signals, friction points, usability findings
   - `04-performance-report.md` — latency, error rates, capacity, resource trends
   - `05-customer-feedback.md` — verbatim user feedback, themes, classification
4. **Recommend** — improvement proposals grounded strictly in the week's observations.

## Tooling

- Report data is generated reproducibly by `infra/scripts/weekly_report.sh` (SSH → VPS → Prometheus + Supabase + logs → markdown skeletons in `docs/weekly/`). Analysis sections are authored by a human/AI from the real data.
- Issue tracker: GitHub issues on `Aakibkhan07/trademetrix-terminal` (public; no secrets in issues).
- Feedback channels currently observed: none exist yet — no in-app feedback, no support inbox, no analytics (see Week 1 Customer Feedback report). Until one exists, "user reports" come from support reach-outs, GitHub issues, and observed behavior.

## What Founder Mode is NOT

- No new features, no new modules, no scope creep from suggestions that aren't tied to observed behavior.
- No changes driven by speculation about what users *might* want.
