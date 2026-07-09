import logging
import time
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta, timezone
from collections import defaultdict, deque

from core.db import async_supabase, get_supabase
from core.models import NormalizedOrder
from core.safe_query import async_safe_execute, safe_execute, safe_single
from execution.models import ExecutionRequest
from market.status import market_status_service
from risk.models import RiskConfig, RiskDecision, RiskRuleResult, RiskRuleType

logger = logging.getLogger(__name__)


async def _compute_daily_pnl_fifo(user_id: str) -> float:
    try:
        IST = timezone(timedelta(hours=5, minutes=30))
        today_start = datetime.now(IST).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        supabase = get_supabase()
        filled = await async_safe_execute(
            supabase.table("orders")
            .select("symbol, side, quantity, filled_quantity, average_price, created_at")
            .eq("user_id", user_id)
            .eq("status", "FILLED")
            .gte("created_at", today_start)
            .order("created_at")
        )
        if not filled:
            return 0.0

        sell_symbols = {o["symbol"] for o in filled if o["side"] == "SELL"}
        historical: dict[str, list[dict]] = {}
        for sym in sell_symbols:
            hist_rows = await async_safe_execute(
                supabase.table("orders")
                .select("quantity, filled_quantity, average_price")
                .eq("user_id", user_id)
                .eq("symbol", sym)
                .eq("side", "BUY")
                .eq("status", "FILLED")
                .lt("created_at", today_start)
                .order("created_at")
            )
            if hist_rows:
                historical[sym] = hist_rows

        pnl = 0.0
        buy_queue: dict[str, list[list[float]]] = {}

        for o in filled:
            sym = o["symbol"]
            qty = float(o.get("filled_quantity") if o.get("filled_quantity") is not None else o.get("quantity") or 0)
            price = float(o.get("average_price") or 0)
            if qty <= 0:
                continue

            if o["side"] == "BUY":
                buy_queue.setdefault(sym, []).append([qty, price])
            else:
                rem = qty
                queue = buy_queue.setdefault(sym, [])
                while rem > 0 and queue:
                    bqty, bprice = queue[0]
                    used = min(rem, bqty)
                    pnl += used * (price - bprice)
                    rem -= used
                    queue[0][0] -= used
                    if queue[0][0] <= 1e-8:
                        queue.pop(0)
                if rem > 0:
                    for h in historical.get(sym, []):
                        if rem <= 0:
                            break
                        hqty = float(h.get("filled_quantity") or h.get("quantity") or 0)
                        hprice = float(h.get("average_price") or 0)
                        if hqty > 0:
                            used = min(rem, hqty)
                            pnl += used * (price - hprice)
                            rem -= used
        return pnl
    except Exception as e:
        logger.warning("FIFO PnL computation failed: %s", e)
        return 0.0


class RiskRule(ABC):
    rule_type: RiskRuleType

    @abstractmethod
    async def evaluate(self, req: ExecutionRequest, config: RiskConfig) -> RiskRuleResult:
        ...


class KillSwitchRule(RiskRule):
    rule_type = RiskRuleType.KILL_SWITCH

    async def evaluate(self, req: ExecutionRequest, config: RiskConfig) -> RiskRuleResult:
        start = time.monotonic()
        if config.kill_switch_enabled:
            return RiskRuleResult(
                rule=self.rule_type, decision=RiskDecision.REJECTED,
                reason="Kill switch is active. All trading halted.",
                latency_ms=(time.monotonic() - start) * 1000,
            )
        return RiskRuleResult(rule=self.rule_type, latency_ms=(time.monotonic() - start) * 1000)


class EmergencyStopRule(RiskRule):
    rule_type = RiskRuleType.EMERGENCY_STOP

    async def evaluate(self, req: ExecutionRequest, config: RiskConfig) -> RiskRuleResult:
        start = time.monotonic()
        if config.emergency_stop:
            return RiskRuleResult(
                rule=self.rule_type, decision=RiskDecision.REJECTED,
                reason="Emergency stop is active. All trading halted.",
                latency_ms=(time.monotonic() - start) * 1000,
            )
        return RiskRuleResult(rule=self.rule_type, latency_ms=(time.monotonic() - start) * 1000)


