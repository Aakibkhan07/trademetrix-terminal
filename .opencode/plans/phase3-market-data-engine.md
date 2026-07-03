# Phase 3: Market Data Engine Implementation Plan

## Status: APPROVED — Ready for Implementation

---

## Implementation Order (11 steps)

### Step 1: Create `apps/api/market/cache.py`
**File**: `market/cache.py` — In-memory tick/quote/option-chain cache

- Singleton class `MarketCache`
- Fields: `_ticks` (dict[symbol -> (timestamp, Tick)]), `_latest_ticks` (OrderedDict, max 500), `_option_chains`, `_quotes`, `_market_status`
- Configurable TTLs: tick_ttl=60s, quote_ttl=30s, chain_ttl=10s, status_ttl=3600s
- Methods: `put_tick(tick)`, `get_tick(symbol)`, `get_all_ticks()`, `get_latest_ticks(limit)`, `put_option_chain(key, data)`, `get_option_chain(key)`, `put_quote(symbol, data)`, `get_quote(symbol)`, `put_market_status(status)`, `get_market_status()`, `clear()`
- Auto-evict stale entries on read
- Module-level singleton: `market_cache = MarketCache()`
- **Does NOT depend on Redis or core/cache.py**

### Step 2: Create `apps/api/market/types.py`
**File**: `market/types.py` — Normalized Tick with option fields

- `NormalizedTick(BaseModel)`: extends Tick fields + adds `last_quantity`, `oi_change`, `iv`, `source`
- `TickBuffer(list[NormalizedTick])`: bounded list with maxlen 1000
- `OptionChainEntry(BaseModel)`: strike, option_type, last_price, bid, ask, volume, oi, oi_change, iv, expiry, underlying
- `MarketStatus(BaseModel)`: is_open, open_time, close_time, next_holiday, last_check

### Step 3: Create `apps/api/market/adapter.py`
**File**: `market/adapter.py` — Standardized MarketDataAdapter wrapper

- `MarketDataAdapter` class wrapping any broker adapter
- Interface: `connect(config)`, `disconnect()`, `subscribe(symbols)`, `unsubscribe(symbols)`, `get_ltp(symbol)`, `get_quote(symbol)`, `get_option_chain(symbol, expiry)`, `get_historical_data(symbol, interval, days)`, `get_market_status()`
- Delegates to existing broker methods where available
- Registry: `get_market_data_adapter(broker_type)`

### Step 4: Create `apps/api/market/subscription_manager.py`
**File**: `market/subscription_manager.py` — Centralized subscription handling

- `SubscriptionManager` singleton wrapping existing SharedDataSocket
- Reconnect with exponential backoff (1s→2s→4s→...→max 60s)
- Health check every 30s

### Step 5: Create `apps/api/market/option_chain.py`
**File**: `market/option_chain.py` — NSE API + broker fallback

- `OptionChainEngine` singleton
- `get_option_chain(symbol, expiry)`: NSE API primary, broker fallback
- `calculate_pcr()`, `calculate_max_pain()`, `calculate_oi_change()`

### Step 6: Create `apps/api/market/historical.py`
**File**: `market/historical.py` — Unified historical data

- `HistoricalDataEngine` singleton
- Broker → simulator → empty fallback chain
- Caches with interval-dependent TTL

### Step 7: Create `apps/api/market/status.py`
**File**: `market/status.py` — Market open/closed detection

- Trading hours: 9:15-15:30 IST, Mon-Fri
- NSE holiday calendar on startup, cached 24h
- Weekend detection built-in

### Step 8: Update `apps/api/market/symbol_master.py`
- Add `auto_sync_fo()` daily at 8:00 AM IST
- Add `get_broker_symbol(broker, symbol)`, `get_symbol_info(symbol)`, `search_symbols()`

### Step 9: Update `apps/api/market/data_socket.py`
- `broadcast_tick()` now also caches via `market_cache.put_tick(tick)`
- Add `get_stats()` method

### Step 10: Create `apps/api/market/observability.py`
- `MarketMetrics` singleton: counters for ticks, latency, errors, reconnects

### Step 11: Update `apps/api/routes/v1_marketdata.py`
- Add 5 new GET endpoints (historical, option-chain, status, instruments, metrics)

---

## Rollback Plan

```bash
cd /Users/aakib/trademetrix-terminal
rm apps/api/market/cache.py apps/api/market/types.py apps/api/market/adapter.py
rm apps/api/market/subscription_manager.py apps/api/market/option_chain.py
rm apps/api/market/historical.py apps/api/market/observability.py
git checkout apps/api/market/symbol_master.py
git checkout apps/api/market/data_socket.py
git checkout apps/api/routes/v1_marketdata.py
```
7 deletions + 3 git checkouts. No DB rollback needed.
