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

### Recently Fixed — Commit `03a45fd`
1. **`execution/manager.py:130`** — `existing.get()` on `None` when `_check_existing_order()` returns `None` (insert fails for non-duplicate reason). Fix: guard with `if existing:` — return `INSERT_FAILED` otherwise.
2. **`execution/manager.py`** — Replaced `.upsert()` with `.insert()` because `client_order_id` has no unique constraint, causing silent upsert failures.
3. **`brokers/token_manager.py:59`** — Added `if session_obj is None: raise ValueError(...)` guard on `authenticate()` return.
4. **`core/security.py`** — `decrypt_broker_credentials()` returns `""` on empty/null ciphertext instead of crashing.
5. **`risk/helpers.py`** — Added missing `async_safe_single` import.

### Order Pipeline Flow
```
gate.py:execute_order()
  → resolve_broker() — gets active broker from broker_credentials table
  → RiskGuard.check_order() — risk checks
  → symbol_master.resolve_symbol()
  → execution_manager.place_order(req)
    → _build_normalized_order()
    → validate_order()
    → risk_manager.evaluate()
    → _get_adapter() — connects to broker via BrokerExecutionAdapter
      → TokenManager.get_session() — loads/refreshes credentials
      → adapter.authenticate(session)
    → _insert_order_atomic() — DB insert
    → _execute_with_retry() — calls adapter.place_order with retry
    → _update_order_in_db()
```

### Key Design Decisions
- **Broker resolution before risk check** — `RiskGuard.check_order()` uses `subscription_tier` from `resolve_capabilities_by_id()` which requires knowing the broker.
- **No upsert** — `.insert()` used instead because `client_order_id` has no unique constraint in Supabase.
- **Token refresh** — Credentials decrypted via `decrypt_broker_credentials()`, token refresh with timeout (10s), 1 retry, 5-min expiry buffer.
- **Rate limiter** — Per-broker Redis-based token bucket.
- **Kill switch** — Redis flag `global:kill_switch`, checked in `RiskGuard`.

### Verified Safe (never None)
- All 11 broker `place_order()` → always returns `OrderResult`
- All 11 broker `authenticate()` → always returns `Session` or raises
- `_execute_with_retry()` → always returns `OrderResult`
- `retry_with_backoff()` → always returns result or raises
- `_get_adapter()` → returns `None` on connect failure (callers handle with "BROKER_UNAVAILABLE")
- `TokenManager` → raises on decrypt failure, caught by `connect()` → `_get_adapter()` returns None

### Outstanding / Potential Issues
- **`token_manager.py:59`** — `session_obj.get("access_token")` still called via fallback path if `session_obj` lacks `access_token` attribute. Guard added for `None` but unknown non-dict types could still cause `AttributeError`.
- **`gate.py:263`** — `risk_check["allowed"]` assumes `risk_check` is dict. If `RiskGuard.check_order()` returns `None`, this would crash with `TypeError`. RiskGuard always returns dict in current code.
- **`gate.py:110`** — `_resolve_broker` uses `creds["broker"]` (not `.get()`) — could `KeyError` if schema changes.
- **No tests** for `execution/manager.py` `place_order()` method.

### Broker Credential Decrypt Chain
```
decrypt_broker_credentials(ciphertext)
  → empty guard → returns "" if falsy
  → Fernet decrypt → returns plaintext
  → on failure → logs warning, returns ""

TokenManager._load_credentials()
  → for each row: decrypt api_key, secret_key, access_token
  → if InvalidToken: skip row, try next
  → if no decryptable rows: raise ValueError
  → caller catches → connect() returns False → BROKER_UNAVAILABLE
```

## Test Commands
```bash
cd apps/api && .venv/bin/pytest tests/ -x -q
```

## Deployment
```bash
bash infra/deploy-prod.sh    # pushes to GitHub + deploys to VPS
```
VPS: `root@187.127.185.56` — Docker Compose at `/root/trademetrix-terminal/infra/production/docker-compose.yml`