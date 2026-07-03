# Production Readiness Audit — TradeMetrix Terminal

> Generated: 2026-07-03 | Scope: apps/api (market/, runtime/, engine/)
> Auditor's note: Only the most impactful issues (46 total) are listed, prioritized by severity.

---

# CRITICAL (Must fix before production)

## C1. RuntimeContext calls nonexistent method `market_cache.get_candles()`
- **File:** `runtime/context.py:86`
- **Root cause:** `self._build_indicator_context()` calls `market_cache.get_candles(symbol, interval)` which does NOT exist on `MarketCache` (only `get_tick`, `get_quote`, `get_option_chain` exist). This raises `AttributeError` on every strategy evaluation.
- **Fix:** This should call `market_cache.get_candles(...)` which needs to be implemented, or use a candle store client (e.g., Supabase/Redis candle repository). The method is currently dead code that crashes any strategy evaluation that reaches the indicator context builder.
- **Risk:** **Every strategy evaluation crashes** when `_build_indicator_context` is called. No strategy can function.
- **Effort:** 2–4h (implement candle storage/retrieval backend)

## C2. Quote context silently returns all zeros
- **File:** `runtime/context.py:57–68`
- **Root cause:** `market_cache.get_quote()` returns a `dict`, not an object. `hasattr(cached, "last_price")` on a dict is `False`, so every portfolio/quote lookup returns zero values. Strategies trading based on bid/ask or margin see zero prices.
- **Fix:** Change to `cached.get("last_price", 0)` pattern since `get_quote` returns a dict.
- **Risk:** Strategies making decisions on zero price data produce incorrect signals silently.
- **Effort:** 30 min

## C3. Complete strategy state loss on process restart
- **File:** `runtime/manager.py:63–66`, `runtime/registry.py:22–26`
- **Root cause:** `_configs`, `_contexts`, `_evaluation_tasks`, `_states`, `_instances` are all in-memory dicts with zero persistence. An API server restart wipes all registered strategies, running states, and instances. No recovery mechanism.
- **Fix:** Persist strategy state to DB (strategy_health table exists but is write-once). Add a `load_state()` on startup to rehydrate RUNNING strategies. Add a `StrategyStateChange` model with timestamps for audit trail.
- **Risk:** Any deployment or crash loses all running strategies. Operators must manually restart every strategy.
- **Effort:** 8–12h

## C4. Synchronous HTTP calls in `execute_order` block the event loop
- **File:** `engine/gate.py:61–82` (`_write_audit`), `engine/gate.py:87–97` (`_log_order`)
- **Root cause:** `_write_audit` and `_log_order` call `supabase.table(...).insert(...).execute()` synchronously (blocking the entire asyncio event loop) in the hot path of order execution. With high-frequency trading, this blocks all concurrent operations.
- **Fix:** Use async Supabase client (`get_async_supabase()`) or push to a background task queue / message bus for audit persistence.
- **Risk:** Event loop stalls of 50–500ms per order, cascading latency across all users and strategies.
- **Effort:** 4–8h

## C5. Synthetic historical data served without markers → cache poisoned
- **File:** `market/historical.py:38–43`
- **Root cause:** When `_fetch_from_broker()` returns empty, `get_historical()` silently falls back to `_synthesize()` (randomly generated candles) and caches them under a key `historical:{symbol}:{exchange}:{interval}:{days}` that does NOT include `user_id`. User A's failed fetch == User B sees fake data.
- **Fix:** (1) Synthesized data must have an `is_synthetic: true` flag. (2) Include `user_id` in cache key. (3) Never cache synthetic data. (4) Expose synthetic flag to UI.
- **Risk:** Strategies backtest or trade on randomly generated candle data thinking it's real.
- **Effort:** 3–5h

