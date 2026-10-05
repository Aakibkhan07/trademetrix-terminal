# LIVE_PATH_SAFETY_INSPECTION.md

**Scope:** read-only inspection of instrument-metadata resolution and position sizing on the
live execution path and the backtest path.
**Date:** 2026-10-05
**Commit inspected:** `c6a5343` (branch `main`)
**Production measured:** `148.135.138.27`, Supabase `db.nwutlfuowiulfpbsrldn`

> **No implementation was modified. Nothing was deployed. No broker order was sent.**
> Every number below was measured by reading the source, running a local read-only probe, or
> querying the production database read-only. Where a claim could not be verified it is marked
> `UNVERIFIED` rather than asserted.

---

## 0. Executive summary

| Question | Answer |
|---|---|
| Where does Dhan instrument data enter the system? | **Nowhere.** The Dhan instrument sync is a stub that logs a warning and returns 0. |
| Where is it stored? | It isn't. `symbol_master` holds 68 rows, **all tagged `broker='master'`**, none from Dhan. |
| How are symbols resolved? | Six unrelated mechanisms, no shared normaliser. |
| How are security IDs resolved? | **They are not.** The Dhan adapter sends the app's display symbol in the `securityId` field. |
| Where does lot size come from? | Two duplicate hardcoded dicts plus 6 ingestion paths; **nine different fallback defaults**. |
| Why does NIFTY fall back to 75? | The lookup key is `NSE:NIFTY50-INDEX`; the dict keys are `NIFTY`. They never match. |
| Does live execution have the same issue? | **Worse.** Live forcibly rewrites every non-equity order to `10 × lot` before risk validation. |
| Does backtest have the same issue? | Yes, plus a separate symbol-wiring defect that makes strategies trade a symbol they were never asked for. |

**The single most dangerous finding is not the fallback. It is that Dhan instrument data is
absent from the system entirely, while the Dhan adapter constructs order payloads from the
app's own display symbols.**

---

## 1. Where Dhan instrument data enters the system

### It does not.

`market/symbol_master.py:171`

```python
async def _sync_dhan_instruments(self) -> int:
    logger.warning("Dhan instrument sync not yet implemented")
    return 0
```

`_sync_zerodha_instruments` (line 175) is identical. The dispatcher at line 129 routes
`sync_broker_instruments("dhan")` into that stub, so the call succeeds and returns `0` — a
**silent no-op**, not an error. Any scheduler or admin action invoking it believes it synced.

The Dhan adapter itself (`brokers/dhan_adapter.py`) has **no instrument-master method at
all**. Its complete endpoint surface is:

```
POST   /v2/orders            GET/PUT/DELETE /v2/orders[...]
GET    /v2/positions
GET    /v2/holdings
GET    /v2/fundlimit
POST   /v2/marketfeed/...   (streaming)
GET    /v2/marketfeed/quote
POST   /v2/oauth/token
```

There is no instruments/scrip endpoint call anywhere in the file.

### What Dhan security IDs *are* used for

`securityId` appears in exactly three places, all of them **parsing an ID returned by Dhan**,
never resolving one:

| Line | Use |
|---|---|
| `dhan_adapter.py:400` | `_parse_instrument(item.get("securityId", ""))` on a **positions** response |
| `dhan_adapter.py:423` | same, on a **holdings** response |
| `dhan_adapter.py:455` | `_parse_instrument(sym)` on a quote |

So the adapter can decode a contract into strike/expiry/option-type
(`_parse_instrument`, line 476, regex `^([A-Z]+)(\d{2})([A-Z]{3})(\d+)(CE|PE)$`), but it can
never *look up* one. Resolution is inbound-only.

---

## 2. Where instrument metadata is stored

Table `symbol_master` (columns: `id, symbol, exchange, broker, broker_symbol, token,
instrument_type, expiry, strike, option_type, lot_size, tick_size, segment, last_updated`),
indexed on `(broker, exchange, symbol)`.