class BrokerOfflineRule(RiskRule):
    rule_type = RiskRuleType.BROKER_OFFLINE

    async def evaluate(self, req: ExecutionRequest, config: RiskConfig) -> RiskRuleResult:
        start = time.monotonic()
        if req.broker in config.broker_blocked:
            return RiskRuleResult(
                rule=self.rule_type, decision=RiskDecision.REJECTED,
                reason=f"Broker {req.broker} is blocked by risk settings.",
                latency_ms=(time.monotonic() - start) * 1000,
            )
        return RiskRuleResult(rule=self.rule_type, latency_ms=(time.monotonic() - start) * 1000)


class MarketClosedRule(RiskRule):
    rule_type = RiskRuleType.MARKET_CLOSED

    async def evaluate(self, req: ExecutionRequest, config: RiskConfig) -> RiskRuleResult:
        start = time.monotonic()
        try:
            if not market_status_service.is_market_open():
                return RiskRuleResult(
                    rule=self.rule_type, decision=RiskDecision.REJECTED,
                    reason="Market is closed.",
                    latency_ms=(time.monotonic() - start) * 1000,
                )
        except Exception as e:
            logger.error("MarketClosedRule check failed: %s", e)
            return RiskRuleResult(
                rule=self.rule_type, decision=RiskDecision.REJECTED,
                reason="Market status unavailable — trading blocked (fail-closed)",
                latency_ms=(time.monotonic() - start) * 1000,
            )
        return RiskRuleResult(rule=self.rule_type, latency_ms=(time.monotonic() - start) * 1000)


class TradingWindowRule(RiskRule):
    rule_type = RiskRuleType.TRADING_WINDOW

    async def evaluate(self, req: ExecutionRequest, config: RiskConfig) -> RiskRuleResult:
        start = time.monotonic()
        if not config.trading_start or not config.trading_end:
            return RiskRuleResult(rule=self.rule_type, latency_ms=(time.monotonic() - start) * 1000)

        now = datetime.now(timezone(timedelta(hours=5, minutes=30)))
        try:
            open_h, open_m = map(int, config.trading_start.split(":"))
            close_h, close_m = map(int, config.trading_end.split(":"))
            open_dt = now.replace(hour=open_h, minute=open_m, second=0, microsecond=0)
            close_dt = now.replace(hour=close_h, minute=close_m, second=0, microsecond=0)
            if not (open_dt <= now <= close_dt):
                return RiskRuleResult(
                    rule=self.rule_type, decision=RiskDecision.REJECTED,
                    reason=f"Outside trading window ({config.trading_start}-{config.trading_end} IST).",
                    latency_ms=(time.monotonic() - start) * 1000,
                )
        except Exception as e:
            logger.error("TradingWindowRule check failed: %s", e)
            return RiskRuleResult(
                rule=self.rule_type, decision=RiskDecision.REJECTED,
                reason="Trading window check failed — trading blocked (fail-closed)",
                latency_ms=(time.monotonic() - start) * 1000,
            )
        return RiskRuleResult(rule=self.rule_type, latency_ms=(time.monotonic() - start) * 1000)


class DailyLossLimitRule(RiskRule):
    rule_type = RiskRuleType.DAILY_LOSS_LIMIT

    async def evaluate(self, req: ExecutionRequest, config: RiskConfig) -> RiskRuleResult:
        start = time.monotonic()
        if config.daily_loss_limit <= 0:
            return RiskRuleResult(rule=self.rule_type, latency_ms=(time.monotonic() - start) * 1000)

        today_pnl = await self._get_today_pnl(req.user_id)
        if today_pnl <= -config.daily_loss_limit:
            return RiskRuleResult(
                rule=self.rule_type, decision=RiskDecision.REJECTED,
                reason=f"Daily loss {today_pnl:.2f} exceeds limit {config.daily_loss_limit:.2f}.",
                details={"daily_pnl": today_pnl, "limit": config.daily_loss_limit},
                latency_ms=(time.monotonic() - start) * 1000,
            )
        return RiskRuleResult(rule=self.rule_type, latency_ms=(time.monotonic() - start) * 1000)

    async def _get_today_pnl(self, user_id: str) -> float:
        return await _compute_daily_pnl_fifo(user_id)