## C6. `importlib.reload()` in strategy hot-reload is unsafe
- **File:** `runtime/registry.py:74–80`
- **Root cause:** `importlib.reload(module)` does not reload dependencies, leaves stale references, and can cause `__del__` / circular import issues. Old instances may reference old code. State corruption is likely.
- **Fix:** Use a proper plugin hot-reload mechanism (e.g., `exec` in a restricted namespace, or require a full process restart). Remove the `reload()` capability or sandbox it.
- **Risk:** Strategy reload silently produces undefined behavior, hard-to-debug state corruption.
- **Effort:** 6–10h for a proper plugin sandbox

## C7. No deduplication in subscriber lists — duplicate callbacks accumulate
- **File:** `market/data_socket.py:63–66`
- **Root cause:** `subscribe()` uses `list.append()` with no dedup. If `subscribe(symbol, cb)` is called twice with the same callback, the callback runs twice per tick. No protection against double-registration by naive callers.
- **Fix:** Use `set[Callable]` instead of `list[Callable]`, or check for existence before appending.
- **Risk:** Strategies receive duplicate ticks → double signals → duplicate orders.
- **Effort:** 30 min

## C8. Slow tick callback blocks ALL symbol delivery
- **File:** `market/data_socket.py:81–89`
- **Root cause:** `broadcast_tick` iterates callbacks **sequentially** and `await`s each async callback. If alert_checker.py's `_check_alerts` (which does a DB query per tick) is slow, every symbol's tick delivery is blocked.
- **Fix:** Use `asyncio.gather()` or `asyncio.create_task()` for independent callbacks. Add a per-callback timeout. Consider a bounded callback queue for backpressure.
- **Risk:** One slow subscriber starves all others. Tick processing latency grows linearly with subscriber count × slowest subscriber.
- **Effort:** 4–6h

## C9. Alert checker blocks the broadcast chain with DB queries on every tick
- **File:** `market/alert_checker.py:14–23`
- **Root cause:** `_check_alerts` runs a DB query (`safe_execute` is likely sync HTTP) on **every tick** for every symbol. At 1000 ticks/sec, this is 1000 DB queries/sec. The callback is subscribed under `"*"`, blocking every tick for every symbol.
- **Fix:** (1) Batch alert checking — buffer ticks and evaluate every 1–2s. (2) Move alert rules to an in-memory cache with periodic DB sync. (3) Use an alert-specific queue with bounded processing.
- **Risk:** DB overload, event loop blocking, cascading failure across all market data delivery.
- **Effort:** 6–8h

## C10. MarketCache TTL-only eviction causes unbounded memory growth
- **File:** `market/cache.py:34–56`
- **Root cause:** `put_tick()` inserts into `_ticks` dict with TTL but entries are only cleaned during `get_tick()` / `get_all_ticks()` reads. If users only `put` and never `get`, memory grows unboundedly. Same for `_quotes`, `_option_chains`, `_expiry_list`.
- **Fix:** Add a background TTL sweep task (runs every 60s). Add a maximum entry cap per cache. Use `OrderedDict` with LRU eviction for all caches.
- **Risk:** Memory OOM in long-running deployments, especially during market hours with no reader.
- **Effort:** 3–5h

---

# HIGH (Fix within first sprint)

## H1. Subscriber callback list grows unboundedly — subscription memory leak
- **File:** `market/subscription_manager.py:47–51`
- **Root cause:** Each `subscribe()` call adds a callback to `_subscriptions[symbol]` set (set is fine), but `shared_socket.subscribe()` uses a list. If strategies register/unregister repeatedly, callback references accumulate.
- **Risk:** Memory leak proportional to strategy restarts.
- **Effort:** 2h

## H2. Reconnection causes message loss with no replay mechanism
- **File:** `market/subscription_manager.py:67–88`
- **Root cause:** When a broker feed disconnects and reconnects, there is zero buffering. All ticks during the reconnection window (seconds to minutes with exponential backoff) are lost. No sequence numbers, no gap detection.
- **Fix:** Add a tick sequence counter per symbol. On reconnect, request "from sequence N+1". Buffer missed ticks in Redis. Alert on detection of gaps.
- **Risk:** Strategies miss price movements during reconnection → wrong signals.
- **Effort:** 8–12h