### Measured in production

```
total rows      : 68
by broker       : master = 68      ← dhan = 0, fyers = 0, zerodha = 0
instrument_type : FUT   = 68      ← nothing else, ever
last_updated    : 2026-07-28      ← 2.5 months stale
```

The five rows whose symbol matches `%NIFTY%` / `%SENSEX%`:

| symbol | broker | instrument_type | lot_size | Correct value |
|---|---|---|---|---|
| NIFTY | master | FUT | **50** | 65 (per Dhan) |
| BANKNIFTY | master | FUT | **15** | 30 |
| FINNIFTY | master | FUT | **40** | 60 |
| MIDCPNIFTY | master | FUT | **50** | 75 |
| SENSEX | master | FUT | **20** | 20 |

**These are not merely stale — they are wrong.** The lot sizes match neither the Dhan contract
nor the repo's own hardcoded constants. Nothing in the codebase ever reads these five rows for
lot size (see §6), which is why the wrongness has never surfaced.

### Every ingestion path that writes lot_size

| File:line | Source | Lot size | Fallback |
|---|---|---|---|
| `symbol_master.py:122` | NSE bhavcopy (equities) | **hardcoded `1`** | — |
| `symbol_master.py:161` | Fyers `NSE_CM.csv`, `parts[3]` | real (cash equity only) | `1` |
| `symbol_master.py:258` | NSE `fo-sec-list`, `item["lotSize"]` | **real** | `1` |
| `symbol_master.py:268` | same, `_fo_cache_put` | **real** | `1` |
| `symbol_master.py:307,348,373` | Fyers `NSE_FO.csv`, `parts[3]` | real | `1` |
| `symbol_master.py:405` | — | **hardcoded `1`** | — |
| `symbol_master.py:171` | **Dhan** | **stub — returns 0** | — |

Note that the NSE and Fyers F&O paths *do* carry real exchange lot sizes. That is why the
problem is invisible: correct data exists for F&O contracts, wrong data exists for indices, and
**the code reads none of it**.

---

## 3. How symbols are resolved

There is no symbol normaliser. Six independent mechanisms:

| # | Mechanism | Location | Behaviour |
|---|---|---|---|
| 1 | **Strategy fallback** | `strategies/*.py:16` etc. | `self.symbol = config.get("symbol", "NIFTY")` |
| 2 | Index alias map | `market/option_chain.py:15` `_INDEX_ALIASES` | `"NIFTY50-INDEX" → "NIFTY"` — **used by option_chain only, by no strategy** |
| 3 | Substring match | `engine/gate.py:328` `_get_lot_size` | `if "NIFTY" in s: ...` |
| 4 | Yahoo map | `providers/yahoo.py:19` | `"NSE:NIFTY50-INDEX" → "^NSEI"` |
| 5 | Fyers token map | `brokers/update_tokens.py:13` | `"NSE:NIFTY50-INDEX": "99926000"` |
| 6 | Exchange strip | e.g. `fivepaisa_adapter.py:473` | `clean = symbol.split(":")[-1]` |

Mechanism 3 is especially fragile: `"NIFTY" in s` matches `NIFTY`, `BANKNIFTY`, `FINNIFTY` and
`MIDCPNIFTY` alike. It is ordered so `BANKNIFTY` is tested first, which happens to work — but
any new symbol containing a substring silently inherits the wrong contract size.

### 3a. The NIFTY index vs NIFTY derivative distinction

The user asked whether an index symbol is being given a derivative lot size. **It is.**

`core/constants.py:4`

```python
LOT_SIZES: dict[str, int] = {"NIFTY": 65, "SENSEX": 20, "BANKNIFTY": 30,
                             "FINNIFTY": 60, "MIDCPNIFTY": 75}
```

The keys are **bare index names with no instrument-type qualifier**, and every consumer applies
them to derivatives — `engine/gate.py:_snap_quantity_to_lot` skips `InstrumentType.EQ` and
applies the index lot size to everything else:

```python
if order.instrument_type and order.instrument_type.value == "EQ":
    return False
lot = _get_lot_size(order.symbol)
```

So the index `NSE:NIFTY50-INDEX` (which is **not tradable** on NSE as an index instrument) and
NIFTY futures (tradable) are given the same number, and both are multiplied by 10. The
distinction the user asked for does not exist anywhere in the codebase.

---

## 4. How security IDs are resolved

**They are not resolved. They are substituted.**

`brokers/dhan_adapter.py:128`

```python
payload: dict = {
    "dhanClientId": self._client_id,
    "transactionType": self._map_side(order.side),
    "exchangeSegment": seg,
    "productType": self._map_product(order.product),
    "orderType": self._map_order_type(order.order_type),
    "validity": "DAY",
    "securityId": order.symbol,          # ← the app's display symbol
    "quantity": order.quantity,
    "afterMarketOrder": False,
}
```

`order.symbol` is the canonical app symbol — `NSE:NIFTY50-INDEX`, or whatever the strategy
produced (which, per §5, is often just `NIFTY`). Dhan's `securityId` for exchange instruments
is a broker-assigned internal identifier, not a trading symbol. The payload sends a display
string into a field that requires a broker ID.

Two further defects in the same block:

**Segment defaults to cash-equity.** Line 127:

```python
seg = exchange_segment_map.get((order.exchange, order.instrument_type), "NSE_EQ")
```

The map has seven entries. Anything outside them — including `Exchange.NSE` +
`InstrumentType.FUT`, a combination a strategy can readily produce — silently becomes
`NSE_EQ`. A future order is sent to the cash-equity segment with a wrong security ID. The
default is the *least* restrictive value rather than a rejection.

**Derivative identity is never assembled.** Lines 145–151 add `drvExpiryDate`,
`drvOptionType` and `drvStrikePrice` only when those fields happen to be already populated on
the order. No code path derives expiry or strike from a Dhan instrument master, because there
is no instrument master.

---

## 5. Why NIFTY currently falls back to 75

Three independent defects compound. Reproduced by
`apps/api/scripts/verify_strategy_symbol_wiring.py`.

### Defect A — the strategy is never told which symbol to trade

`routes/v1_backtest.py:130`

```python
config = BacktestConfig(
    strategy_type=req.strategy_type,
    strategy_params=req.strategy_params,   # user's form fields; empty by default
    symbol=req.symbol,                      # "NSE:NIFTY50-INDEX" lands HERE
    ...
)
```

`backtest/manager.py:_setup_strategy` → `strategy_cls(config.strategy_params)`.

Every strategy reads:

```python
self.symbol = config.get("symbol", "NIFTY")
```

`config` here is `strategy_params`. **`BacktestConfig.symbol` is never passed in.** Measured:

```
strategy                config.symbol       strategy.symbol
trend_rider             NSE:NIFTY50-INDEX   NIFTY          <-- MISMATCH
macd_cross              NSE:NIFTY50-INDEX   NIFTY          <-- MISMATCH
bollinger_bandit        NSE:NIFTY50-INDEX   NIFTY          <-- MISMATCH
rsi_mean_reversion      NSE:NIFTY50-INDEX   NIFTY          <-- MISMATCH
smc_sniper              NSE:NIFTY50-INDEX   NIFTY          <-- MISMATCH
orb_pro                 NSE:NIFTY50-INDEX   BANKNIFTY      <-- MISMATCH

6 of 6 strategies trade a symbol the run was not asked for.
```

Candles are loaded for `NSE:NIFTY50-INDEX`; the order is placed for `NIFTY`. Those keys never
meet, so `BacktestBroker._last_times["NIFTY"]` is never populated — which is why
`entry_time`/`exit_time` came back empty — and the fill engine has no candle at `NIFTY`.

### Defect B — the dict key can never match the symbol in use

`strategies/trend_rider.py:24` (identical in 10 other strategies)

