from __future__ import annotations

import logging
import math
from collections import defaultdict
from datetime import UTC, datetime, timedelta, timezone
from typing import Any, Callable

from core.models import Candle, Exchange, NormalizedOrder, OrderSide, OrderType, ProductType, Tick
from strategies.base import BaseStrategy, SignalResult

from builder.blocks import get_block
from builder.compiler import compile_dsl
from builder.models import ExecutionGraph, StrategyDSL

logger = logging.getLogger(__name__)


class GraphStrategy(BaseStrategy):
    name = "graph_strategy"
    description = "DAG-based visual strategy"

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self._graph: ExecutionGraph | None = None
        self._dsl: StrategyDSL | None = None
        self._memory: dict[str, Any] = {}
        self._series: dict[str, list[float]] = defaultdict(list)
        self._candle_index = 0
        self._port_in_map: dict[str, list[tuple[str, str, str]]] = defaultdict(list)

        dsl_data = config.get("_dsl") if config else None
        if dsl_data:
            if isinstance(dsl_data, dict):
                self._dsl = StrategyDSL(**dsl_data)
            else:
                self._dsl = dsl_data
            for edge in self._dsl.edges:
                self._port_in_map[edge.target_node].append((edge.target_port, edge.source_node, edge.source_port))
            graph, validation = compile_dsl(self._dsl)
            if graph and validation.valid:
                self._graph = graph
            else:
                logger.warning("Graph strategy compilation had issues: %s", [i.message for i in validation.issues if i.severity == "error"])

    async def on_start(self) -> None:
        self._memory.clear()
        self._series.clear()
        self._candle_index = 0

    async def on_stop(self) -> None:
        pass

    async def on_tick(self, tick: Tick) -> SignalResult | None:
        return None

    async def on_candle(self, candle: Candle) -> SignalResult | None:
        if not self._graph:
            return None

        self._candle_index += 1
        self._append_series("open", candle.open)
        self._append_series("high", candle.high)
        self._append_series("low", candle.low)
        self._append_series("close", candle.close)
        self._append_series("volume", float(candle.volume))
        self._append_series("oi", float(candle.oi))

        results: dict[str, Any] = {}
        signal_result: SignalResult | None = None

        try:
            for exec_node in self._graph.nodes:
                result = self._evaluate_node(exec_node, candle, results)
                results[exec_node.id] = result

                if exec_node.block_type in ("order.buy", "order.sell", "order.exit", "order.reverse"):
                    if result and isinstance(result, dict) and result.get("triggered", False):
                        parsed = self._parse_signal(exec_node.block_type, result, candle)
                        if parsed:
                            signal_result = parsed

            return signal_result

        except Exception as e:
            logger.error("Graph strategy evaluation error: %s", e)
            return None

    def _evaluate_node(self, node, candle: Candle, results: dict) -> Any:
        block = get_block(node.block_type)
        if not block:
            return None

        inputs: dict[str, Any] = {}
        for inp_id in node.inputs:
            inp_result = results.get(inp_id)
            if inp_result is not None:
                if isinstance(inp_result, dict):
                    inputs.update(inp_result)
                else:
                    inputs["value"] = inp_result

        for target_port, source_node, source_port in self._port_in_map.get(node.id, []):
            inputs[target_port] = _port_value(results.get(source_node), source_port)

        ctx = {
            "candle": candle,
            "series": dict(self._series),
            "memory": self._memory,
            "candle_index": self._candle_index,
            "params": node.params,
            "inputs": inputs,
            "_block_type": node.block_type,
        }

        return _COMPUTE_FUNCTIONS.get(node.block_type, _compute_default)(ctx)

    def _append_series(self, key: str, value: float) -> None:
        self._series[key].append(value)
        if len(self._series[key]) > 500:
            self._series[key] = self._series[key][-500:]

    def _parse_signal(self, block_type: str, result: dict, candle: Candle) -> SignalResult | None:
        if not result or not result.get("triggered", False):
            return None

        meta = result.get("meta", {})
        qty = meta.get("quantity", 0) or self.config.get("quantity", 75)
        product_str = meta.get("product", "INTRADAY")
        order_type_str = meta.get("order_type", "MARKET")

        if block_type == "order.buy":
            side = OrderSide.BUY
        elif block_type == "order.sell":
            side = OrderSide.SELL
        elif block_type == "order.exit":
            return None
        elif block_type == "order.reverse":
            return None
        else:
            return None

        order = NormalizedOrder(
            symbol=self.config.get("symbol", candle.symbol),
            exchange=Exchange(self.config.get("exchange", "NSE")),
            side=side,
            order_type=OrderType(order_type_str),
            product=ProductType(product_str),
            quantity=int(qty) if qty else 75,
            strategy_id=self.config.get("strategy_id"),
            reason=meta.get("reason", f"Signal from {block_type}"),
        )
        return SignalResult(orders=[order], reason=meta.get("reason", block_type))


