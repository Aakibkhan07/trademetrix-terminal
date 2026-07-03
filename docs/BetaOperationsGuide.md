# Beta Operations Guide — TradeMetrix Terminal

## Overview

This guide covers all operational procedures for managing the closed beta program (20 users). All tools are already built into the platform — this document explains how to use them.

**Beta period**: July 7 – August 7, 2026 (4 weeks)
**Capacity**: 20 invite-only users
**Contact**: ops@trademetrix.tech

---

## 1. Invite Management

### Generate Invite Codes

Each beta user needs a unique invite code to register.

1. Navigate to **Admin → Beta** (`/admin/beta`)
2. Select the **Invite Codes** tab
3. Enter the number of codes (e.g., 20 for full cohort)
4. Click **Generate Codes**
5. Each code appears with status badges:
   - **Available** (green) — ready to send
   - **Used** (amber) — code has been redeemed
   - **Revoked** (red) — manually invalidated
6. Click **Copy** to copy a code to clipboard

### Send Invites

1. In the **Waitlist** tab, add users by email + name
2. Click **Approve** to mark a user approved
3. In the **Approvals** tab, click **Send Invite Email** (sends confirmation toast — actual email delivery requires SMTP backend)
4. Provide the invite code to the user via your own channel (email/Slack)

### Revoke Access

- **Revoke invite code**: In **Invite Codes** tab, click **Revoke** on any Available code
- **Remove user access**: In **Approvals** tab, click **Remove Access**
- **Emergency suspend**: In **Admin → Users** tab, select user → change tier to `free` or deselect their active assignments

### Batch Invite (20 users)

Generate 25 codes (20 + 5 buffer). Record codes and assigned users in a spreadsheet. Send codes via email with onboarding instructions.

---

## 2. User Management

All user management is in the **Admin** page (`/admin`).

### Users Tab

- **Search**: Filter by email or name
- **Select**: Click a user to view details
- **Change tier**: Dropdown to upgrade/downgrade subscription tier
- **Assign strategies**: Toggle strategy assignments per user
- **View limits**: Active assignments / max strategies shown per user

### Support Tab

- **Search**: Find users by email or name
- **Action cards** (UI actions — backend required for real effect):
  - **Impersonate**: Copies user ID for debugging
  - **Force Logout**: Terminates sessions
  - **Reset Broker**: Clears broker credentials
  - **Clear Cache**: Resets runtime state

### Suspending a User

1. Go to **Admin → Users**
2. Search for the user
3. Select them, then set tier to `free`
4. Remove all strategy assignments
5. (Optional) Use **Support → Force Logout** to terminate sessions

---

## 3. Feedback Collection

Users submit feedback via **Feedback** (`/feedback`). Three channels:

### Bug Reports
- Title + description + optional email
- Currently stores in-memory only (toast confirmation)
- **Admin must manually record:** copy bug details to the bug tracker

### Feature Requests
- Same form as bug reports
- Tag the request and add to the roadmap

### NPS Survey
- 0-10 rating scale
- Sentiment: Promoter (9-10), Passive (7-8), Detractor (0-6)
- Optional comments

### Weekly Feedback Review Process

1. Ask users to submit feedback via `/feedback`
2. Manually collect from users during check-ins
3. Log all feedback in the weekly report (see Section 5)

---

## 4. Usage Monitoring

Two dashboards available:

### Analytics (`/analytics`)

Real-time platform metrics:

| Metric | Source |
|--------|--------|
| Total P&L | `/engine/positions` → unrealised P&L |
| Win Rate | `/engine/orders` → filled order P&L |
| Total Trades | `/engine/orders` → count |
| Active Strategies | `/strategies/list` → is_active |
| Total Margin | `/engine/funds` |
| Brokers Connected | `/brokers/credentials` |
| Users | `/admin/stats` |
| Recent Runs | `/engine/runs` |

### Admin Dashboard (`/admin` Dashboard tab)

Operational metrics:

| Panel | Source |
|-------|--------|
| Total Users | `/admin/stats` |
| Admins | `/admin/stats` |
| Active Assignments | `/admin/stats` |
| Strategies | `/admin/stats` |
| Broker Status | `/admin/active-brokers` |
| Active Sessions | `/admin/users` → count |
| Recent Activity | `/admin/audit-log?limit=5` |

### Status Page (`/status`)