```python
self.quantity = config.get("quantity", LOT_SIZES.get(self.symbol, 75))
```

`LOT_SIZES` keys are `NIFTY`, `BANKNIFTY`, … With Defect A, `self.symbol` is `"NIFTY"` and the
lookup **does** hit — returning 65. Where `strategy_params` does carry a symbol, e.g.
`NSE:NIFTY50-INDEX`, the lookup misses and returns **75**.

Measured both ways:

```
LOT_SIZES['NSE:NIFTY50-INDEX'] : ABSENT  -> falls back to 75
LOT_SIZES['NIFTY50-INDEX']     : ABSENT
```

So the answer to "why 75" is: **the key format does not match the symbol format the app uses
internally**, and the fallback fires. The system is right to distrust a default here, and wrong
to have one.

### Defect C — nine different fallback defaults

| Value | Sites |
|---|---|
| **75** | `trend_rider:24`, `macd_cross:16`, `bollinger_bandit:17`, `rsi_mean_reversion:16`, `smc_sniper:22`, `breakout_scanner:16`, `intraday_momentum:16`, `mean_reversion_pro:16`, `arbitrage_hunter:16` |
| **65** | `market/instrument_service.py:31`, `engine/strategy_compiler.py:120`, `:241`, `engine/user_strategy_backtest.py:180`, `engine/user_strategy_runner.py:146` |
| **40** | `strategies/gap_up_express.py:16` |
| **25** | `strategies/orb_pro.py:25` |
| **50** | `strategies/expiry_hunter.py:25` |
| **1** | every `symbol_master` ingestion path |
| **10 × lot** | `engine/gate.py:343` — a multiplier, not a default, but the same failure mode |

Two independent copies of the same dict exist: `core/constants.py:4` and
`market/option_chain.py:11`. They currently agree by coincidence; nothing enforces that.

---

## 6. Does live execution have the same issue

**Yes, and there is an additional defect that does not exist in the backtest path.**

### 6a. The live gate multiplies by 10 unconditionally

`engine/gate.py:343`

```python
def _snap_quantity_to_lot(order: NormalizedOrder) -> bool:
    if order.instrument_type and order.instrument_type.value == "EQ":
        return False
    lot = _get_lot_size(order.symbol)          # substring match on hardcoded constants
    if not lot or lot <= 1:
        return False
    qty = int(order.quantity or 0)
    if qty <= 0:
        return False
    new_qty = 10 * lot                        # ← every non-EQ order becomes 10 lots
    if qty == new_qty:
        return False
    logger.info("Lot enforce 10 lots: %s qty %s -> %s (lot %s x10)", ...)
    order.quantity = new_qty
    return True
```

The function name says "snap"; the behaviour is "replace". Whatever quantity the strategy
computed from its risk budget is discarded.

For NIFTY at lot 65: `10 × 65 = 650` units. At the index level observed in production
(~24,000) that is **₹1,56,00,000 notional**.

The user asked specifically whether quantity might be multiplied by lot size twice. It is
multiplied by **lot size and by 10**, and the strategy's own quantity — already sized in units
— is thrown away rather than converted from lots.

### 6b. Order of operations

`engine/gate.py:414–444`

```
414   await _snap_to_itm_strike(user_id, order)     # rewrite the strike
416   _snap_quantity_to_lot(order)                  # quantity := 10 × lot
418   riskguard = RiskGuard(user_id)
419   risk_check = await riskguard.check_order(order)
444   oms_order = await order_manager.place_and_wait(req, timeout=20.0)
```

**The ordering is correct** — `RiskGuard` at 419 does validate the post-snap quantity. That was
worth verifying and it holds. But risk is being asked to approve a number that was chosen
before any capital, stop-loss or risk budget was consulted.

### 6c. Two risk engines exist, and three of four accounts have position limits disabled

```
gate.py:419          RiskGuard.check_order()        ← the gate path
execution/manager.py:104   risk_manager.evaluate()  ← the platform /orders path
routes/v1_orders.py:151    risk_manager.evaluate()
```

