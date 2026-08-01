# Beta Operations Guide

## Overview

The Beta Operations layer provides admin tooling for managing the TradeMetrix Terminal beta program, user support, system monitoring, and audit capabilities.

## Admin Dashboard (`/admin`)

### Dashboard Tab
- **KPI Cards**: Total users, admins, active assignments, strategies (from `/admin/stats`)
- **System Health**: Broker connectivity (active/total OAuth brokers), running strategies count, OMS queue placeholder, error rate placeholder
- **Active Sessions**: Total registered users count from `/admin/users`
- **Recent Activity**: Last 5 audit log entries from `/admin/audit-log?limit=5`
- **Tier Distribution**: Bar chart showing users per subscription tier

### Users Tab
- Lists all users with email, full name, tier, created date
- **Activate/Deactivate**: Toggle user active status
- **Tier Change**: Dropdown with Free/Starter/Pro/Enterprise — calls `updateTier()` API

### Brokers Tab
- Lists all broker connections from `/admin/brokers` with status, exchange, meta
- **Revoke**: Removes broker connection with confirmation

### Orders Tab (Trades)
- Lists all orders from `/admin/orders`
- Shows ID, symbol, side (colored), type, status, filled, price, created date
- **Cancel**: Cancels individual orders

### Audit Tab
- Filterable by action type (login, trade, admin, settings, etc.)
- Table: Time, User ID, Action, Resource, Details
- **Refresh**: Reloads from `/admin/audit-log`
- **Export CSV**: Downloads current filtered entries as CSV file

### Risk Tab
- Kill switch status, circuit breaker, max drawdown settings
- **Toggle**: Enable/disable kill switch
- **Update**: Save risk settings via API

### Broadcast Tab
- Input for message text
- **Send**: Broadcasts message to all users

### Support Tab (New)
- **User Search**: Search by email or name, results show tier badge
- **Action Cards** (UI-only, require backend):
  - **Impersonate User**: Copies user ID to clipboard
  - **Disable Account**: Shows warning toast (requires backend endpoint)
  - **Force Logout**: Terminates all sessions
  - **Reset Broker**: Clears broker credentials
  - **Clear Cache**: Resets runtime state

### Beta Tab
- Link to `/admin/beta` for full beta program management

## Beta Invite System (`/admin/beta`)

### Invite Codes
- Generate N random 8-character alphanumeric codes
- Status: Available (green), Used (amber), Revoked (red)
- **Copy**: Copies code to clipboard
- **Revoke**: Marks code as revoked

### Waitlist
- Pre-populated demo entries (John Doe, Jane Smith, Bob Wilson)
- **Add**: Add email + name to waitlist
- **Approve/Reject**: Update entry status with toast feedback
- Approved users appear in Approvals tab

### Approvals
- Shows approved users with invite codes
- **Send Invite Email**: Toast confirmation
- **Remove Access**: Removes user from approved list

## Status Page (`/status`)

### System Components
- **API Server**: Checks `/api/v1/health/live`
- **Web App**: Checks `/health`
- **Database**: Parses `/api/v1/health/ready` for `dependencies.database`
- **Cache (Redis)**: Parses `/api/v1/health/ready` for `dependencies.cache`
- **WebSocket**: Attempts EventSource connection to `/ws`
- **Market Data Feed**: Derived from API Server status

Each component shows: name, status dot (green/red/yellow), status text, last checked time.

### Incident History
- Hardcoded entries: Redis issue (Jul 3), Scheduled maintenance (Jun 28), API outage (Jun 15)
- Each shows date, title, resolved/completed badge

### Maintenance
- Displays current status: "Not in maintenance" (green dot)
- **Toggle**: Shows toast — requires server config

### Uptime Stats
- Today: 100%, This Week: 99.9%, This Month: 99.8%

## Architecture

### Files
| File | Purpose |
|------|---------|
| `app/admin/page.tsx` | Main admin dashboard (7 tabs) |
| `app/admin/beta/page.tsx` | Beta invite management (3 tabs) |
| `app/admin/broadcast/page.tsx` | Broadcast messages |
| `app/status/page.tsx` | Public status page |
| `components/app-layout.tsx` | Sidebar navigation (System section) |

### API Endpoints Used
| Endpoint | Source |
|----------|--------|
| `/admin/stats` | `api.admin.stats()` |
| `/admin/users` | `api.admin.users.list()` |
| `/admin/users/:id/tier` | `api.admin.users.updateTier()` |
| `/admin/brokers` | `api.admin.brokers()` |
| `/admin/orders` | `api.admin.orders()` |
| `/admin/audit-log` | `api.admin.auditLog()` |
| `/admin/active-brokers` | `api.admin.activeBrokers()` |
| `/admin/risk` | `api.admin.risk()` |
| `/admin/broadcast` | `api.admin.broadcast.*` |
| `/health/live` | Public health check |
| `/health/ready` | Public health check |

## Development Notes

- All user support actions (Support tab) are UI-only with toast confirmations — backend endpoints needed for actual functionality
- Beta invite data is stored in component state (session-only, no persistence)
- Status page polls health endpoints on load (no auto-refresh)
- Audit export generates CSV via Blob download
- `/status` is a standalone page (no sidebar, no auth required)