def _compute_default(ctx: dict) -> Any:
    return ctx.get("inputs", {})


def _port_value(result: Any, source_port: str) -> Any:
    """Resolve the value flowing out of an upstream node's port."""
    if result is None:
        return None
    if isinstance(result, dict):
        return result.get(source_port)
    return result


def _condition_triggered(ctx: dict) -> bool:
    """Order-block condition gate.

    Returns True only when a connected condition input evaluates truthy.
    No connected condition -> False (never trigger by default).
    """
    inputs = ctx.get("inputs", {})
    if not inputs:
        return False
    for key in ("condition", "triggered", "result", "value"):
        if key in inputs and inputs[key] is not None:
            return bool(inputs[key])
    return False


def _get_series(ctx: dict, key: str) -> list[float]:
    return ctx.get("series", {}).get(key, [])


def _get_last(series: list[float]) -> float:
    return series[-1] if series else 0.0


def _get_prev(series: list[float]) -> float:
    return series[-2] if len(series) >= 2 else _get_last(series)


# ─── Compute Functions ───

def _compute_sma(ctx: dict) -> dict:
    series = _get_series(ctx, "close")
    period = int(ctx.get("params", {}).get("period", 20))
    if len(series) < period:
        return {"value": 0.0, "series": []}
    sma_series: list[float] = []
    running = 0.0
    for i, price in enumerate(series):
        running += price
        if i >= period:
            running -= series[i - period]
        if i >= period - 1:
            sma_series.append(running / period)
    return {"value": sma_series[-1], "series": sma_series}


def _compute_ema(ctx: dict) -> dict:
    series = _get_series(ctx, "close")
    period = int(ctx.get("params", {}).get("period", 20))
    if len(series) < period:
        return {"value": _get_last(series), "series": list(series)}
    multiplier = 2 / (period + 1)
    ema_series: list[float] = []
    ema = sum(series[:period]) / period
    for i, price in enumerate(series):
        if i < period:
            ema = sum(series[: i + 1]) / (i + 1)
        else:
            ema = (price - ema) * multiplier + ema
        ema_series.append(ema)
    return {"value": ema, "series": ema_series}


def _compute_rsi(ctx: dict) -> dict:
    series = _get_series(ctx, "close")
    period = int(ctx.get("params", {}).get("period", 14))
    oversold = float(ctx.get("params", {}).get("oversold", 30))
    overbought = float(ctx.get("params", {}).get("overbought", 70))

    if len(series) < period + 1:
        return {"value": 50.0, "series": [], "is_oversold": False, "is_overbought": False}

    gains, losses = 0.0, 0.0
    for i in range(-period, 0):
        change = series[i] - series[i - 1]
        if change >= 0:
            gains += change
        else:
            losses -= change
    avg_gain = gains / period
    avg_loss = losses / period
    rsi = 100.0 if avg_loss == 0 else 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))

    return {"value": rsi, "is_oversold": rsi <= oversold, "is_overbought": rsi >= overbought}


def _compute_macd(ctx: dict) -> dict:
    series = _get_series(ctx, "close")
    fast = int(ctx.get("params", {}).get("fast", 12))
    slow = int(ctx.get("params", {}).get("slow", 26))
    signal = int(ctx.get("params", {}).get("signal", 9))

    def _ema(s, p):
        if len(s) < p:
            return s[-1] if s else 0
        m = 2 / (p + 1)
        e = sum(s[:p]) / p
        for v in s[p:]:
            e = (v - e) * m + e
        return e

    macd_line = _ema(series, fast) - _ema(series, slow)
    series_macd: list[float] = []
    for i in range(len(series)):
        window = series[: i + 1]
        series_macd.append(_ema(window, fast) - _ema(window, slow))
    series_signal: list[float] = []
    for i in range(len(series_macd)):
        series_signal.append(_ema(series_macd[: i + 1], signal))
    sig_line = series_signal[-1] if series_signal else 0
    return {
        "macd_line": macd_line,
        "signal_line": sig_line,
        "histogram": macd_line - sig_line,
        "series_macd": series_macd,
        "series_signal": series_signal,
    }