Different classes, different rule sets, different state. The backtest path uses a third
(`backtest/risk.py::BacktestRiskSimulator`).

`RiskGuard` does implement the limits the user requires — `_check_max_position_size`,
`_check_max_open_positions`, `_check_max_daily_loss`, `_check_drawdown`,
`_check_max_capital`. But line 175 reads:

```python
if settings.max_position_size <= 0:
    return allowed        # 0 means "no limit"
```

Measured in production `risk_settings` (4 rows):

```
max_position_size = 0      ->  3 rows   (limit DISABLED)
max_position_size = 250000 ->  1 row
is_live = true             ->  2 rows
```

So for three of four accounts the exposure ceiling that would catch a ₹1.56 crore order
**does not exist**. The other account's ceiling (₹2,50,000) is below it — but the limit that
fires depends on which account the order runs under.

### 6d. Live credential population

```
zerodha 6 · fyers 4 · dhan 4 · upstox 2 · lemonn 1 · angelone 1
```

18 stored broker credentials, and 2 accounts have `is_live = true`. The path in §6a–6c is
reachable. **No order was placed to test it.**

---

## 7. Does the backtest path have the same issue

Yes, plus the symbol-wiring defect of §5A which the live path does not have (the live path
receives the symbol in the order itself).

Backtest-specific:

- `backtest/manager.py:_setup_strategy` passes `config.strategy_params` and drops
  `config.symbol`.
- Sizing uses the same `LOT_SIZES.get(symbol, 75)` as the strategies.
- `backtest/risk.py::BacktestRiskSimulator.check()` **does** enforce `MAX_QUANTITY`,
  `MAX_CAPITAL`, `MAX_EXPOSURE` and `MAX_SYMBOL_EXPOSURE` — the backtest risk engine is more
  complete than the live gate. It is validating the strategy's 75-unit order, so its
  protections are real but are checking the wrong quantity.

**Documented divergence, as requested:** backtest and live resolve instrument metadata through
entirely different mechanisms, and neither uses Dhan.

| | Backtest | Live |
|---|---|---|
| Lot size source | `core/constants.LOT_SIZES` (hardcoded) | `core/constants.LOT_SIZES` via substring match (hardcoded) |
| Quantity multiplier | none | `× 10` (`gate.py:343`) |
| Symbol into strategy | **dropped** | passed in the order |
| Risk engine | `BacktestRiskSimulator` | `RiskGuard` |
| Exposure cap enforced | yes (`MAX_EXPOSURE`) | only if `max_position_size > 0` — 3 of 4 accounts disabled |
| `symbol_master` consulted | no | no (`resolve()` has one unrelated caller) |

A backtest can therefore report a result the live path would never reproduce, in either
direction.

### 7a. The one resolver that does exist, and is not wired in

`broker_connect/execution/symbols.py:26`

```python
def resolve(broker: str, signal: Signal) -> tuple[str, int]:
    ...
    .select("broker_symbol, lot_size")
    .eq("broker", broker)
```

This reads `symbol_master` and returns `(broker_symbol, lot_size)` — the right shape for the
job. It has exactly **one** caller:

```
broker_connect/execution/engine.py:131    broker_symbol=to_broker_symbol(broker, signal)
```

`engine/gate.py` — the actual live execution path — does not import it. Per §2 the table it
reads has no Dhan rows and the wrong index lot sizes, so wiring it in as-is would import the
wrong numbers rather than the right ones.

---

## 8. Exact files and functions responsible

### Root cause

| File:line | Defect |
|---|---|
| `market/symbol_master.py:171` | `_sync_dhan_instruments` is a stub; Dhan is never ingested |
| `brokers/dhan_adapter.py` (whole file) | no instrument-master method; no security-ID resolution |
| `brokers/dhan_adapter.py:135` | `securityId` = display symbol |
| `brokers/dhan_adapter.py:127` | segment defaults to `NSE_EQ` |

