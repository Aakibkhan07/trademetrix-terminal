"""Backtest execution: deterministic candle-based fills + broker adapter.

BacktestBroker mirrors the PaperBroker surface (place/modify/cancel, positions,
funds, health) but runs fully in-memory against the loaded candle series:
no Supabase writes, no event bus, no portfolio_manager refresh — fast enough
for MAX-speed backtests over years of candles.

Fill semantics (design doc Phase 5.3):
- Orders are evaluated at candle `index + latency_candles` (look-ahead bias
  mitigation: a signal on candle N executes at the close of candle N+latency).
- MARKET   -> fill at that candle's close +/- slippage.
- LIMIT    -> fill within `fill_timeout_candles` when the candle trades through
              the limit (fill at limit, or better open); else stays resting and
              is retried every candle until the window expires.
- SL (SL-L)-> fills when BOTH trigger and limit are traded through.
- SLM (SL-M) -> fills when the trigger is breached (fill at trigger, or worse
              open on a gap), slippage applied.
- Partial fills: seeded RNG, `partial_fill_probability` chance the order fills
  at 30-100% of quantity (remainder cancelled).
- Indian charges (backtest.costs.estimate_cost) are debited on every fill.
"""
from __future__ import annotations

import logging
import random
import time
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from backtest.costs import BacktestCostConfig, CostEstimate, estimate_cost, segment_for
from core.models import (
    Exchange, Funds, NormalizedOrder, OrderResult, OrderStatus,
    OrderType, Position, ProductType,
)
from execution.models import BrokerCapabilities

logger = logging.getLogger(__name__)


class BacktestExecutionConfig(BaseModel):
    initial_capital: float = 100_000.0
    slippage_pct: float = 0.0
    latency_candles: int = 0
    fill_timeout_candles: int = 5
    partial_fill_probability: float = 0.0
    seed: int | None = None
    cost_config: dict = Field(default_factory=dict)


class FillResult(BaseModel):
    price: float = 0.0
    quantity: int = 0
    status: str = "pending"          # filled | partially_filled | pending | rejected
    reason: str = ""