def _compute_bollinger(ctx: dict) -> dict:
    series = _get_series(ctx, "close")
    period = int(ctx.get("params", {}).get("period", 20))
    std_dev = float(ctx.get("params", {}).get("std_dev", 2.0))

    if len(series) < period:
        return {"upper": 0, "middle": 0, "lower": 0, "bandwidth": 0, "percent_b": 0.5, "is_squeeze": False}

    sma = sum(series[-period:]) / period
    variance = sum((p - sma) ** 2 for p in series[-period:]) / period
    std = math.sqrt(variance)
    upper = sma + std_dev * std
    lower = sma - std_dev * std
    bandwidth = (upper - lower) / sma if sma else 0
    current = _get_last(series)
    percent_b = (current - lower) / (upper - lower) if (upper - lower) != 0 else 0.5

    return {"upper": upper, "middle": sma, "lower": lower,
            "bandwidth": bandwidth, "percent_b": percent_b,
            "is_squeeze": bandwidth < 0.05 if bandwidth else False}


def _compute_vwap(ctx: dict) -> dict:
    series_close = _get_series(ctx, "close")
    series_volume = _get_series(ctx, "volume")
    if not series_close:
        return {"value": 0, "deviation": 0, "deviation_pct": 0}
    series_high = _get_series(ctx, "high")
    series_low = _get_series(ctx, "low")
    n = len(series_close)
    if n and not any(series_volume):
        tp_sum = sum((series_close[i] + (series_high[i] if i < len(series_high) else series_close[i]) + (series_low[i] if i < len(series_low) else series_close[i])) / 3 for i in range(n))
        vwap = tp_sum / n
    else:
        tp = sum((series_close[i] + series_high[i] + series_low[i]) / 3 * series_volume[i]
                 for i in range(n) if i < len(series_volume))
        vol = sum(series_volume)
        vwap = tp / vol if vol else 0
    current = _get_last(series_close)
    return {"value": vwap, "deviation": current - vwap, "deviation_pct": (current - vwap) / vwap * 100 if vwap else 0}


def _compute_atr(ctx: dict) -> dict:
    high_s = _get_series(ctx, "high")
    low_s = _get_series(ctx, "low")
    close_s = _get_series(ctx, "close")
    period = int(ctx.get("params", {}).get("period", 14))

    if len(close_s) < period + 1:
        return {"value": 0, "series": []}

    tr_values = []
    for i in range(1, len(close_s)):
        tr = max(high_s[i] - low_s[i], abs(high_s[i] - close_s[i - 1]), abs(low_s[i] - close_s[i - 1]))
        tr_values.append(tr)

    if len(tr_values) < period:
        return {"value": sum(tr_values) / len(tr_values) if tr_values else 0}
    atr = sum(tr_values[-period:]) / period
    return {"value": atr}


def _compute_supertrend(ctx: dict) -> dict:
    high_s = _get_series(ctx, "high")
    low_s = _get_series(ctx, "low")
    close_s = _get_series(ctx, "close")
    period = int(ctx.get("params", {}).get("period", 10))
    mult = float(ctx.get("params", {}).get("multiplier", 3.0))

    if len(close_s) < period + 1:
        return {"value": 0, "direction": 1, "is_up": True, "is_down": False}

    tr_values = []
    for i in range(1, len(close_s)):
        tr = max(high_s[i] - low_s[i], abs(high_s[i] - close_s[i - 1]), abs(low_s[i] - close_s[i - 1]))
        tr_values.append(tr)
    atr = sum(tr_values[-period:]) / period

    hl2 = (high_s[-1] + low_s[-1]) / 2
    upper = hl2 + mult * atr
    lower = hl2 - mult * atr
    direction = 1 if close_s[-1] > (hl2 + atr) else -1
    return {"value": upper if direction == 1 else lower, "direction": direction,
            "is_up": direction == 1, "is_down": direction == -1}