## H3. TOCTOU race condition on order deduplication
- **File:** `engine/gate.py:218–231`
- **Root cause:** `client_order_id` dedup check (`SELECT ... eq("client_order_id", ...)`) followed by insert is not atomic. Two concurrent requests with the same `client_order_id` can both pass the check. `on_conflict` is not used here.
- **Fix:** Use Supabase's `upsert` with `on_conflict=["client_order_id"]` and check the result. Or use a DB-level unique constraint and catch the duplicate error.
- **Risk:** Duplicate orders placed in production.
- **Effort:** 3–5h

## H4. Missing `broker` filter in token refresh update — cross-contamination
- **File:** `engine/token_refresh.py:56`
- **Root cause:** `safe_update("broker_credentials", update_data, "user_id", user_id)` updates **ALL** rows for that `user_id` regardless of `broker`. A user with Fyers + Zerodha will have both brokers' tokens overwritten with the latest refresh result.
- **Fix:** Add `.eq("broker", broker)` filter before update.
- **Risk:** Corrupted broker credentials cause auth failures for the non-refreshed broker.
- **Effort:** 30 min

## H5. `RuntimeMetrics._latencies` list grows unboundedly
- **File:** `runtime/observability.py:22`
- **Root cause:** No maxlen on `_latencies`. Every strategy evaluation appends a float. Over hours of operation with hundreds of strategies, this grows to millions of entries.
- **Fix:** Use `collections.deque(maxlen=10000)` or use a probabilistic sketch (e.g., TDigest) for latency percentiles.
- **Risk:** Memory exhaustion in long-running processes.
- **Effort:** 1–2h

## H6. `MarketMetrics._latencies` uses O(n) pop(0) — unbounded
- **File:** `market/observability.py:39–41`
- **Root cause:** Same as H5 but `pop(0)` on a list is O(n). At 1000 ticks/sec, this becomes a performance bottleneck.
- **Fix:** Use `collections.deque(maxlen=1000)`.
- **Risk:** Latency calculation becomes O(n²) over time, degrading performance.
- **Effort:** 30 min

## H7. `on_tick` in scheduler iterates all strategies sequentially per tick
- **File:** `runtime/scheduler.py:54–62`
- **Root cause:** For every tick, `on_tick` loops through ALL registered EVERY_TICK strategies and awaits each callback. With 50 strategies, 1000 ticks/sec becomes 50K sequential callback executions/sec.
- **Fix:** Use `asyncio.gather()` for independent callbacks. Add a bounded semaphore to control concurrency.
- **Risk:** Tick processing falls behind, latency grows unboundedly.
- **Effort:** 3–5h

## H8. Fire-and-forget tasks are never tracked — silent failures
- **File:** `runtime/scheduler.py:89,93,97,113,116`
- **Root cause:** `asyncio.create_task(self._run_callback(...))` creates orphaned tasks. If a callback hangs (e.g., waiting on a slow API), the task is never cancelled, never garbage collected, and `active` flag never resets.
- **Fix:** Track all created tasks in a dict keyed by `sid`. Cancel and clean up in `unregister()`. Add a task timeout.
- **Risk:** Orphaned tasks accumulate, event loop leaks, schedulers eventually stall permanently.
- **Effort:** 4–6h

## H9. Emergency stop during market close is sequential, not concurrent
- **File:** `runtime/manager.py:345–347`
- **Root cause:** `_on_market_close` iterates `self._configs` and `await`s each `stop_strategy` sequentially. If any strategy's `on_stop()` hangs (DB write, API call), the market close loop blocks indefinitely.
- **Fix:** Use `asyncio.gather()` with a timeout per strategy. Force-kill stragglers after 30s.
- **Risk:** Market close signal delayed for all strategies. Positions left open overnight.
- **Effort:** 2–4h

