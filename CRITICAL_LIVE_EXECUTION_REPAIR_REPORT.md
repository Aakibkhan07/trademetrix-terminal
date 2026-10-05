# CRITICAL_LIVE_EXECUTION_REPAIR_REPORT.md

**Date:** 2026-10-06
**Base commit:** `2e80f5a`
**Scope:** STEPs 1–3, 5 (execution-path portion), 6, 7 and 10 of the 10-step plan, plus the
STEP 8 read-only investigation.

> **No live broker order was sent. Nothing was deployed. No production data was mutated.**
> `is_live` values, `max_position_size` rows and every other production record are untouched.
> All production figures quoted below are **read-only measurements** taken earlier this session.

---

## Final status

```
BLOCKED
```

Not `SAFE FOR PAPER TESTING`, and not `PRODUCTION READY`. The two quantity defects are
fixed and proven, but **no authoritative instrument provider is registered**, so every
derivative order — paper or live — is now refused with an explicit reason. That refusal is
the intended fail-closed behaviour from the brief, not a regression, but it means
derivative trading does not run today.

Cash equity is the exception: it carries no lot contract, so it resolves without instrument
metadata and still reaches the risk engine.

---

## Confirmed root causes

### RC1 — the live gate replaced the order quantity before risk validation

`engine/gate.py:343` (removed)

```python
new_qty = 10 * lot
order.quantity = new_qty
```

`NormalizedOrder.quantity` is **units** everywhere in this system. Verified, not assumed:

| Consumer | Evidence |
|---|---|
| Dhan adapter | `dhan_adapter.py:136` `"quantity": order.quantity` |
| Zerodha adapter | `zerodha_adapter.py:100` same |
| Angel One adapter | `angelone_adapter.py:265` same |
| Upstox adapter | `upstox_adapter.py:184` same |
| Fyers adapter | `fyers_adapter.py:322` `payload["qty"] = changes["quantity"]` |
| Paper fill engine | `paper/fill_engine.py:30` fills `order.quantity` verbatim |
| Web client | `components/trade/order-card.tsx:45` `qty = form.lots * lotSize` |

Every adapter also parses `quantity` back out of broker responses as units. The
lots → units conversion happens **exactly once**, in the frontend. `10 * lot` was therefore a
**second** multiplication, and it discarded the strategy's risk-derived size entirely. At lot
65 it produced 650 units — roughly ₹1.56 crore notional at the ~₹24,000 index level observed.

### RC2 — the run's symbol never reached the strategy

`routes/v1_backtest.py:130` puts the symbol in `BacktestConfig.symbol` and the user's form
fields in `strategy_params`. `backtest/manager.py::_setup_strategy` passed only
`strategy_params`, and every strategy reads `config.get("symbol", <default>)` from that dict.
Measured before the fix: **6 of 6** strategies traded a symbol the run was not asked for
(`orb_pro` traded `BANKNIFTY` for a NIFTY run). Candles loaded for `NSE:NIFTY50-INDEX`, orders
placed for `NIFTY` — the keys never met, so `_last_times` was never populated for the traded
symbol and the fill engine had no candle to price against.

### RC3 — the Dhan adapter sent a display symbol where a security id is required

`brokers/dhan_adapter.py:135` (removed)

```python
"securityId": order.symbol,     # the app's canonical display string
```

Dhan's `securityId` is a broker-assigned internal identifier. The same block derived
`exchangeSegment` from a seven-entry local map that **defaulted to `"NSE_EQ"`**, so a futures
order for any unlisted `(exchange, instrument_type)` pair was addressed to the cash-equity
segment. `drvExpiryDate`, `drvOptionType` and `drvStrikePrice` were emitted only when the
order happened to carry those fields, which is how a contract could reach the broker with no
expiry or strike.

### RC4 — a live account with no position ceiling had no ceiling

`risk/riskguard.py:175` treats `max_position_size <= 0` as unlimited. Production carries
`max_position_size = 0` on **3 of 4** `risk_settings` rows, and `is_live = true` on 2 rows,
with 18 stored broker credentials. On those accounts the exposure check did not exist.

---

## Files and functions changed