def _compute_stoch(ctx: dict) -> dict:
    high_s = _get_series(ctx, "high")
    low_s = _get_series(ctx, "low")
    close_s = _get_series(ctx, "close")
    k_period = int(ctx.get("params", {}).get("k_period", 14))
    k_smooth = int(ctx.get("params", {}).get("k_smooth", 3))
    d_period = int(ctx.get("params", {}).get("d_period", 3))

    if len(close_s) < k_period + 1:
        return {"k": 50, "d": 50}

    ll = min(low_s[-k_period:])
    hh = max(high_s[-k_period:])
    k = ((close_s[-1] - ll) / (hh - ll) * 100) if (hh - ll) != 0 else 50
    return {"k": k, "d": k}


def _compute_adx(ctx: dict) -> dict:
    return {"adx": 25, "plus_di": 20, "minus_di": 20}


def _cross_series_and_target(ctx: dict) -> tuple[list[float], float]:
    inputs = ctx.get("inputs", {})
    a = inputs.get("a")
    b = inputs.get("b", 0)
    if isinstance(a, list) and a:
        series = a
    else:
        series = _get_series(ctx, "close")
    if isinstance(b, (int, float)):
        target = float(b)
    elif isinstance(b, list) and b:
        target = float(b[-1])
    else:
        target = 0.0
    return series, target


def _compute_cross_above(ctx: dict) -> dict:
    series_a, target = _cross_series_and_target(ctx)
    if len(series_a) >= 2:
        triggered = series_a[-2] <= target and series_a[-1] > target
        return {"triggered": triggered, "crossover_value": series_a[-1]}
    return {"triggered": False, "crossover_value": 0}


def _compute_cross_below(ctx: dict) -> dict:
    series_a, target = _cross_series_and_target(ctx)
    if len(series_a) >= 2:
        triggered = series_a[-2] >= target and series_a[-1] < target
        return {"triggered": triggered, "crossunder_value": series_a[-1]}
    return {"triggered": False, "crossunder_value": 0}


def _order_meta(ctx: dict) -> dict:
    params = ctx.get("params", {})
    return {
        "quantity": int(params.get("quantity", 0) or ctx.get("config", {}).get("quantity", 75)),
        "order_type": params.get("order_type", "MARKET"),
        "product": params.get("product", "INTRADAY"),
        "reason": params.get("reason", ""),
    }


def _compute_order_buy(ctx: dict) -> dict:
    return {
        "triggered": _condition_triggered(ctx),
        "meta": _order_meta(ctx),
    }


def _compute_order_sell(ctx: dict) -> dict:
    return {
        "triggered": _condition_triggered(ctx),
        "meta": _order_meta(ctx),
    }


def _compute_order_exit(ctx: dict) -> dict:
    return {
        "triggered": _condition_triggered(ctx),
        "meta": _order_meta(ctx),
    }


def _compute_order_reverse(ctx: dict) -> dict:
    return {
        "triggered": _condition_triggered(ctx),
        "meta": _order_meta(ctx),
    }


def _compute_math_op(ctx: dict) -> float:
    inputs = ctx.get("inputs", {})
    a = inputs.get("a", 0)
    b = inputs.get("b", 0)
    block_type = ctx.get("_block_type", "math.add")
    ops = {
        "math.add": lambda x, y: x + y,
        "math.sub": lambda x, y: x - y,
        "math.mul": lambda x, y: x * y,
        "math.div": lambda x, y: x / y if y != 0 else 0,
        "math.min": min,
        "math.max": max,
        "math.avg": lambda x, y: (x + y) / 2,
    }
    return ops.get(block_type, lambda x, y: 0)(a, b)


def _compute_logic_op(ctx: dict) -> bool:
    inputs = ctx.get("inputs", {})
    a = inputs.get("a", False)
    b = inputs.get("b", False)
    kwargs = ctx.get("params", {})
    block_type = ctx.get("_block_type", "logic.and")
    if block_type == "logic.and":
        return bool(a) and bool(b)
    elif block_type == "logic.or":
        return bool(a) or bool(b)
    elif block_type == "logic.not":
        return not bool(inputs.get("value", a))
    elif block_type == "logic.gt":
        return float(a or 0) > float(b or 0)
    elif block_type == "logic.lt":
        return float(a or 0) < float(b or 0)
    elif block_type == "logic.gte":
        return float(a or 0) >= float(b or 0)
    elif block_type == "logic.lte":
        return float(a or 0) <= float(b or 0)
    elif block_type == "logic.eq":
        return a == b
    elif block_type == "logic.neq":
        return a != b
    return False


