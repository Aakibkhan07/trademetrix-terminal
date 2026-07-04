from __future__ import annotations

import logging
import math
from collections import defaultdict
from typing import Any

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

        dsl_data = config.get("_dsl") if config else None
        if dsl_data:
            if isinstance(dsl_data, dict):
                self._dsl = StrategyDSL(**dsl_data)
            else:
                self._dsl = dsl_data
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
                    if result and isinstance(result, dict) and result.get("triggered", True):
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

        ctx = {
            "candle": candle,
            "series": dict(self._series),
            "memory": self._memory,
            "candle_index": self._candle_index,
            "params": node.params,
            "inputs": inputs,
        }

        return _COMPUTE_FUNCTIONS.get(node.block_type, _compute_default)(ctx)

    def _append_series(self, key: str, value: float) -> None:
        self._series[key].append(value)
        if len(self._series[key]) > 500:
            self._series[key] = self._series[key][-500:]

    def _parse_signal(self, block_type: str, result: dict, candle: Candle) -> SignalResult | None:
        if not result or not result.get("triggered", True):
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


def _get_series(ctx: dict, key: str) -> list[float]:
    return ctx.get("series", {}).get(key, [])


def _get_last(series: list[float]) -> float:
    return series[-1] if series else 0.0


def _get_prev(series: list[float]) -> float:
    return series[-2] if len(series) >= 2 else _get_last(series)


# ─── Compute Functions ───

def _compute_sma(ctx: dict) -> float:
    series = _get_series(ctx, "close")
    period = int(ctx.get("params", {}).get("period", 20))
    if len(series) < period:
        return 0.0
    return sum(series[-period:]) / period


def _compute_ema(ctx: dict) -> float:
    series = _get_series(ctx, "close")
    period = int(ctx.get("params", {}).get("period", 20))
    if len(series) < period:
        return _get_last(series)
    multiplier = 2 / (period + 1)
    ema = sum(series[:period]) / period
    for price in series[period:]:
        ema = (price - ema) * multiplier + ema
    return ema


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
    sig_line = _ema(series, signal)
    return {"macd_line": macd_line, "signal_line": sig_line, "histogram": macd_line - sig_line}


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
    if not series_close or not series_volume:
        return {"value": 0, "deviation": 0, "deviation_pct": 0}
    tp = sum((series_close[i] + _get_series(ctx, "high")[i] + _get_series(ctx, "low")[i]) / 3 * series_volume[i]
             for i in range(len(series_close)) if i < len(series_volume))
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


def _compute_cross_above(ctx: dict) -> dict:
    inputs = ctx.get("inputs", {})
    series_a = _get_series(ctx, "close")
    series_b_val = inputs.get("b", 0)
    if isinstance(series_b_val, (int, float)):
        target = series_b_val
    else:
        target = series_b_val[-1] if isinstance(series_b_val, list) and series_b_val else 0
    if len(series_a) >= 2:
        triggered = series_a[-2] <= target and series_a[-1] > target
        return {"triggered": triggered, "crossover_value": series_a[-1]}
    return {"triggered": False, "crossover_value": 0}


def _compute_cross_below(ctx: dict) -> dict:
    series_a = _get_series(ctx, "close")
    inputs = ctx.get("inputs", {})
    series_b_val = inputs.get("b", 0)
    if isinstance(series_b_val, (int, float)):
        target = series_b_val
    else:
        target = series_b_val[-1] if isinstance(series_b_val, list) and series_b_val else 0
    if len(series_a) >= 2:
        triggered = series_a[-2] >= target and series_a[-1] < target
        return {"triggered": triggered, "crossunder_value": series_a[-1]}
    return {"triggered": False, "crossunder_value": 0}


def _compute_order_buy(ctx: dict) -> dict:
    params = ctx.get("params", {})
    return {
        "triggered": True,
        "meta": {
            "quantity": int(params.get("quantity", 0) or ctx.get("config", {}).get("quantity", 75)),
            "order_type": params.get("order_type", "MARKET"),
            "product": params.get("product", "INTRADAY"),
            "reason": params.get("reason", ""),
        },
    }


def _compute_order_sell(ctx: dict) -> dict:
    params = ctx.get("params", {})
    return {
        "triggered": True,
        "meta": {
            "quantity": int(params.get("quantity", 0) or ctx.get("config", {}).get("quantity", 75)),
            "order_type": params.get("order_type", "MARKET"),
            "product": params.get("product", "INTRADAY"),
            "reason": params.get("reason", ""),
        },
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
        return not bool(a)
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


_COMPUTE_FUNCTIONS: dict[str, callable] = {
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
    "signal.divergence": _compute_signal_divergence,
    "order.buy": _compute_order_buy,
    "order.sell": _compute_order_sell,
    "smc.order_block": _compute_order_block,
    "smc.liquidity_grab": _compute_liquidity_grab,
    "smc.fvg": _compute_fvg,
    "source.position": _compute_source_position,
    "candle.bullish": _compute_candle_bullish,
    "candle.bearish": _compute_candle_bearish,
    "candle.doji": _compute_candle_doji,
}
