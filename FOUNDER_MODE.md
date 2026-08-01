# Founder Mode — TradeMetrix v1.0 (GA)

TradeMetrix v1.0 is **feature complete**. No new product modules.

Operating mode: **observe real users → classify every reported issue → publish weekly evidence-based reports → recommend improvements from observed behavior only.**

## Roadmap Evidence Gate (mandatory)

**No roadmap item may enter development unless supported by at least one of:**

1. **Product analytics** — event/usage data (e.g. funnel drop-offs, feature usage, session replay, crashes).
2. **User feedback** — in-app feedback (bug/feature/nps/report), support inbox, GitHub issues.
3. **Support ticket** — an actual user-reported problem from a support channel.
4. **Performance metrics** — latency, error rates, capacity, resource or reliability measurements.
5. **Security issue** — a demonstrated vulnerability or security defect.

**Opinion alone is not sufficient.** Every roadmap item must cite the evidence source(s) that justify it; an item with no backing evidence stays in the backlog (P3).

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
3. **Report** — publish 11 reports under `docs/weekly/<YYYY-Wnn>/`:
   - `01-product-health.md` — adoption, activity, top issues, RAG status
   - `02-crash-report.md` — crashes, restarts, exceptions, top exception signatures
   - `03-ux-report.md` — observed behavior signals, friction points, usability findings
   - `04-performance-report.md` — latency, error rates, capacity, resource trends
   - `05-customer-feedback.md` — verbatim user feedback, themes, classification
   - `06-funnel.md` — step conversions and drop-off (Beta Ops analytics)
   - `07-activation.md` — activation stages and daily activity
   - `08-retention.md` — weekly cohort retention
   - `09-most-used-features.md` — event-based feature usage ranking
   - `10-drop-off.md` — session stats, bounce, crash signatures
   - `11-most-requested-features.md` — requested-feature evidence for the roadmap
4. **Recommend** — improvement proposals grounded strictly in the week's observations, each citing its evidence source per the Roadmap Evidence Gate.

## Tooling

- Report data is generated reproducibly by `infra/scripts/weekly_report.sh` (SSH → VPS → Prometheus + Supabase + logs → markdown skeletons in `docs/weekly/`) and `infra/scripts/analytics_report.sh` (Beta Ops reports 06–11 from `analytics_events` + `feedback_items`). Analysis sections are authored by a human/AI from the real data.
- Issue tracker: GitHub issues on `Aakibkhan07/trademetrix-terminal` (public; no secrets in issues).
- Feedback channels: in-app Feedback Center (bug/feature/nps/report → Supabase), Beta Dashboard triage at `/admin/beta` (admin), GitHub issues, support reach-outs.

## What Founder Mode is NOT

- No new features, no new modules, no scope creep from suggestions that aren't tied to observed behavior.
- No changes driven by speculation about what users *might* want.