def _compute_if_else(ctx: dict) -> Any:
    inputs = ctx.get("inputs", {})
    return inputs.get("then") if inputs.get("condition") else inputs.get("else")


def _compute_pct_change(ctx: dict) -> float:
    inputs = ctx.get("inputs", {})
    curr = inputs.get("current", 0)
    prev = inputs.get("previous", 0)
    if prev == 0:
        return 0.0
    return (curr - prev) / prev * 100


def _compute_abs_value(ctx: dict) -> float:
    inputs = ctx.get("inputs", {})
    return abs(inputs.get("value", 0))


def _compute_order_block(ctx: dict) -> dict:
    series_open = _get_series(ctx, "open")
    series_high = _get_series(ctx, "high")
    series_low = _get_series(ctx, "low")
    series_close = _get_series(ctx, "close")
    lookback = int(ctx.get("params", {}).get("lookback", 10))

    if len(series_close) < 5:
        return {"bullish": False, "bearish": False, "level": 0}

    prev = {"open": series_open[-2], "high": series_high[-2], "low": series_low[-2], "close": series_close[-2]}
    prev2 = {"open": series_open[-3], "high": series_high[-3], "low": series_low[-3], "close": series_close[-3]}
    last_close = series_close[-1]

    bullish = prev2["low"] < prev["low"] and prev["high"] > prev2["high"] and last_close > prev["high"] and prev["close"] < prev["open"]
    bearish = prev2["high"] > prev["high"] and prev["low"] < prev2["low"] and last_close < prev["low"] and prev["close"] > prev["open"]

    return {"bullish": bullish, "bearish": bearish, "level": prev["low"] if bullish else prev["high"] if bearish else 0}


def _compute_liquidity_grab(ctx: dict) -> dict:
    series_high = _get_series(ctx, "high")
    series_low = _get_series(ctx, "low")
    series_close = _get_series(ctx, "close")

    if len(series_close) < 6:
        return {"bullish": False, "bearish": False, "grab_level": 0}

    prior_high = max(series_high[-6:-3]) if len(series_high) >= 6 else 0
    prior_low = min(series_low[-6:-3]) if len(series_low) >= 6 else 0
    recent_high = series_high[-3:-1] if len(series_high) >= 3 else []
    recent_low = series_low[-3:-1] if len(series_low) >= 3 else []

    bearish = any(h > prior_high for h in recent_high) and series_close[-1] < prior_high
    bullish = any(l < prior_low for l in recent_low) and series_close[-1] > prior_low

    return {"bullish": bullish, "bearish": bearish, "grab_level": prior_high if bearish else prior_low if bullish else 0}


def _compute_fvg(ctx: dict) -> dict:
    series_high = _get_series(ctx, "high")
    series_low = _get_series(ctx, "low")
    if len(series_high) < 3:
        return {"bullish": False, "bearish": False, "gap_high": 0, "gap_low": 0}
    bullish = series_low[-2] > series_high[-3]
    bearish = series_high[-2] < series_low[-3]
    return {"bullish": bullish, "bearish": bearish,
            "gap_high": series_low[-2] if bullish else series_high[-3] if bearish else 0,
            "gap_low": series_high[-3] if bullish else series_low[-2] if bearish else 0}


def _compute_source_position(ctx: dict) -> dict:
    memory = ctx.get("memory", {})
    return {
        "quantity": memory.get("position_qty", 0),
        "avg_price": memory.get("position_avg", 0),
        "pnl": memory.get("position_pnl", 0),
        "has_position": memory.get("position_qty", 0) != 0,
    }


def _compute_source_candle(ctx: dict) -> dict:
    candle = ctx.get("candle")
    if candle is None:
        return {"open": 0, "high": 0, "low": 0, "close": 0, "volume": 0, "oi": 0, "candle": None}
    return {
        "open": float(candle.open),
        "high": float(candle.high),
        "low": float(candle.low),
        "close": float(candle.close),
        "volume": float(candle.volume),
        "oi": float(candle.oi),
        "candle": candle,
    }