class BacktestFillEngine:
    """Deterministic candle-based fill simulation."""

    def __init__(self, config: BacktestExecutionConfig):
        self._config = config
        self._candles: list[dict] = []
        self._index = -1
        self._rng = random.Random(config.seed)

    def set_candles(self, candles: list[dict]) -> None:
        self._candles = candles or []

    def set_index(self, index: int) -> None:
        self._index = index

    @property
    def current_index(self) -> int:
        return self._index

    def _target_index(self) -> int:
        return self._index + self._config.latency_candles

    def _candle(self, idx: int) -> dict | None:
        if 0 <= idx < len(self._candles):
            return self._candles[idx]
        return None

    def _slip(self, price: float, side: str) -> float:
        pct = self._config.slippage_pct / 100.0
        if pct <= 0:
            return price
        return round(price * (1 + pct) if side.upper() == "BUY" else price * (1 - pct), 4)

    def _maybe_partial(self, order: NormalizedOrder) -> tuple[int, bool]:
        qty = order.quantity
        prob = self._config.partial_fill_probability
        if prob <= 0 or qty <= 1:
            return qty, False
        if self._rng.random() < prob:
            return max(1, int(qty * self._rng.uniform(0.3, 1.0))), True
        return qty, False

    def simulate_fill(self, order: NormalizedOrder) -> FillResult:
        """Attempt a fill at the current evaluation index (index + latency)."""
        side = order.side.value if hasattr(order.side, "value") else str(order.side)
        otype = order.order_type.value if hasattr(order.order_type, "value") else str(order.order_type)
        target = self._target_index()
        candle = self._candle(target)
        if candle is None:
            return FillResult(status="pending", reason="no candle at evaluation index")

        open_, high, low = (float(candle["open"]), float(candle["high"]), float(candle["low"]))

        if otype == OrderType.MARKET.value:
            price = self._slip(float(candle["close"]), side)
            qty, partial = self._maybe_partial(order)
            if qty <= 0:
                return FillResult(status="rejected", reason="zero fill quantity")
            return FillResult(
                price=price, quantity=qty,
                status="partially_filled" if partial else "filled",
                reason="market",
            )

        if otype == OrderType.LIMIT.value:
            return self._limit_fill(order, side, candle)

        if otype in (OrderType.SL.value, OrderType.SLM.value):
            return self._stop_fill(order, side, otype, candle)

        return FillResult(status="rejected", reason=f"unsupported order type {otype}")

    def _limit_fill(self, order: NormalizedOrder, side: str, candle: dict) -> FillResult:
        limit = float(order.price)
        open_, high, low = (float(candle["open"]), float(candle["high"]), float(candle["low"]))
        if side == "BUY":
            if low > limit:
                return FillResult(status="pending", reason="limit not breached")
            price = min(limit, open_)
        else:
            if high < limit:
                return FillResult(status="pending", reason="limit not breached")
            price = max(limit, open_)
        qty, partial = self._maybe_partial(order)
        return FillResult(
            price=round(price, 4), quantity=qty,
            status="partially_filled" if partial else "filled",
            reason="limit",
        )

    def _stop_fill(self, order: NormalizedOrder, side: str, otype: str, candle: dict) -> FillResult:
        trigger = float(order.trigger_price or order.price)
        open_, high, low = (float(candle["open"]), float(candle["high"]), float(candle["low"]))
        if side == "BUY":
            if high < trigger:
                return FillResult(status="pending", reason="stop not triggered")
            base = max(trigger, open_)
        else:
            if low > trigger:
                return FillResult(status="pending", reason="stop not triggered")
            base = min(trigger, open_)

        if otype == OrderType.SL.value:  # SL-L: both trigger and limit traded
            limit = float(order.price)
            if side == "BUY":
                if low > limit:
                    return FillResult(status="pending", reason="limit not traded")
                base = min(base, limit)
            else:
                if high < limit:
                    return FillResult(status="pending", reason="limit not traded")
                base = max(base, limit)

        price = self._slip(base, side)
        qty, partial = self._maybe_partial(order)
        return FillResult(
            price=round(price, 4), quantity=qty,
            status="partially_filled" if partial else "filled",
            reason="stop",
        )