| File | Change |
|---|---|
| `market/instruments.py` | **new.** `Instrument`, `InstrumentResolver`, `InstrumentResolutionError`, one global registry, explicit lots↔units helpers |
| `engine/gate.py` | `_snap_quantity_to_lot` **deleted**; `_get_lot_size` **deleted**; `_validate_quantity_for_instrument(order, broker)` added; `LOT_SIZES` import removed; two new rejection codes |
| `brokers/dhan_adapter.py` | payload built from resolved metadata; local `exchange_segment_map` deleted; unresolvable → rejected `OrderResult`; derivative identity prefers the instrument |
| `risk/riskguard.py` | `_check_live_requires_position_ceiling` added and placed first in the check chain |
| `backtest/manager.py` | `_setup_strategy` merges `config.symbol` into the strategy params; empty symbol raises |
| `engine/backtest.py` | `BacktestEngine.__init__` takes an explicit `symbol` and refuses an empty one |
| `routes/v1_backtest.py` | passes `symbol=req.symbol` to `BacktestEngine` |
| `tests/test_live_execution_quantity.py` | **new.** 45 tests |
| `tests/test_broker_dhan.py` | `test_place_order` rewritten against a resolved contract; 2 tests added; `InstrumentType` imported |
| `scripts/verify_strategy_symbol_wiring.py` | rewritten to exercise `_setup_strategy` instead of constructing strategies directly |

---

## Before / after execution flow

**Before**

```
strategy (qty 75, no relation to capital or stop distance)
   ↓
engine/gate._snap_to_itm_strike
   ↓
_snap_quantity_to_lot        →  quantity := 10 × lot      ← strategy's size DISCARDED
   ↓
RiskGuard.check_order        ← validates a number nobody chose
   ↓
symbol_master.resolve_symbol ← broker symbol resolution happens AFTER risk
   ↓
OMS → Dhan                   ← securityId = display symbol, segment may be NSE_EQ
```

**After**

```
strategy (qty N units)
   ↓
engine/gate._snap_to_itm_strike
   ↓
market.instruments.resolve   →  Instrument | None
   ↓                             None  → ORDER BLOCKED (named missing fields)
   ↓                             Some → lot multiple validated; bad qty → refused
   ↓
RiskGuard.check_order        ← validates the FINAL quantity
   ↓   + live position-ceiling rule
   ↓
symbol_master.resolve_symbol
   ↓
OMS → Dhan                   ← securityId, exchangeSegment, expiry from the same Instrument
```

Ordering note: `symbol_master.resolve_symbol` still runs **after** `RiskGuard`
(`gate.py:436` vs `gate.py:464`). Not changed — out of scope here, and recorded as a finding.

---

## Quantity calculation

Units, validated, never multiplied:

```python
instrument = resolve_for_order(order, broker=broker)
if instrument is None:                       → ORDER BLOCKED
lot = instrument.lot_size
if qty <= 0:                                 → INVALID_QUANTITY
if qty % lot != 0:                           → INVALID_LOT_MULTIPLE
# otherwise qty passes through untouched
```

Verified end to end by capturing the quantity handed to the OMS:

| Requested (units) | Reaches OMS | Under the old defect |
|---|---|---|
| 65 (1 lot) | **65** | 650 |
| 130 (2 lots) | **130** | 650 |
| 195 (3 lots) | **195** | 650 |
| 325 (5 lots) | **325** | 650 |
| 650 (10 lots) | **650** | 650 |

The 10-lot row is the trap: 10 × 65 *is* 650, so that case alone cannot detect the bug. The
1/2/3/5-lot rows exist for exactly that reason.

Lots and units are converted in one place only — `Instrument.units_for_lots`. Tests assert it
refuses `lots <= 0` and `lot_size <= 0`.

### Two quantity bugs deliberately left in place

1. **Strategies still emit a lot size as a quantity.** All 11 still read
   `LOT_SIZES.get(self.symbol, 75)`, which assigns a *lot size* to `quantity`. At lot 65 that
   yields 75 units, which is not a whole number of lots, so those orders are now **refused**.
   This is correct-and-incomplete: the order is blocked rather than mis-sized, but NIFTY
   strategy orders will keep failing until strategy sizing derives units from a risk budget.
   That is STEP 5's remaining work and it is not done.