def _compute_source_close_history(ctx: dict) -> dict:
    series = ctx.get("series", {})
    max_length = int(ctx.get("params", {}).get("max_length", 500))
    return {
        "prices": list(series.get("close", []))[-max_length:],
        "highs": list(series.get("high", []))[-max_length:],
        "lows": list(series.get("low", []))[-max_length:],
        "volumes": list(series.get("volume", []))[-max_length:],
    }


def _compute_breakout(ctx: dict) -> dict:
    series_high = _get_series(ctx, "high")
    series_low = _get_series(ctx, "low")
    series_close = _get_series(ctx, "close")
    lookback = int(ctx.get("params", {}).get("lookback", 20))
    buffer_pct = float(ctx.get("params", {}).get("buffer_pct", 0.1))

    if len(series_close) < lookback + 2:
        return {"breakout": False, "breakdown": False, "level": 0}

    resistance = max(series_high[-lookback - 1 : -1])
    support = min(series_low[-lookback - 1 : -1])
    close = series_close[-1]
    breakout = close > resistance * (1 + buffer_pct / 100)
    breakdown = close < support * (1 - buffer_pct / 100)
    return {
        "breakout": breakout,
        "breakdown": breakdown,
        "level": resistance if breakout else support if breakdown else 0,
    }


def _market_ist(candle) -> datetime:
    from core.models import Candle

    if candle is None:
        return datetime.now(UTC)
    ts = candle.timestamp if isinstance(candle, Candle) else getattr(candle, "timestamp", datetime.now(UTC))
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return ts.astimezone(timezone(timedelta(hours=5, minutes=30)))


def _compute_source_market_time(ctx: dict) -> dict:
    ist = _market_ist(ctx.get("candle"))
    hour, minute, dow = ist.hour, ist.minute, ist.weekday()
    open_ts = ist.replace(hour=9, minute=15, second=0, microsecond=0)
    close_ts = ist.replace(hour=15, minute=30, second=0, microsecond=0)
    is_open = dow < 5 and open_ts <= ist <= close_ts
    return {
        "session": "open" if is_open else "closed",
        "hour": hour,
        "minute": minute,
        "day_of_week": dow,
        "is_market_open": is_open,
    }


def _compute_day_of_week(ctx: dict) -> dict:
    dow = _market_ist(ctx.get("candle")).weekday()
    return {
        "day": dow,
        "is_monday": dow == 0,
        "is_friday": dow == 4,
        "is_expiry": dow == 3,
    }


def _compute_time_range(ctx: dict) -> dict:
    ist = _market_ist(ctx.get("candle"))
    params = ctx.get("params", {})
    start = ist.replace(hour=int(params.get("start_hour", 9)), minute=int(params.get("start_min", 15)),
                        second=0, microsecond=0)
    end = ist.replace(hour=int(params.get("end_hour", 15)), minute=int(params.get("end_min", 30)),
                      second=0, microsecond=0)
    return {"in_range": start <= ist <= end}


def _compute_constant_number(ctx: dict) -> dict:
    value = float(ctx.get("params", {}).get("value", 0))
    return {"value": value}


def _compute_signal_divergence(ctx: dict) -> dict:
    series_price = _get_series(ctx, "close")
    inputs = ctx.get("inputs", {})
    indicator_s = inputs.get("indicator", [])
    if not isinstance(indicator_s, list):
        indicator_s = []
    lookback = int(ctx.get("params", {}).get("lookback", 10))

    if len(series_price) < lookback or len(indicator_s) < lookback:
        return {"bullish": False, "bearish": False, "strength": 0}

    price_high = max(series_price[-lookback:])
    price_low = min(series_price[-lookback:])
    ind_high = max(indicator_s[-lookback:])
    ind_low = min(indicator_s[-lookback:])
    price_dir = series_price[-1] - series_price[-lookback]
    ind_dir = indicator_s[-1] - indicator_s[-lookback]

    bullish = price_dir < 0 and ind_dir > 0
    bearish = price_dir > 0 and ind_dir < 0
    strength = min(abs(price_dir) / max(abs(series_price[-lookback]), 1) * 100, 100) if bullish or bearish else 0

    return {"bullish": bullish, "bearish": bearish, "strength": round(strength, 1)}