## H10. Strategy evaluation has no isolation — one crash can take down others
- **File:** `runtime/manager.py:180–224`
- **Root cause:** `evaluate()` runs in the caller's context. If a strategy raises an exception, the error propagates but other strategies are not isolated. There's no per-strategy exception boundary or resource quota.
- **Fix:** Each strategy evaluation should run in a `asyncio.Task` with its own timeout. A crash should not affect other strategies' tick delivery.
- **Risk:** Buggy strategy halts evaluation for all strategies.
- **Effort:** 6–10h

## H11. SymbolMaster `_cache` grows unboundedly
- **File:** `market/symbol_master.py:282–290`
- **Root cause:** `get_broker_symbol()` caches results in `_cache` dict with no eviction strategy. Over time with diverse symbol lookups, memory grows unboundedly.
- **Fix:** Add LRU eviction (e.g., `@lru_cache(maxsize=10000)` or OrderedDict). Or use Redis TTL cache.
- **Risk:** Memory exhaustion.
- **Effort:** 1–2h

---

# MEDIUM (Fix within first month)

## M1. `threading.Lock` used in asyncio context — blocks event loop
- **File:** `runtime/observability.py:8`
- **Root cause:** `threading.Lock` is a blocking lock. Using `with self._lock:` in an async method blocks the event loop thread.
- **Fix:** Use `asyncio.Lock()`.
- **Risk:** Event loop stalls on hot metric recording paths (strategy evaluation).
- **Effort:** 30 min

## M2. Duplicate scheduler instances
- **File:** `engine/scheduler.py:97` + `runtime/scheduler.py:146`
- **Root cause:** Two separate scheduler classes (`ISTScheduler`, `RuntimeScheduler`) running independently. Both share no state. Both have overlapping responsibilities (market open/close, minute-based triggers).
- **Fix:** Consolidate into one scheduler. `ISTScheduler` appears to be unused or should be removed.
- **Risk:** Double execution of scheduled tasks, conflicting state.
- **Effort:** 4–6h

## M3. No jitter in reconnection backoff — thundering herd
- **File:** `market/subscription_manager.py:84`
- **Root cause:** `delay = min(2 ** backoff, self._max_backoff)` has no random jitter. Multiple feeds disconnecting simultaneously all reconnect at the same times.
- **Fix:** Add `random.uniform(0, delay * 0.5)` jitter.
- **Risk:** Stampede on broker APIs at reconnect boundaries.
- **Effort:** 30 min