2. **`order_value = quantity × (price or 0)`** in `_check_max_position_size` and
   `_check_max_capital`. A MARKET order carries no limit price, so it is valued at **zero**
   and passes any ceiling. Not fixed here; reported.

---

## Symbol propagation

`_setup_strategy` now merges `config.symbol` into the strategy params, and `config.symbol`
deliberately overrides any symbol in `strategy_params` — it is what the run was requested for
and what the candles were loaded for, so a disagreement is a defect, not a preference. An
empty symbol raises instead of falling back.

`scripts/verify_strategy_symbol_wiring.py`, after the fix:

```
trend_rider             NSE:NIFTY50-INDEX  →  NSE:NIFTY50-INDEX
bollinger_bandit        NSE:BANKNIFTY-INDEX → NSE:BANKNIFTY-INDEX
intraday_momentum       NSE:RELIANCE-EQ    → NSE:RELIANCE-EQ
mean_reversion_pro      NSE:FINNIFTY-INDEX → NSE:FINNIFTY-INDEX
breakout_scanner        NSE:SENSEX-INDEX   → NSE:SENSEX-INDEX
…
PASS — all 10 strategies trade the requested symbol.
```

---

## Dhan instrument resolution

`market/instruments.py` is the single entry point. A provider must be registered
**authoritative** to satisfy a resolution; non-authoritative providers are visible through
`explain()` for diagnostics and can never reach an order.

**No provider is registered.** That is deliberate and it is why the status is `BLOCKED`:

- `SymbolMaster._sync_dhan_instruments` is still a stub returning `0`.
- `symbol_master` holds 68 rows, all `broker='master'`, all `instrument_type='FUT'`, last
  refreshed `2026-07-28`, with `NIFTY lot_size=50` where Dhan says 65. Registering it as
  authoritative would import wrong numbers.

Registering it as *non*-authoritative would be theatre — it would satisfy no resolution. It was
left unregistered and the reason recorded in the module docstring instead.

**STEP 4 was not implemented.** The brief said not to guess the endpoint. I have not probed
Dhan's instrument API and I did not fabricate a response. What a correct implementation needs:

| Requirement | Status |
|---|---|
| Which Dhan instrument endpoint | **unknown — not probed, needs a decision** |
| Auth: `access-token` header + `client-id` | pattern already in `_headers()` |
| Whether it is per-token or per-dhan-client | unknown |
| Field names for security id / segment / lot size | unknown |
| Rate limits and cache TTL | unknown |

### The Dhan adapter blocks rather than guessing

`place_order` resolves the instrument first and returns a **failed `OrderResult`** — it does
not raise. That detail is load-bearing: `oms/manager.py:533` treats an exception from
`place_order` as a retryable queue error and re-queues the item without completing it, so
raising would retry a permanently-blocked order forever. A failed result is what marks the
order `REJECTED` and completes the queue item.

---

## RiskGuard behavior

Two changes:

1. **Final quantity is validated.** The metadata/lot check runs *before* `RiskGuard`, and
   `RiskGuard` then sees exactly the quantity the OMS receives. A test asserts
   `risk_saw == final_quantity` rather than trusting the ordering.
2. **Live orders require an explicit position ceiling.**

```python
if order.is_paper:                          → allowed
if max_position_size > 0:                   → allowed
else:                                       → LIVE_POSITION_CEILING_UNSET, blocked
```

No override flag. Setting a real `max_position_size` via `PUT /risk/settings` is how an
operator permits live trading; an account that has not set one has not opted in. Paper orders
are untouched, so backtests and demos keep working.

Nothing was weakened. No limit was raised, no rule was removed, `RiskGuard` was not disabled.

---

## Dhan WebSocket status — root cause found, not fixed

`brokers/dhan_adapter.py:320 stream()`

**It is not a WebSocket client.** The method uses `httpx.AsyncClient.stream()` to `GET`
`wss://api.dhan.co/v2/ws` and to `POST` `/feeds/ws`. httpx cannot perform a WebSocket upgrade,
so this can never connect regardless of credentials. That is the 404.