class MaxTradesPerDayRule(RiskRule):
    rule_type = RiskRuleType.MAX_TRADES_PER_DAY

    async def evaluate(self, req: ExecutionRequest, config: RiskConfig) -> RiskRuleResult:
        start = time.monotonic()
        if config.max_trades_per_day <= 0:
            return RiskRuleResult(rule=self.rule_type, latency_ms=(time.monotonic() - start) * 1000)

        count = await self._get_today_trade_count(req.user_id)
        if count >= config.max_trades_per_day:
            return RiskRuleResult(
                rule=self.rule_type, decision=RiskDecision.REJECTED,
                reason=f"Trade count {count} exceeds daily limit {config.max_trades_per_day}.",
                details={"trade_count": count, "limit": config.max_trades_per_day},
                latency_ms=(time.monotonic() - start) * 1000,
            )
        return RiskRuleResult(rule=self.rule_type, latency_ms=(time.monotonic() - start) * 1000)

    async def _get_today_trade_count(self, user_id: str) -> int:
        try:
            IST = timezone(timedelta(hours=5, minutes=30))
            today_start = datetime.now(IST).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
            supabase = get_supabase()
            rows = await async_safe_execute(
                supabase.table("orders")
                .select("id")
                .eq("user_id", user_id)
                .gte("created_at", today_start)
            )
            return len(rows) if rows else 0
        except Exception as e:
            logger.warning("Failed to get trade count: %s", e)
            return 0


class MaxOpenPositionsRule(RiskRule):
    rule_type = RiskRuleType.MAX_OPEN_POSITIONS

    async def evaluate(self, req: ExecutionRequest, config: RiskConfig) -> RiskRuleResult:
        start = time.monotonic()
        if config.max_open_positions <= 0:
            return RiskRuleResult(rule=self.rule_type, latency_ms=(time.monotonic() - start) * 1000)

        count = await self._get_open_position_count(req.user_id)
        if count >= config.max_open_positions:
            return RiskRuleResult(
                rule=self.rule_type, decision=RiskDecision.REJECTED,
                reason=f"Open positions {count} >= limit {config.max_open_positions}.",
                details={"open_positions": count, "limit": config.max_open_positions},
                latency_ms=(time.monotonic() - start) * 1000,
            )
        return RiskRuleResult(rule=self.rule_type, latency_ms=(time.monotonic() - start) * 1000)

    async def _get_open_position_count(self, user_id: str) -> int:
        try:
            supabase = get_supabase()
            rows = await async_safe_execute(
                supabase.table("positions_snapshot")
                .select("quantity").eq("user_id", user_id)
            )
            return len([r for r in rows if r.get("quantity", 0) != 0]) if rows else 0
        except Exception as e:
            logger.warning("Failed to get open positions: %s", e)
            return 0


class MaxQuantityRule(RiskRule):
    rule_type = RiskRuleType.MAX_QUANTITY

    async def evaluate(self, req: ExecutionRequest, config: RiskConfig) -> RiskRuleResult:
        start = time.monotonic()
        if config.max_quantity <= 0:
            return RiskRuleResult(rule=self.rule_type, latency_ms=(time.monotonic() - start) * 1000)
        if req.quantity > config.max_quantity:
            return RiskRuleResult(
                rule=self.rule_type, decision=RiskDecision.REJECTED,
                reason=f"Quantity {req.quantity} exceeds max {config.max_quantity}.",
                details={"quantity": req.quantity, "limit": config.max_quantity},
                latency_ms=(time.monotonic() - start) * 1000,
            )
        return RiskRuleResult(rule=self.rule_type, latency_ms=(time.monotonic() - start) * 1000)


class MaxExposureRule(RiskRule):
    rule_type = RiskRuleType.MAX_EXPOSURE

    async def evaluate(self, req: ExecutionRequest, config: RiskConfig) -> RiskRuleResult:
        start = time.monotonic()
        if config.max_exposure <= 0:
            return RiskRuleResult(rule=self.rule_type, latency_ms=(time.monotonic() - start) * 1000)

        current = await self._get_current_exposure(req.user_id)
        order_value = req.quantity * (req.price or 0)
        if current + order_value > config.max_exposure:
            return RiskRuleResult(
                rule=self.rule_type, decision=RiskDecision.REJECTED,
                reason=f"Exposure {current + order_value:.2f} would exceed limit {config.max_exposure:.2f}.",
                details={"current_exposure": current, "order_value": order_value, "limit": config.max_exposure},
                latency_ms=(time.monotonic() - start) * 1000,
            )
        return RiskRuleResult(rule=self.rule_type, latency_ms=(time.monotonic() - start) * 1000)

    async def _get_current_exposure(self, user_id: str) -> float:
        try:
            supabase = get_supabase()
            rows = await async_safe_execute(
                supabase.table("positions_snapshot")
                .select("quantity, average_buy_price").eq("user_id", user_id)
            )
            return sum(abs(r.get("quantity", 0)) * r.get("average_buy_price", 0) for r in rows) if rows else 0.0
        except Exception as e:
            logger.warning("Failed to get exposure: %s", e)
            return 0.0