class BacktestBroker:
    """In-memory broker adapter for backtests (PaperBroker-compatible surface)."""

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.broker = "paper"
        self._config = BacktestExecutionConfig()
        self._fill_engine = BacktestFillEngine(self._config)
        self._orders: dict[str, dict] = {}
        self._positions: dict[str, dict] = {}
        self._last_prices: dict[str, float] = {}
        self._cash = self._config.initial_capital
        self._total_costs = 0.0
        self._total_slippage = 0.0
        self._realized = 0.0
        self._order_counter = 0
        self._trades: list[dict] = []
        self._last_times: dict[str, str] = {}
        self._authenticated = False

    async def connect(self) -> bool:
        self._authenticated = True
        return True

    async def disconnect(self):
        self._authenticated = False

    async def health(self) -> dict:
        return {
            "broker": "paper",
            "authenticated": self._authenticated,
            "connected": self._authenticated,
            "paper": True,
            "backtest": True,
            "capital": self._cash,
            "equity": self.equity(),
        }

    def capabilities(self) -> BrokerCapabilities:
        return BrokerCapabilities(
            broker="paper",
            supports_orders=True,
            supports_modify=True,
            supports_cancel=True,
            supports_bracket=False,
            supports_cover=False,
            supports_gtt=False,
            supports_websocket=False,
            supports_option_chain=False,
            supports_positions=True,
            supports_holdings=True,
        )

    def update_config(self, config: BacktestExecutionConfig) -> None:
        self._config = config
        self._fill_engine._config = config
        self._fill_engine._rng = random.Random(config.seed)
        self._cash = config.initial_capital
        self._total_costs = 0.0
        self._total_slippage = 0.0
        self._realized = 0.0

    def get_config(self) -> BacktestExecutionConfig:
        return self._config

    def set_candles(self, candles: list[dict]) -> None:
        self._fill_engine.set_candles(candles)

    async def on_candle(self, index: int) -> None:
        """Advance the fill index, retry resting orders, mark to market."""
        self._fill_engine.set_index(index)
        for order_id in list(self._orders.keys()):
            entry = self._orders[order_id]
            if entry["status"] != "pending":
                continue
            order = entry["order"]
            window = self._config.fill_timeout_candles
            if index - entry["index"] > window:
                entry["status"] = "expired"
                continue
            result = self._fill_engine.simulate_fill(order)
            if result.status in ("filled", "partially_filled"):
                self._apply_fill(order, result, order_id, entry)
                entry["status"] = result.status
                entry["fills"].append(result)
        candle = self._candle_at(index)
        if candle:
            self._last_prices[candle["symbol"]] = float(candle["close"])
            self._last_times[candle["symbol"]] = str(candle.get("timestamp", ""))

    def _candle_at(self, index: int) -> dict | None:
        candles = self._fill_engine._candles
        if 0 <= index < len(candles):
            return candles[index]
        return None

    async def place_order(self, order: NormalizedOrder) -> OrderResult:
        start = time.monotonic()
        self._order_counter += 1
        order_id = f"bt_{self._order_counter}_{int(time.time())}"
        order.broker_order_id = order_id
        order.broker = "paper"
        order.user_id = order.user_id or self.user_id

        result = self._fill_engine.simulate_fill(order)

        if result.status == "rejected":
            return OrderResult(
                success=False, broker_order_id=order_id, order=order,
                message=result.reason, status="rejected",
            )

        if result.status == "pending":
            self._orders[order_id] = {
                "order": order, "status": "pending", "fills": [],
                "index": self._fill_engine.current_index,
                "created_at": datetime.now(UTC),
            }
            return OrderResult(
                success=True, broker_order_id=order_id, order=order,
                message="Order pending (limit/stop not triggered)", status="pending",
            )

        self._apply_fill(order, result, order_id)
        self._orders[order_id] = {
            "order": order, "status": result.status, "fills": [result],
            "index": self._fill_engine.current_index,
            "created_at": datetime.now(UTC),
        }

        elapsed_ms = (time.monotonic() - start) * 1000
        order.status = (
            OrderStatus.PARTIALLY_FILLED if result.status == "partially_filled" else OrderStatus.FILLED
        )
        order.filled_quantity = result.quantity
        order.average_price = result.price
        order.filled_at = datetime.now(UTC)
        order.latency_ms = round(elapsed_ms, 2)
        order.slippage = round(self._config.slippage_pct, 4)

        return OrderResult(
            success=True, broker_order_id=order_id, order=order,
            message=f"Backtest order {result.status} {result.quantity} @ {result.price:.2f}",
            status=result.status, filled_qty=result.quantity, avg_price=result.price,
        )

    def _apply_fill(self, order: NormalizedOrder, result: FillResult, order_id: str, entry: dict | None = None) -> None:
        symbol = order.symbol
        side = order.side.value if hasattr(order.side, "value") else str(order.side)
        qty = result.quantity
        price = result.price
        traded_value = qty * price

        slippage_value = traded_value * self._config.slippage_pct / 100.0
        seg = segment_for(
            order.instrument_type.value if hasattr(order.instrument_type, "value") else "",
            order.product.value if hasattr(order.product, "value") else "",
        )
        cost_cfg = BacktestCostConfig(**self._config.cost_config)
        cost = estimate_cost(
            side=side, traded_value=traded_value, segment=seg, qty=qty, price=price,
            slippage_value=slippage_value, config=cost_cfg,
        )
        self._total_costs += cost.total
        self._total_slippage += cost.slippage

        pos = self._positions.setdefault(
            symbol,
            {"quantity": 0, "avg_price": 0.0, "realized_pnl": 0.0, "total_cost": 0.0},
        )
        opened_at = self._last_times.get(symbol, "")
        order_reason = getattr(order, "reason", "") or ""
        exit_reason = self._exit_reason(order, order_reason)
        fill_costs = self._cost_split(cost)

        if side == "BUY":
            prev_qty = pos["quantity"]
            if prev_qty >= 0:
                prev_time = pos.get("entry_time")
                opening = prev_qty == 0
                pos["quantity"] = prev_qty + qty
                pos["avg_price"] = (pos["avg_price"] * prev_qty + price * qty) / max(1, prev_qty + qty)
                pos["entry_time"] = prev_time or opened_at
                pos.setdefault("entry_reason", order_reason or "signal")
                if opening:
                    pos["entry_costs"] = dict(fill_costs)
                    pos["stop_price"] = self._stop_price_at_symbol(symbol)
                else:
                    pos["entry_costs"] = self._sum_costs(pos.get("entry_costs"), fill_costs)
                pos.setdefault("entry_qty", 0)
                pos["entry_qty"] += qty
            else:
                closed = min(qty, -prev_qty)
                pnl = (pos["avg_price"] - price) * closed
                pos["realized_pnl"] += pnl
                self._realized += pnl
                self._record_trade(
                    symbol, "SELL", pos["avg_price"], price, closed, pnl,
                    pos.get("entry_time") or opened_at,
                    entry_reason=pos.get("entry_reason", "") or "",
                    exit_reason=exit_reason,
                    entry_costs=pos.get("entry_costs"),
                    exit_costs=fill_costs,
                )
                self._consume_entry_costs(pos, closed)
                pos["quantity"] = prev_qty + closed
                if qty > closed:
                    pos["quantity"] = qty - closed
                    pos["avg_price"] = price
                    pos["entry_time"] = opened_at
                    pos["entry_reason"] = order_reason or "signal"
                    pos["entry_costs"] = dict(fill_costs)
                    pos["entry_qty"] = qty - closed
                    pos["stop_price"] = self._stop_price_at_symbol(symbol)
                else:
                    self._clear_entry_state(pos)
            self._cash -= traded_value + cost.total
        else:
            prev_qty = pos["quantity"]
            if prev_qty <= 0:
                prev_time = pos.get("entry_time")
                opening = prev_time is None
                pos["quantity"] = prev_qty - qty
                pos["avg_price"] = (abs(pos["avg_price"]) * abs(prev_qty) + price * qty) / max(1, abs(prev_qty) + qty)
                pos["entry_time"] = prev_time or opened_at
                pos.setdefault("entry_reason", order_reason or "signal")
                if opening:
                    pos["entry_costs"] = dict(fill_costs)
                    pos["stop_price"] = self._stop_price_at_symbol(symbol)
                else:
                    pos["entry_costs"] = self._sum_costs(pos.get("entry_costs"), fill_costs)
                pos.setdefault("entry_qty", 0)
                pos["entry_qty"] += qty
            else:
                closed = min(qty, prev_qty)
                pnl = (price - pos["avg_price"]) * closed
                pos["realized_pnl"] += pnl
                self._realized += pnl
                self._record_trade(
                    symbol, "BUY", pos["avg_price"], price, closed, pnl,
                    pos.get("entry_time") or opened_at,
                    entry_reason=pos.get("entry_reason", "") or "",
                    exit_reason=exit_reason,
                    entry_costs=pos.get("entry_costs"),
                    exit_costs=fill_costs,
                )
                self._consume_entry_costs(pos, closed)
                pos["quantity"] = prev_qty - closed
                if qty > closed:
                    pos["quantity"] = -(qty - closed)
                    pos["avg_price"] = price
                    pos["entry_time"] = opened_at
                    pos["entry_reason"] = order_reason or "signal"
                    pos["entry_costs"] = dict(fill_costs)
                    pos["entry_qty"] = qty - closed
                    pos["stop_price"] = self._stop_price_at_symbol(symbol)
                else:
                    self._clear_entry_state(pos)
            self._cash += traded_value - cost.total

        self._last_prices[symbol] = price

    def _sum_costs(self, a: dict | None, b: dict) -> dict:
        a = a or {"slippage": 0.0, "charges": 0.0, "taxes": 0.0, "total": 0.0}
        return {k: round(v + b.get(k, 0.0), 2) for k, v in a.items()}

    def _clear_entry_state(self, pos: dict) -> None:
        for key in ("entry_time", "entry_reason", "entry_costs", "stop_price", "entry_qty"):
            pos.pop(key, None)

    def _exit_reason(self, order: NormalizedOrder, order_reason: str) -> str:
        if order_reason:
            return order_reason
        otype = order.order_type.value if hasattr(order.order_type, "value") else str(order.order_type)
        if otype in ("SL", "SLM"):
            return "stop"
        if otype in ("LIMIT",):
            return "target"
        return "signal"

    def _stop_price_at_symbol(self, symbol: str) -> float | None:
        """Best-effort stop level: a resting SL/SL-M order on the closing side."""
        for entry in self._orders.values():
            order = entry.get("order")
            if not order or order.symbol != symbol:
                continue
            otype = order.order_type.value if hasattr(order.order_type, "value") else str(order.order_type)
            if otype not in ("SL", "SLM"):
                continue
            os_side = order.side.value if hasattr(order.side, "value") else str(order.side)
            if os_side not in ("BUY", "SELL"):
                continue
            level = order.trigger_price or order.price
            if level and level > 0:
                return float(level)
        return None

    def _cost_split(self, cost: CostEstimate) -> dict:
        return {
            "slippage": round(cost.slippage, 2),
            "charges": round(cost.brokerage + cost.exchange_tc, 2),
            "taxes": round(cost.stt + cost.stamp_duty + cost.gst + cost.sebi, 2),
            "total": round(cost.total, 2),
        }

    def _consume_entry_costs(self, pos: dict, closed: int) -> None:
        """Proportionally reduce accumulated entry costs after a partial close."""
        entry_qty = pos.get("entry_qty", 0) or 0
        if entry_qty <= 0:
            return
        share = closed / entry_qty
        costs = pos.get("entry_costs") or {}
        pos["entry_costs"] = {
            k: round(v * (1 - share), 2) for k, v in costs.items()
        }
        pos["entry_qty"] = max(0, entry_qty - closed)

    def _record_trade(self, symbol: str, side: str, entry: float, exit_price: float,
                      qty: int, pnl: float, entry_time: str | None = None,
                      entry_reason: str = "", exit_reason: str = "signal",
                      entry_costs: dict | None = None, exit_costs: dict | None = None) -> None:
        entry_costs = entry_costs or {"slippage": 0.0, "charges": 0.0, "taxes": 0.0, "total": 0.0}
        exit_costs = exit_costs or {"slippage": 0.0, "charges": 0.0, "taxes": 0.0, "total": 0.0}
        exit_time = self._last_times.get(symbol, "")
        duration_minutes = 0
        try:
            t0 = datetime.fromisoformat(str(entry_time).replace("Z", "+00:00"))
            t1 = datetime.fromisoformat(str(exit_time).replace("Z", "+00:00"))
            duration_minutes = max(0, int((t1 - t0).total_seconds() // 60))
        except (ValueError, AttributeError, TypeError):
            pass
        slippage = round(entry_costs.get("slippage", 0.0) + exit_costs.get("slippage", 0.0), 2)
        charges = round(entry_costs.get("charges", 0.0) + exit_costs.get("charges", 0.0), 2)
        taxes = round(entry_costs.get("taxes", 0.0) + exit_costs.get("taxes", 0.0), 2)
        cost_total = round(slippage + charges + taxes, 2)
        risk_amount = 0.0
        stop = self._stop_price_at_symbol(symbol)
        if stop and float(stop) != float(entry):
            risk_amount = round(abs(float(entry) - float(stop)) * qty, 2)
        rr = 0.0
        if risk_amount > 0:
            rr = round(pnl / risk_amount, 2)
        self._trades.append({
            "symbol": symbol,
            "side": side,
            "entry_price": round(entry, 4),
            "exit_price": round(exit_price, 4),
            "quantity": qty,
            "pnl": round(pnl, 2),
            "entry_time": entry_time or exit_time,
            "exit_time": exit_time,
            "duration_minutes": duration_minutes,
            "entry_reason": entry_reason or "signal",
            "exit_reason": exit_reason,
            "slippage": slippage,
            "charges": charges,
            "taxes": taxes,
            "cost_total": cost_total,
            "risk_amount": risk_amount,
            "rr": rr,
        })

    async def modify_order(self, order_id: str, changes: dict) -> OrderResult:
        entry = self._orders.get(order_id)
        if not entry:
            return OrderResult(success=False, message="Order not found")
        order = entry["order"]
        if "quantity" in changes:
            order.quantity = int(changes["quantity"])
        if "price" in changes:
            order.price = float(changes["price"])
        if "trigger_price" in changes:
            order.trigger_price = float(changes["trigger_price"])
        return OrderResult(
            success=True, broker_order_id=order_id, order=order,
            message="Order modified", status=entry["status"],
        )

    async def cancel_order(self, order_id: str) -> OrderResult:
        entry = self._orders.get(order_id)
        if not entry:
            return OrderResult(success=False, message="Order not found")
        entry["status"] = "cancelled"
        return OrderResult(
            success=True, broker_order_id=order_id, order=entry["order"],
            message="Order cancelled", status="cancelled",
        )

    async def get_order(self, order_id: str) -> NormalizedOrder | None:
        entry = self._orders.get(order_id)
        return entry["order"] if entry else None

    async def get_orders(self) -> list[NormalizedOrder]:
        return [entry["order"] for entry in self._orders.values()]

    async def get_orderbook(self) -> list[NormalizedOrder]:
        return await self.get_orders()

    async def get_positions(self) -> list:
        return [
            {
                "symbol": symbol,
                "quantity": p["quantity"],
                "average_buy_price": p["avg_price"] if p["quantity"] >= 0 else 0.0,
                "average_sell_price": p["avg_price"] if p["quantity"] < 0 else 0.0,
                "last_price": self._last_prices.get(symbol, 0.0),
                "unrealised_pnl": self._unrealised(symbol),
                "realised_pnl": p["realized_pnl"],
            }
            for symbol, p in self._positions.items()
        ]

    async def get_holdings(self) -> list:
        return []

    async def get_funds(self) -> Funds:
        return Funds(
            total_margin=self._cash,
            used_margin=0.0,
            available_margin=self._cash,
            broker="paper",
        )

    async def validate_order(self, order: NormalizedOrder) -> dict:
        return {"valid": True, "errors": []}

    # ─── accounting helpers ───

    def _unrealised(self, symbol: str) -> float:
        p = self._positions.get(symbol)
        if not p or p["quantity"] == 0:
            return 0.0
        last = self._last_prices.get(symbol, p["avg_price"])
        return (last - p["avg_price"]) * p["quantity"]

    def equity(self) -> float:
        unrealised = sum(self._unrealised(s) for s in self._positions)
        return self._cash + unrealised

    @property
    def cash(self) -> float:
        return self._cash

    @property
    def total_costs(self) -> float:
        return self._total_costs

    @property
    def total_slippage(self) -> float:
        return self._total_slippage

    @property
    def realized_pnl(self) -> float:
        return self._realized

    @property
    def trades(self) -> list[dict]:
        return list(self._trades)

    def positions(self) -> dict[str, dict]:
        return self._positions

    def reset(self) -> None:
        self._orders.clear()
        self._positions.clear()
        self._last_prices.clear()
        self._last_times.clear()
        self._trades.clear()
        self._cash = self._config.initial_capital
        self._total_costs = 0.0
        self._total_slippage = 0.0
        self._realized = 0.0


backtest_broker_factory = BacktestBroker