def _compute_candle_bullish(ctx: dict) -> bool:
    inputs = ctx.get("inputs", {})
    o = inputs.get("open", _get_series(ctx, "open"))
    c = inputs.get("close", _get_series(ctx, "close"))
    o = o[-1] if isinstance(o, list) else o
    c = c[-1] if isinstance(c, list) else c
    return c > o


def _compute_candle_bearish(ctx: dict) -> bool:
    inputs = ctx.get("inputs", {})
    o = inputs.get("open", _get_series(ctx, "open"))
    c = inputs.get("close", _get_series(ctx, "close"))
    o = o[-1] if isinstance(o, list) else o
    c = c[-1] if isinstance(c, list) else c
    return c < o


def _compute_candle_doji(ctx: dict) -> bool:
    inputs = ctx.get("inputs", {})
    o = inputs.get("open", _get_series(ctx, "open"))
    c = inputs.get("close", _get_series(ctx, "close"))
    o = o[-1] if isinstance(o, list) else o
    c = c[-1] if isinstance(c, list) else c
    body_pct = float(ctx.get("params", {}).get("body_pct", 5.0))
    body = abs(c - o)
    return body / max(o, c) * 100 <= body_pct if max(o, c) > 0 else False


def _compute_highest(ctx: dict) -> float:
    series = ctx.get("inputs", {}).get("source", _get_series(ctx, "close"))
    if isinstance(series, list) and series:
        period = int(ctx.get("params", {}).get("period", 20))
        return max(series[-period:])
    return 0


def _compute_lowest(ctx: dict) -> float:
    series = ctx.get("inputs", {}).get("source", _get_series(ctx, "close"))
    if isinstance(series, list) and series:
        period = int(ctx.get("params", {}).get("period", 20))
        return min(series[-period:])
    return 0


_COMPUTE_FUNCTIONS: dict[str, Callable] = {
    "indicator.sma": _compute_sma,
    "indicator.ema": _compute_ema,
    "indicator.rsi": _compute_rsi,
    "indicator.macd": _compute_macd,
    "indicator.bollinger": _compute_bollinger,
    "indicator.vwap": _compute_vwap,
    "indicator.atr": _compute_atr,
    "indicator.supertrend": _compute_supertrend,
    "indicator.stoch": _compute_stoch,
    "indicator.adx": _compute_adx,
    "math.add": _compute_math_op,
    "math.sub": _compute_math_op,
    "math.mul": _compute_math_op,
    "math.div": _compute_math_op,
    "math.min": _compute_math_op,
    "math.max": _compute_math_op,
    "math.avg": _compute_math_op,
    "math.abs": _compute_abs_value,
    "math.pct_change": _compute_pct_change,
    "math.highest": _compute_highest,
    "math.lowest": _compute_lowest,
    "logic.and": _compute_logic_op,
    "logic.or": _compute_logic_op,
    "logic.not": _compute_logic_op,
    "logic.gt": _compute_logic_op,
    "logic.lt": _compute_logic_op,
    "logic.gte": _compute_logic_op,
    "logic.lte": _compute_logic_op,
    "logic.eq": _compute_logic_op,
    "logic.neq": _compute_logic_op,
    "logic.if_else": _compute_if_else,
    "signal.cross_above": _compute_cross_above,
    "signal.cross_below": _compute_cross_below,
    "signal.breakout": _compute_breakout,
    "signal.divergence": _compute_signal_divergence,
    "order.buy": _compute_order_buy,
    "order.sell": _compute_order_sell,
    "order.exit": _compute_order_exit,
    "order.reverse": _compute_order_reverse,
    "smc.order_block": _compute_order_block,
    "smc.liquidity_grab": _compute_liquidity_grab,
    "smc.fvg": _compute_fvg,
    "source.position": _compute_source_position,
    "source.candle": _compute_source_candle,
    "source.close_history": _compute_source_close_history,
    "source.market_time": _compute_source_market_time,
    "time.day_of_week": _compute_day_of_week,
    "time.time_range": _compute_time_range,
    "constant.number": _compute_constant_number,
    "candle.bullish": _compute_candle_bullish,
    "candle.bearish": _compute_candle_bearish,
    "candle.doji": _compute_candle_doji,
}