### Live path

| File:line | Defect |
|---|---|
| `engine/gate.py:343` | `_snap_quantity_to_lot` — `new_qty = 10 * lot` |
| `engine/gate.py:328` | `_get_lot_size` — substring match, `None` on miss |
| `risk/riskguard.py:175` | `max_position_size <= 0` → allowed |
| `engine/gate.py:419` vs `execution/manager.py:104` | two risk engines |

### Backtest path

| File:line | Defect |
|---|---|
| `backtest/manager.py:_setup_strategy` | passes `strategy_params`, drops `config.symbol` |
| `routes/v1_backtest.py:130` | `symbol` and `strategy_params` are separate; only the latter reaches the strategy |

### Shared hardcoded constants

| File:line | Defect |
|---|---|
| `core/constants.py:4` | `LOT_SIZES`, no instrument-type dimension |
| `market/option_chain.py:11` | duplicate `LOT_SIZES` |
| `strategies/*.py` (11 files) | `LOT_SIZES.get(self.symbol, 75)` and four other defaults |
| `market/instrument_service.py:31` | `LOT_SIZES.get(index.upper(), 65)` — docstring says "falling back to constants" |
| `engine/strategy_compiler.py:120,241` | `LOT_SIZES.get(symbol, 65)` |
| `engine/user_strategy_backtest.py:180`, `engine/user_strategy_runner.py:146` | `LOT_SIZES.get(index_symbol, 65)` |

---

## 9. Recommended architecture

```text
Dhan instrument / scrip master          ← the single source of truth
        ↓
Ingestion (SymbolMaster._sync_dhan_instruments)
        ↓
symbol_master, keyed (broker='dhan', exchange, security_id) + (broker='dhan', trading_symbol)
        ↓
InstrumentResolver — the ONLY way to obtain contract metadata
        │   returns security_id, exchange_segment, instrument_type, lot_size, tick_size,
        │   underlying, expiry, strike, option_type
        ↓
Strategy asks for LOTS, not units
        ↓
Sizing: risk budget ÷ (stop distance × lot_size)  →  lots
        ↓
quantity = lots × lot_size                       ← exactly once, in ONE place
        ↓
Exposure = quantity × price;  margin from broker fundlimit
        ↓
Risk engine validates the FINAL quantity and the FINAL exposure
        ↓
Order validation (segment, security_id, lot multiple, tick size)
        ↓
Execution
```

### Rules this imposes

1. **One ingress.** Implement `_sync_dhan_instruments` against Dhan's instrument endpoint. It
   must be idempotent, record `broker='dhan'`, and store `security_id` as a first-class column.
   Until it exists, `resolve()` must **fail**, not default.

2. **One resolver, no fallbacks.** `InstrumentResolver.resolve(symbol, instrument_type)` is the
   only sanctioned entry point. `core/constants.LOT_SIZES` and `market/option_chain.LOT_SIZES`
   are deleted, not deprecated. A miss returns `None`.

3. **Fail closed, with the user's required message.** No metadata, no order:

   ```
   ORDER BLOCKED
   Reason: Unable to resolve authoritative Dhan instrument metadata.

   Required metadata:
   - Security ID
   - Exchange Segment
   - Instrument Type
   - Lot Size
   ```

   This is safer than sending an order with an assumed quantity, and it is the behaviour the
   user asked for explicitly.

4. **Index and derivative are different instruments.** A key must carry the instrument class —
   `(exchange, instrument_type, underlying, expiry, strike, option_type)` — not a bare
   `NIFTY`. `NSE:NIFTY50-INDEX` must not resolve to an index lot size, and must not resolve to a
   futures contract either. If a caller needs a tradable contract and passed an index symbol,
   that is a mismatch to report, not a lot size to invent.

5. **Lots and units never share a variable name.** `lots: int` is the strategy's output;
   `quantity: int` is `lots × lot_size`, computed once, in one function. `_snap_quantity_to_lot`
   is deleted: it can only ever multiply, never convert.