Public system health monitoring:

- **API Server**: `/api/v1/health/live`
- **Web App**: `/health`
- **Database**: `/api/v1/health/ready` → `dependencies.database`
- **Cache**: `/api/v1/health/ready` → `dependencies.cache`
- **WebSocket**: EventSource to `/ws`
- **Market Data**: Derived from API status

---

## 5. Weekly Beta Report

### Template

```markdown
# Beta Report — Week {N} (Jul 7 – Jul 13, 2026)

## Summary
- Active users: {count}
- New invites sent: {count}
- Suspensions: {count}

## Usage Metrics
- Daily Active Users: {avg}
- Total orders placed: {count}
- Broker connections: {count}
- Strategy runs: {count}
- Error rate: {pct}

## Feedback
- Bug reports: {count}
  - {summary of each}
- Feature requests: {count}
  - {summary of each}
- NPS score: {score} ({Promoters/Passives/Detractors})
  - {top comments}

## Incidents
- {date}: {description} — {status}
- {date}: {description} — {status}

## Action Items
- [ ] {item}
- [ ] {item}

## Recommendations
- {recommendation}
```

### Collection Method

| Data Point | How to Collect |
|------------|---------------|
| Active users | `/admin` Dashboard → Active Sessions |
| Orders | `/analytics` → Total Trades |
| Brokers | `/analytics` → Brokers Connected |
| Strategies | `/analytics` → Active Strategies |
| Error rate | Admin Dashboard → Error Rate panel |
| Runs | `/analytics` → Recent Runs |
| Feedback | Check-in with users + `/feedback` |
| Incidents | Status page + server logs |

### Distribution
- Send to: team@trademetrix.tech
- Format: Markdown (this template)
- Frequency: Every Monday by 10:00 AM

---

## 6. Incident Response

### Severity Levels

| Level | Definition | Response Time |
|-------|-----------|---------------|
| S1 | Platform down, no one can trade | 15 min |
| S2 | Feature broken, trading degraded | 1 hour |
| S3 | Minor bug, cosmetic issue | Next business day |
| S4 | Question, improvement | Within week |

### Response Steps

1. **Acknowledge**: Confirm the incident in team chat
2. **Assess**: Check `/status` for system health
3. **Contain**: Use Admin → Users → Support to disable affected users if needed
4. **Fix**: Deploy fix via standard pipeline
5. **Verify**: Confirm on `/status` and in staging
6. **Communicate**: Update affected users via email

### Emergency Contacts

| Role | Contact |
|------|---------|
| Lead Developer | dev@trademetrix.tech |
| Infrastructure | ops@trademetrix.tech |
| User Support | support@trademetrix.tech |

---

## 7. Onboarding Flow

Send this to each new beta user:

```
Welcome to TradeMetrix Terminal Beta!

1. Go to https://ai.trademetrix.tech/auth
2. Enter your invite code when prompted
3. Complete the 6-step onboarding wizard:
   a. Create account or sign in
   b. Connect a broker (paper trading available)
   c. Enable paper trading mode
   d. Explore your first strategy
   e. Run a backtest
   f. Go live with paper trading
4. Submit feedback at /feedback
5. Check /status for system health

Need help? Email support@trademetrix.tech
```

---

## 8. Tools Reference

| Page | URL | Purpose |
|------|-----|---------|
| Admin Dashboard | `/admin` | Operations, users, brokers, trades, audit, risk |
| Beta Management | `/admin/beta` | Invite codes, waitlist, approvals |
| Broadcast | `/admin/broadcast` | Send messages to all users |
| Analytics | `/analytics` | Platform usage metrics |
| Feedback | `/feedback` | Bug reports, feature requests, NPS |
| Status | `/status` | System health monitoring |
| Help Center | `/help` | User documentation |
| Changelog | `/changelog` | Release history |

## 9. First Week Checklist

- [ ] Generate 25 invite codes (20 + 5 buffer)
- [ ] Assign codes to the first 20 users
- [ ] Send onboarding email to each user
- [ ] Verify all users can complete onboarding
- [ ] Confirm `/status` shows all systems operational
- [ ] Set up weekly report template
- [ ] Create a shared bug tracker (spreadsheet or Notion)
- [ ] Schedule weekly check-in with beta users
- [ ] Test force-logout on a test user
- [ ] Verify `/admin/broadcast` reaches all users