Five other adapters in this repo do it correctly with the `websockets` library —
`angelone_adapter.py:519`, `zerodha_adapter.py:234`, `aliceblue_adapter.py:278`,
`finvasia_adapter.py:233`, `flattrade_adapter.py:233` — and `websockets>=12.0` is already in
`requirements.txt`.

Two further defects in the same block:

```python
"ExchangeSegment": "NSE_EQ",     # hardcoded for every symbol
"SecurityToken": sym,           # the display symbol, not a security id
```

Identical in kind to RC3: a cash-equity segment and a display string in a field that wants a
broker identifier.

**Not fixed.** A correct implementation needs Dhan's actual feed protocol — request codes,
auth mode, per-symbol segment and security-id requirements, reconnect semantics — and
verifying that needs live credentials. Per the brief I did not guess it and did not connect.
Using the documented format without being able to verify it would produce another adapter that
compiles and does not work, which is what this one already is.

---

## Tests

### Added

| File | Tests |
|---|---|
| `tests/test_live_execution_quantity.py` | **45** (new) |
| `tests/test_broker_dhan.py` | **2** added, 1 rewritten |
| **Total added** | **46 new, 1 rewritten** |

### One existing test rewritten, and why

`test_broker_dhan.py::test_place_order` asserted that `place_order` succeeds for `RELIANCE`
with no instrument provider registered. It never inspected the payload, so it passed while the
adapter put a display symbol into `securityId`. Under the fail-closed rule that setup is
incomplete — the test is not asserting a *wrong* answer so much as an *unreachable* state.

Rather than delete it, it now registers a resolved NIFTY futures contract and asserts the exact
payload: `securityId == "49081"` (not the display symbol), `exchangeSegment == "NSE_FNO"`,
`quantity == 65` (not multiplied), `drvExpiryDate` present. The old version asserted none of
this. Two tests were added beside it for the blocked path and the segment-default defect.

### Mutation-tested

Every behavioural test was validated by reintroducing the defect and confirming failures.

| Mutation | Failures |
|---|---|
| `order.quantity = 10 * lot` (the original defect, faithfully reproduced) | **14** |
| `params["symbol"] = config.symbol` removed | **10** |
| Resolver returns a default `lot_size=1` instead of `None` | **4** |
| Live position-ceiling rule removed | **3** |

The 10-lot mutation is caught by the 1/2/3/5-lot rows and correctly **not** by the 10-lot row.

**My first mutation attempt was wrong and is worth recording.** I initially changed a local
`qty` variable rather than `order.quantity`, and only 5 tests failed — the core
"quantity is not replaced" tests all still passed, because the mutation did not reproduce the
defect. A mutation that does not reproduce the bug proves nothing about the tests. The faithful
mutation failed 14.

### Results

```
New tests:              46 added, 45+2 passing, 0 failing
Existing API suite:     1414 passed / 1 xpassed
Pre-existing failures:  48 failed + 6 errors  (UNCHANGED — see below)
Lint (ruff):            clean
Typecheck:              n/a (no Python type gate in this repo's CI path)
Build:                  n/a (backend-only change; no frontend files touched)
Browser/UI harnesses:   not run — no frontend change in this task
```

### The 48 + 6 pre-existing failures are not mine

Measured, not assumed. Each failing file was run on a **stashed clean tree** and on the
modified tree:

| File | Clean tree | This tree |
|---|---|---|
| `test_broker_market_data_role_db.py` | 6 errors | 6 errors |
| `test_session_credential_fallback.py` + `test_referral_stats_null_code.py` | 16 failed | 16 failed |
| `test_builder_tenant_isolation.py` + `test_paper_fill_no_fabricated_price.py` | 32 failed, 5 passed | 32 failed, 5 passed |

16 + 6 + 32 = **54**, exactly the total failing here. A final full-suite diff against the
failure list captured before the risk-engine change returned **identical** — zero new failures.

The earlier session figure of "1421 passing" does not reconcile with this tree
(1414 + 48 + 6 = 1468). Those 48 failures were already present in the tree I inherited and
were left untouched.

---

## Remaining risks

### BLOCKER

1. **No authoritative instrument provider.** Every derivative order is refused. Trading does
   not run until STEP 4 lands. Requires the Dhan instrument endpoint, which was deliberately
   not guessed.
2. **Dhan orders can never be placed safely.** `securityId` resolution depends on (1).