class MaxSymbolExposureRule(RiskRule):
    rule_type = RiskRuleType.MAX_SYMBOL_EXPOSURE

    async def evaluate(self, req: ExecutionRequest, config: RiskConfig) -> RiskRuleResult:
        start = time.monotonic()
        if config.max_symbol_exposure <= 0:
            return RiskRuleResult(rule=self.rule_type, latency_ms=(time.monotonic() - start) * 1000)

        current = await self._get_symbol_exposure(req.user_id, req.symbol)
        order_value = req.quantity * (req.price or 0)
        if current + order_value > config.max_symbol_exposure:
            return RiskRuleResult(
                rule=self.rule_type, decision=RiskDecision.REJECTED,
                reason=f"Exposure in {req.symbol} {current + order_value:.2f} exceeds limit {config.max_symbol_exposure:.2f}.",
                details={"symbol": req.symbol, "current_exposure": current, "order_value": order_value, "limit": config.max_symbol_exposure},
                latency_ms=(time.monotonic() - start) * 1000,
            )
        return RiskRuleResult(rule=self.rule_type, latency_ms=(time.monotonic() - start) * 1000)

    async def _get_symbol_exposure(self, user_id: str, symbol: str) -> float:
        try:
            supabase = get_supabase()
            rows = await async_safe_execute(
                supabase.table("positions_snapshot")
                .select("quantity, average_buy_price")
                .eq("user_id", user_id)
                .eq("symbol", symbol)
            )
            return sum(abs(r.get("quantity", 0)) * r.get("average_buy_price", 0) for r in rows) if rows else 0.0
        except Exception as e:
            logger.warning("Failed to get symbol exposure: %s", e)
            return 0.0


class MaxOrdersPerMinuteRule(RiskRule):
    rule_type = RiskRuleType.MAX_ORDERS_PER_MINUTE

    def __init__(self):
        self._order_timestamps: dict[str, deque] = defaultdict(lambda: deque(maxlen=200))

    async def evaluate(self, req: ExecutionRequest, config: RiskConfig) -> RiskRuleResult:
        start = time.monotonic()
        if config.max_orders_per_minute <= 0:
            return RiskRuleResult(rule=self.rule_type, latency_ms=(time.monotonic() - start) * 1000)

        now = time.time()
        user_orders = self._order_timestamps[req.user_id]
        cutoff = now - 60
        while user_orders and user_orders[0] < cutoff:
            user_orders.popleft()
        user_orders.append(now)

        if len(user_orders) > config.max_orders_per_minute:
            return RiskRuleResult(
                rule=self.rule_type, decision=RiskDecision.REJECTED,
                reason=f"Order rate {len(user_orders)}/min exceeds limit {config.max_orders_per_minute}.",
                details={"orders_per_minute": len(user_orders), "limit": config.max_orders_per_minute},
                latency_ms=(time.monotonic() - start) * 1000,
            )
        return RiskRuleResult(rule=self.rule_type, latency_ms=(time.monotonic() - start) * 1000)


class DuplicateOrderRule(RiskRule):
    rule_type = RiskRuleType.DUPLICATE_ORDER

    def __init__(self):
        self._recent_orders: dict[str, set[str]] = defaultdict(set)

    async def evaluate(self, req: ExecutionRequest, config: RiskConfig) -> RiskRuleResult:
        start = time.monotonic()
        dedup_key = f"{req.user_id}:{req.broker}:{req.symbol}:{req.side}:{req.quantity}"
        if dedup_key in self._recent_orders[req.user_id]:
            return RiskRuleResult(
                rule=self.rule_type, decision=RiskDecision.REJECTED,
                reason="Duplicate order detected (same user/broker/symbol/side/quantity).",
                details={"dedup_key": dedup_key},
                latency_ms=(time.monotonic() - start) * 1000,
            )
        self._recent_orders[req.user_id].add(dedup_key)
        if len(self._recent_orders[req.user_id]) > 100:
            self._recent_orders[req.user_id] = set(list(self._recent_orders[req.user_id])[50:])
        return RiskRuleResult(rule=self.rule_type, latency_ms=(time.monotonic() - start) * 1000)