6. **Sizing is a function of the risk budget.** `lots = floor(risk_amount / (stop_distance ×
   lot_size))`, then floor to whole lots. `risk_amount` derives from capital, the configured
   per-trade percentage, and the actual stop distance. A zero or negative stop distance is a
   rejection, not a division.

7. **Enforce the invariants, block on violation** — quantity > 0, quantity ≤ max_quantity,
   exposure ≤ max_exposure, required margin ≤ available margin, risk ≤ allowed risk. **Block;
   never silently resize.** This is the existing `BacktestRiskSimulator` rule vocabulary, which
   is already correct and should become the single implementation rather than the backtest-only
   one.

8. **Make `max_position_size <= 0` mean disabled only when it is explicitly set.** For 3 of 4
   production accounts it is the implicit default. An unset position ceiling on a funded live
   account should be a startup warning, not a silent pass.

9. **Reconcile the two risk engines.** `RiskGuard` and `risk_manager` enforce different rules
   on the same order. Until they are one, the platform `/orders` route and the gate can return
   different verdicts for the same order.

10. **Fix the backtest symbol wiring.** Pass `config.symbol` into the strategy so the strategy
    trades what the run was asked for. Until then every backtest result on an index symbol is
    measuring a different instrument than the one requested.

### Sequencing

Fixing the wiring (§10) and the `×10` multiply (§6a) removes the immediate hazard. Building the
Dhan pipeline (§9.1–9.3) is the larger change and should follow, because the resolver must not
be wired to a table that has no Dhan rows.

**Interim, before any of the above:** treat every `LOT_SIZES` fallback and the
`10 * lot` multiply as a BLOCKER for live trading, and note that Dhan order payloads are being
constructed with display symbols in the `securityId` field.

---

## 10. Reproduction artifacts

Both are read-only and run locally against synthetic data — no broker, no network, no database.

| Script | What it asserts |
|---|---|
| `apps/api/scripts/verify_strategy_symbol_wiring.py` | `BacktestConfig.symbol` vs `strategy.symbol` for 6 strategies — proves 6/6 mismatch |
| `apps/api/scripts/repro_backtest_defects.py` | Full sizing chain with per-order notional/capital ratio, plus the fee-aware P&L reconciliation |

```
$ python scripts/verify_strategy_symbol_wiring.py
6 of 6 strategies trade a symbol the run was not asked for.

$ python scripts/repro_backtest_defects.py
order #1: SELL qty=75 @ ~24,440.6
  notional / capital  : 1.83x
orders emitted       : 14      risk-blocked: 12
sum(trade pnl)       : 47,481.26
total costs          :  2,366.38
equity change        : 45,114.88   →  gross − costs == equity change  EXACT
```

That last line settles a separate question. The accounting reconciles precisely — trade P&L is
gross, costs are tracked separately, and `gross − costs == final equity − initial capital`.
**There is no P&L double-counting in the backtest broker.** The impossible
`max_drawdown_pct = 170.45` is likewise not a formula defect: `dd_pct = (peak − equity) / peak`
is correct, and a value above 100% means only that equity went negative — which is what a
1.83× position produces.

---

## 11. Open questions for the owner

1. **Dhan instrument endpoint access.** Which Dhan endpoint and plan tier is the account on?
   The ingestion shape depends on it. `UNVERIFIED` — not probed, because that would require
   live credentials and the brief forbids placing orders (probing a read-only master was not
   attempted either; it needs a decision on whether that is in scope).
2. **`2 accounts with is_live = true`.** Should they be set to false until §6a–6c are fixed?
   That is a production data change and is not mine to make.
3. **`3 of 4 accounts have no position ceiling.** Should a funded live account be permitted to
   run with `max_position_size = 0`?
4. **Dhan market data is not subscribed** (websocket 404, per earlier session). That blocks
   verifying any of the above against live Dhan prices.