## M4. Market status holiday sync is racy
- **File:** `market/status.py:102–123`
- **Root cause:** `sync_holidays()` writes `self._holidays` while `is_market_open()` / `_is_holiday()` reads it. No lock or atomic swap.
- **Fix:** Use `asyncio.Lock` or do an atomic swap (`new_holidays = ...; self._holidays = new_holidays` — Python's GIL makes this safe for assignments, but the list mutation is not).
- **Risk:** `is_market_open()` returns wrong value during sync → strategies operate on a holiday.
- **Effort:** 1h

## M5. Simulator produces unrealistic data (no validation, uniform noise)
- **File:** `market/simulator.py:63–91`
- **Root cause:** Price changes use `random.uniform(-0.003, 0.003)` (uniform distribution, not geometric). Bid can exceed ask (random generation). Volume and OI are random with no correlation to price. Tick generation rate is `random.uniform(0.5, 1.5)` sec regardless of market state.
- **Fix:** (1) Validate bid < ask, non-negative prices. (2) Use log-normal returns. (3) Correlate volume with absolute returns. (4) Add market hours awareness.
- **Risk:** Strategy developers overfit to unrealistic patterns that don't generalize.
- **Effort:** 4–6h

## M6. TickBuffer uses O(n) pop(0)
- **File:** `market/types.py:23`
- **Root cause:** `self._ticks.pop(0)` on a list is O(n). At high tick rates, this becomes a bottleneck.
- **Fix:** Use `collections.deque(maxlen=self._maxlen)`.
- **Effort:** 30 min

## M7. Historical data interval parsing can raise ValueError
- **File:** `market/historical.py:140–153`
- **Root cause:** `_parse_interval_minutes` uses `int()` conversion that can raise if the input is malformed (e.g., user sends "abc"). Raised value propagates to caller.
- **Fix:** Wrap in try/except, return a safe default (15).
- **Effort:** 30 min

## M8. OptionChainEngine returns synthetic data with no flag
- **File:** `market/option_chain.py:43–46`
- **Root cause:** When NSE fetch fails, `_generate_option_chain()` creates random data. No indication that data is synthetic. Same cache key used for both real and synthetic.
- **Fix:** Add `"source": "synthetic"` or `"source": "nse"` to returned data. Never cache synthetic data.
- **Effort:** 1–2h

## M9. SymbolMaster CSV parsing loads entire file into memory
- **File:** `market/symbol_master.py:78,109,140`
- **Root cause:** `client.get(url)` followed by `.text` loads 100MB+ CSV files entirely into memory. No streaming.
- **Fix:** Use `httpx` streaming response to process lines incrementally.
- **Risk:** OOM on concurrent syncs.
- **Effort:** 3–5h

## M10. Per-row upsert in symbol sync → thousands of DB calls
- **File:** `market/symbol_master.py:55,99,130,161,271`
- **Root cause:** Each symbol is upserted individually. For 2000+ symbols, this is 2000+ round trips to Supabase.
- **Fix:** Batch upsert (Supabase supports `.upsert()` with a list of rows using `upsert_all`).
- **Effort:** 2–4h

---

# LOW (Address as tech debt)

## L1. `get_ltp()` returns 0.0 indistinguishable from valid ₹0 price
- **File:** `market/adapter.py:49`
- **Fix:** Return `None` on failure, or use `Optional[float]`.
- **Effort:** 30 min

## L2. No unsubscribe mechanism for RuntimeEventSubscriber
- **File:** `runtime/event_subscriber.py:17`
- **Fix:** Add an `unsubscribe()` method.
- **Effort:** 30 min

## L3. Square-off scheduler logs but doesn't execute
- **File:** `engine/scheduler.py:79–94`
- **Fix:** Either implement the square-off execution or remove dead code.
- **Effort:** 2h

## L4. MarketDataAdapter.get_option_chain stub always returns None
- **File:** `market/adapter.py:59–60`
- **Fix:** Either implement or raise `NotImplementedError`.
- **Effort:** 30 min

## L5. `_init_strategy_health` writes heartbeat once — no periodic health check
- **File:** `runtime/manager.py:326–335`
- **Fix:** Add a periodic heartbeat loop per strategy (every 60s) to detect stalled strategies.
- **Effort:** 3–5h

## L6. Silent `except: pass` throughout SymbolMaster
- **File:** `market/symbol_master.py:56,101,132,163,183,200,274`
- **Fix:** Log warnings with error details.
- **Effort:** 1h

## L7. `RuntimeEventSubscriber._on_execution_event` is dead code
- **File:** `runtime/event_subscriber.py:27–28`
- **Fix:** Remove or implement.
- **Effort:** 15 min

## L8. Expression parser has no recursion depth limit
- **File:** `runtime/expression.py:182–215`
- **Fix:** Add max depth parameter (e.g., 50). Raise on nested depth exceeding limit.
- **Effort:** 1h

---

# Summary

| Severity | Count | Estimated Total Effort |
|----------|-------|----------------------|
| CRITICAL | 10    | ~38–60 hours         |
| HIGH     | 11    | ~35–53 hours         |
| MEDIUM   | 10    | ~19–29 hours         |
| LOW      | 8     | ~9–14 hours          |
| **Total**| **39**| **~101–156 hours**   |

**Top 5 priorities (order of execution):**
1. **C1 + C2** — RuntimeContext crashes / zero data (blocks ALL strategies)
2. **C4** — Sync HTTP in event loop (cascading latency across system)
3. **C5** — Synthetic cache poisoning (corrupts strategy decisions)
4. **H4** — Token refresh cross-contamination (can lock users out)
5. **C10 + H1 + H5 + H6** — Unbounded memory growth (OOM risk)