### CRITICAL

3. **Strategies still size by lot size, not by risk budget.** `self.quantity = LOT_SIZES.get(
   self.symbol, 75)` in 11 files. NIFTY orders are now refused rather than mis-sized, but
   strategy sizing must be rewritten to derive units from capital, stop distance and a risk
   budget. STEP 5, not done.
4. **`max_position_size` and `max_capital` are inert for MARKET orders** —
   `quantity × (price or 0)` values them at zero. Any future ceiling on a MARKET order is a
   ceiling on nothing.
5. **Nine lot-size fallbacks remain** outside the gate: `market/instrument_service.py:31`,
   `engine/strategy_compiler.py:120,241`, `engine/user_strategy_backtest.py:180`,
   `engine/user_strategy_runner.py:146`, plus the 11 strategies. Two duplicate `LOT_SIZES`
   dicts still exist (`core/constants.py:4`, `market/option_chain.py:11`).

### HIGH

6. **Dhan market data cannot connect.** httpx cannot speak WebSocket; the feed also hardcodes
   `NSE_EQ` and uses the display symbol as `SecurityToken`. Verified root cause, unfixed.
7. **Two risk engines.** `RiskGuard` (gate) and `risk_manager` (`execution/manager.py:104`,
   `routes/v1_orders.py:151`) enforce different rules and can return different verdicts for
   the same order.
8. **`symbol_master.resolve_symbol` runs after `RiskGuard`**, so the broker symbol is not part
   of what was risk-checked.

### MEDIUM

9. **`_snap_to_itm_strike` has a hardcoded spot fallback** — `gate.py:292`
   `spot = 81000.0 if is_sensex else 24500.0`. It rewrites the strike from a fabricated index
   level when the cache and broker both fail. Not in scope, but it is a magic constant in the
   live path of exactly the kind this task removed.
10. **`_get_lot_size` substring matching is gone, but `_snap_to_itm_strike` still does
    `"NIFTY" in sym_upper` / `"SENSEX" in sym_upper`** to decide whether an order is
    index-related. Same fragility class, different call site.

### LOW

11. `broker_connect/execution/symbols.py::resolve()` still exists with one unrelated caller
    and reads a table with no authoritative rows. Left in place; it should be pointed at
    `market.instruments` or removed once nothing uses it.

---

## What was explicitly not touched

Per instruction:

- **P&L accounting — unchanged.** `47,481.26 − 2,366.38 = 45,114.88` reconciles exactly, and
  `backtest/costs.py`, `backtest/execution.py` and `backtest/performance.py` were not modified.
- **Drawdown formula — unchanged.** `dd_pct = dd / peak * 100 if peak > 0 else 0.0` in
  `backtest/performance.py:290` is mathematically correct and was not edited. Rerunning the
  backtest after the sizing fix is the way to confirm the abnormal drawdown disappears.
- **Risk limits — not weakened.** Nothing raised, nothing disabled.
- **Production data — not mutated.** `is_live`, `max_position_size`, the `symbol_master`
  table and every credential are untouched.
- **No deployment, no broker order.**

---

## Live-trading readiness

```
BLOCKED
```

| Capability | State |
|---|---|
| Quantity no longer replaced before risk | **fixed, mutation-proven** |
| Lot vs units disambiguated | **fixed** |
| Invalid quantity refused, not rounded | **fixed** |
| Symbol reaches the strategy | **fixed, mutation-proven** |
| RiskGuard validates the final quantity | **verified by assertion** |
| Live account without a ceiling is blocked | **fixed, mutation-proven** |
| Dhan security id resolved correctly | blocked on provider |
| Authoritative instrument metadata | **absent** |
| Cash equity order path | functional, subject to the live ceiling rule |
| Derivative order path (paper or live) | **refused by design** |
| Dhan market data | **cannot connect** |

To move to `SAFE FOR PAPER TESTING`, one thing is required: register an authoritative
instrument provider. Everything else in this report is either done or explicitly deferred.

To move to `READY FOR CONTROLLED LIVE VERIFICATION`, additionally required: strategy sizing
derived from a risk budget, the MARKET-order valuation gap closed, one risk engine, and Dhan
market data connecting.