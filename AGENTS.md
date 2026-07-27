# TradeMetrix Terminal — AGENTS.md

## Project
Automated trading terminal. FastAPI backend + Next.js frontend. Multi-broker (Fyers, Zerodha, Angel One, Dhan, Upstox, 5Paisa, Alice Blue, Finvasia, Flattrade, Kotak Neo, Groww). Supabase DB, Redis cache/rate-limiter, Prometheus metrics, Telegram alerts.

## Architecture
- `apps/api/` — FastAPI backend (Python 3.12)
- `apps/web/` — Next.js frontend
- `infra/` — Docker Compose deployment configs
- `supabase/` — DB migrations

## Key Directories (apps/api)
- `engine/` — Order gate (`gate.py`), strategy runners
- `execution/` — Order pipeline: `manager.py`, `broker_adapter.py`, `retry.py`
- `brokers/` — 11 broker adapters (`*_adapter.py`), `token_manager.py`, `registry.py`
- `risk/` — Risk checks (`riskguard.py`, `manager.py`, `rules.py`)
- `core/` — Config, security (encryption), DB, models
- `routes/` — API endpoints

## Current State

### Recently Fixed
1. **`execution/manager.py:130`** — `existing.get()` on `None` when `_check_existing_order()` returns `None`. Fix: guard with `if existing:`.
2. **`execution/manager.py`** — Replaced `.upsert()` with `.insert()` (no unique constraint on `client_order_id`).
3. **`brokers/token_manager.py:59`** — Added `hasattr`/`isinstance` guards on `authenticate()` return to handle dict vs object types safely.
4. **`core/security.py`** — `decrypt_broker_credentials()` returns `""` on empty/null ciphertext.
5. **`risk/helpers.py`** — Added missing `async_safe_single` import.
6. **`engine/gate.py:110`** — `_resolve_broker` now uses `creds.get("broker")` with `None` guard.
7. **`engine/gate.py:263-272`** — `risk_check` guarded with `if not risk_check:` + uses `.get("allowed")`.
8. **Frontend**: Fixed all `catch {}`  (19 instances), `key={i}` on dynamic lists (10 instances), `positions/page.tsx` missing `</tbody>`.
9. **Market-agent**: Decoupled API key / token decryption, added WS connect subscription wait, added health check.

### Verified Safe (never None)
- All 11 broker `place_order()` → always returns `OrderResult`
- All 11 broker `authenticate()` → always returns `Session` or raises
- `_execute_with_retry()` → always returns `OrderResult`
- `retry_with_backoff()` → always returns result or raises
- `_get_adapter()` → returns `None` on connect failure (callers handle with "BROKER_UNAVAILABLE")
- `TokenManager` → raises on decrypt failure, caught by `connect()` → `_get_adapter()` returns None
- `_resolve_broker()` → uses `.get()` with `None` guard

### Outstanding / Potential Issues
- **`gate.py`** — `_resolve_broker` and `risk_check` guards are in place. No known unguarded paths.
- **Frontend** — Widespread `any` types (~200 instances). Would need shared API client types to fix properly.
- **Market-agent** — No tests. WS connect timeout heuristic may need tuning per broker.

## Test Commands
```bash
cd apps/api && .venv/bin/pytest tests/ -x -q
```

## Deployment
```bash
bash infra/deploy-prod.sh    # pushes to GitHub + deploys to VPS
```
VPS: `root@187.127.185.56` — Docker Compose at `/root/trademetrix-terminal/infra/production/docker-compose.yml`