class DailyProfitTargetRule(RiskRule):
    rule_type = RiskRuleType.DAILY_PROFIT_TARGET

    async def evaluate(self, req: ExecutionRequest, config: RiskConfig) -> RiskRuleResult:
        start = time.monotonic()
        if config.daily_profit_target <= 0:
            return RiskRuleResult(rule=self.rule_type, latency_ms=(time.monotonic() - start) * 1000)

        today_pnl = await self._get_today_pnl(req.user_id)
        if today_pnl >= config.daily_profit_target:
            return RiskRuleResult(
                rule=self.rule_type, decision=RiskDecision.WARNING,
                reason=f"Daily profit {today_pnl:.2f} has reached target {config.daily_profit_target:.2f}.",
                details={"daily_pnl": today_pnl, "target": config.daily_profit_target},
                latency_ms=(time.monotonic() - start) * 1000,
            )
        return RiskRuleResult(rule=self.rule_type, latency_ms=(time.monotonic() - start) * 1000)

    async def _get_today_pnl(self, user_id: str) -> float:
        return await _compute_daily_pnl_fifo(user_id)


class MaxCapitalRule(RiskRule):
    rule_type = RiskRuleType.MAX_CAPITAL

    async def evaluate(self, req: ExecutionRequest, config: RiskConfig) -> RiskRuleResult:
        start = time.monotonic()
        if config.max_capital <= 0:
            return RiskRuleResult(rule=self.rule_type, latency_ms=(time.monotonic() - start) * 1000)

        current = await self._get_current_usage(req.user_id)
        order_value = req.quantity * (req.price or 0)
        if current + order_value > config.max_capital:
            return RiskRuleResult(
                rule=self.rule_type, decision=RiskDecision.REJECTED,
                reason=f"Capital usage {current + order_value:.2f} exceeds limit {config.max_capital:.2f}.",
                details={"current_usage": current, "order_value": order_value, "limit": config.max_capital},
                latency_ms=(time.monotonic() - start) * 1000,
            )
        return RiskRuleResult(rule=self.rule_type, latency_ms=(time.monotonic() - start) * 1000)

    async def _get_current_usage(self, user_id: str) -> float:
        try:
            supabase = get_supabase()
            rows = await async_safe_execute(
                supabase.table("positions_snapshot")
                .select("quantity, average_buy_price").eq("user_id", user_id)
            )
            return sum(abs(r.get("quantity", 0)) * r.get("average_buy_price", 0) for r in rows) if rows else 0.0
        except Exception:
            return 0.0


class MaxDrawdownRule(RiskRule):
    rule_type = RiskRuleType.MAX_DRAWDOWN

    async def evaluate(self, req: ExecutionRequest, config: RiskConfig) -> RiskRuleResult:
        start = time.monotonic()
        if config.max_drawdown_pct <= 0:
            return RiskRuleResult(rule=self.rule_type, latency_ms=(time.monotonic() - start) * 1000)

        dd = await self._get_drawdown(req.user_id)
        if dd >= config.max_drawdown_pct:
            return RiskRuleResult(
                rule=self.rule_type, decision=RiskDecision.REJECTED,
                reason=f"Drawdown {dd:.1f}% exceeds limit {config.max_drawdown_pct:.1f}%.",
                details={"drawdown_pct": dd, "limit": config.max_drawdown_pct},
                latency_ms=(time.monotonic() - start) * 1000,
            )
        return RiskRuleResult(rule=self.rule_type, latency_ms=(time.monotonic() - start) * 1000)

    async def _get_drawdown(self, user_id: str) -> float:
        try:
            supabase = get_supabase()
            rows = await async_safe_execute(
                supabase.table("strategy_runs")
                .select("total_pnl").eq("user_id", user_id)
            )
            if not rows:
                return 0.0
            pnls = [float(r.get("total_pnl", 0)) for r in rows]
            peak = max(pnls) if pnls else 0
            current = sum(pnls)
            if peak <= 0:
                return 0.0
            return max(0.0, (peak - current) / peak * 100)
        except Exception:
            return 0.0
