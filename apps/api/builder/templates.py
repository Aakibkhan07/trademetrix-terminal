from builder.models import StrategyDSL, GraphNode, GraphEdge, StrategySettings, Position


def _n(block_type: str, x: float, y: float, params: dict | None = None, node_id: str | None = None) -> GraphNode:
    return GraphNode(block_type=block_type, position=Position(x=x, y=y), params=params or {})


def _e(source: str, sp: str, target: str, tp: str) -> GraphEdge:
    return GraphEdge(source_node=source, source_port=sp, target_node=target, target_port=tp)


def _dsl(name: str, desc: str, nodes: list[GraphNode], edges: list[GraphEdge],
         settings: dict | None = None, tags: list[str] | None = None) -> StrategyDSL:
    return StrategyDSL(
        name=name, description=desc, nodes=nodes, edges=edges,
        settings=StrategySettings(**(settings or {})),
        tags=tags or [],
    )


# ─── Template 1: EMA Crossover ───

T_EMA_CROSS = _dsl(
    name="EMA Crossover",
    desc="Classic EMA crossover strategy. Generates BUY when fast EMA crosses above slow EMA, SELL on cross below.",
    nodes=[
        _n("source.candle", 50, 50),
        _n("source.close_history", 50, 200, {"max_length": 100}),
        _n("indicator.ema", 300, 50, {"period": 9}),
        _n("indicator.ema", 300, 200, {"period": 21}),
        _n("signal.cross_above", 550, 50),
        _n("signal.cross_below", 550, 200),
        _n("order.buy", 800, 50, {"quantity": 75, "reason": "Bullish EMA crossover"}),
        _n("order.sell", 800, 200, {"quantity": 75, "reason": "Bearish EMA crossover"}),
    ],
    edges=[
        _e("n0", "close", "n2", "source"),
        _e("n0", "close", "n3", "source"),
        _e("n2", "series", "n4", "a"),
        _e("n3", "series", "n4", "b"),
        _e("n2", "series", "n5", "a"),
        _e("n3", "series", "n5", "b"),
        _e("n4", "triggered", "n6", "condition"),
        _e("n5", "triggered", "n7", "condition"),
    ],
    settings={"symbol": "NIFTY", "interval": "15m", "max_positions": 1},
    tags=["trend", "ema", "crossover", "beginner"],
)


# ─── Template 2: ORB (Opening Range Breakout) ───

T_ORB = _dsl(
    name="Opening Range Breakout",
    desc="Trades breakouts from the first N minutes of trading range. BUY above range high, SELL below range low.",
    nodes=[
        _n("source.candle", 50, 50),
        _n("source.market_time", 50, 200),
        _n("signal.breakout", 300, 50, {"lookback": 5, "buffer_pct": 0.1}),
        _n("order.buy", 550, 50, {"quantity": 50, "reason": "ORB breakout above range"}),
        _n("order.sell", 550, 200, {"quantity": 50, "reason": "ORB breakdown below range"}),
    ],
    edges=[
        _e("n0", "high", "n2", "high"),
        _e("n0", "low", "n2", "low"),
        _e("n0", "close", "n2", "close"),
        _e("n2", "breakout", "n3", "condition"),
        _e("n2", "breakdown", "n4", "condition"),
    ],
    settings={"symbol": "BANKNIFTY", "interval": "5m", "max_positions": 1},
    tags=["breakout", "opening-range", "intraday"],
)


# ─── Template 3: VWAP Mean Reversion ───

T_VWAP = _dsl(
    name="VWAP Mean Reversion",
    desc="Mean reverts around VWAP. BUY when price is below VWAP by threshold, SELL when above.",
    nodes=[
        _n("source.candle", 50, 50),
        _n("indicator.vwap", 300, 50),
        _n("logic.gt", 500, 50),
        _n("logic.lt", 500, 200),
        _n("order.sell", 700, 50, {"quantity": 75, "reason": "Price above VWAP deviation threshold"}),
        _n("order.buy", 700, 200, {"quantity": 75, "reason": "Price below VWAP deviation threshold"}),
    ],
    edges=[
        _e("n1", "deviation_pct", "n2", "a"),
        _e("n1", "deviation_pct", "n3", "a"),
        _e("n2", "result", "n4", "condition"),
        _e("n3", "result", "n5", "condition"),
    ],
    settings={"symbol": "NIFTY", "interval": "5m", "max_positions": 2},
    tags=["mean-reversion", "vwap", "intraday"],
)


# ─── Template 4: RSI Mean Reversion ───

T_RSI = _dsl(
    name="RSI Mean Reversion",
    desc="Mean reversion using RSI. BUY when RSI crosses above oversold, SELL when crosses below overbought.",
    nodes=[
        _n("source.candle", 50, 50),
        _n("source.close_history", 50, 200, {"max_length": 100}),
        _n("indicator.rsi", 300, 50, {"period": 14, "oversold": 30, "overbought": 70}),
        _n("order.buy", 550, 50, {"quantity": 75, "reason": "RSI oversold bounce"}),
        _n("order.sell", 550, 200, {"quantity": 75, "reason": "RSI overbought reversal"}),
    ],
    edges=[
        _e("n1", "prices", "n2", "source"),
        _e("n2", "is_oversold", "n3", "condition"),
        _e("n2", "is_overbought", "n4", "condition"),
    ],
    settings={"symbol": "NIFTY", "interval": "15m", "max_positions": 1},
    tags=["mean-reversion", "rsi", "oscillator"],
)


# ─── Template 5: Bollinger Bandit ───

T_BOLLINGER = _dsl(
    name="Bollinger Bandit",
    desc="Fades touches of outer Bollinger Bands. BUY when price bounces off lower band, SELL when rejected from upper band.",
    nodes=[
        _n("source.candle", 50, 50),
        _n("source.close_history", 50, 200, {"max_length": 100}),
        _n("indicator.bollinger", 300, 50, {"period": 20, "std_dev": 2.0}),
        _n("logic.lt", 500, 50),
        _n("logic.gt", 500, 200),
        _n("order.buy", 700, 50, {"quantity": 75, "reason": "Price bounced off lower band"}),
        _n("order.sell", 700, 200, {"quantity": 75, "reason": "Price rejected off upper band"}),
    ],
    edges=[
        _e("n0", "close", "n3", "a"),
        _e("n2", "lower", "n3", "b"),
        _e("n0", "close", "n4", "a"),
        _e("n2", "upper", "n4", "b"),
        _e("n3", "result", "n5", "condition"),
        _e("n4", "result", "n6", "condition"),
    ],
    settings={"symbol": "NIFTY", "interval": "15m", "max_positions": 1},
    tags=["mean-reversion", "bollinger", "volatility"],
)


# ─── Template 6: SMC Order Block ───

T_SMC = _dsl(
    name="SMC Order Block Sniper",
    desc="Detects Smart Money Concepts order blocks with bullish/bearish confirmation.",
    nodes=[
        _n("source.candle", 50, 50),
        _n("source.close_history", 50, 200, {"max_length": 50}),
        _n("smc.order_block", 300, 50, {"lookback": 10}),
        _n("order.buy", 550, 50, {"quantity": 75, "reason": "Bullish order block detected"}),
        _n("order.sell", 550, 200, {"quantity": 75, "reason": "Bearish order block detected"}),
    ],
    edges=[
        _e("n2", "bullish", "n3", "condition"),
        _e("n2", "bearish", "n4", "condition"),
    ],
    settings={"symbol": "NIFTY", "interval": "15m", "max_positions": 2},
    tags=["smc", "order-block", "price-action"],
)


# ─── Template 7: MACD Cross ───

T_MACD = _dsl(
    name="MACD Crossover",
    desc="MACD line / signal line crossover strategy. BUY on bullish cross, SELL on bearish cross.",
    nodes=[
        _n("source.candle", 50, 50),
        _n("source.close_history", 50, 200, {"max_length": 100}),
        _n("indicator.macd", 300, 50, {"fast": 12, "slow": 26, "signal": 9}),
        _n("signal.cross_above", 500, 50),
        _n("signal.cross_below", 500, 200),
        _n("order.buy", 700, 50, {"quantity": 75, "reason": "MACD bullish crossover"}),
        _n("order.sell", 700, 200, {"quantity": 75, "reason": "MACD bearish crossover"}),
    ],
    edges=[
        _e("n2", "series_macd", "n3", "a"),
        _e("n2", "series_signal", "n3", "b"),
        _e("n2", "series_macd", "n4", "a"),
        _e("n2", "series_signal", "n4", "b"),
        _e("n3", "triggered", "n5", "condition"),
        _e("n4", "triggered", "n6", "condition"),
    ],
    settings={"symbol": "NIFTY", "interval": "15m", "max_positions": 1},
    tags=["trend", "macd", "crossover"],
)


# ─── Template 8: Scalping ───

T_SCALP = _dsl(
    name="Scalping with EMAs",
    desc="Fast scalping strategy using multiple EMA levels for quick entries/exits on 1-5min charts.",
    nodes=[
        _n("source.candle", 50, 50),
        _n("source.close_history", 50, 200, {"max_length": 50}),
        _n("indicator.ema", 250, 50, {"period": 5}),
        _n("indicator.ema", 250, 200, {"period": 13}),
        _n("logic.gt", 450, 50),
        _n("logic.lt", 450, 200),
        _n("order.buy", 650, 50, {"quantity": 150, "reason": "Scalp BUY signal"}),
        _n("order.sell", 650, 200, {"quantity": 150, "reason": "Scalp SELL signal"}),
        _n("order.sl", 850, 100, {"sl_type": "atr", "sl_value": 1.5}),
        _n("order.target", 850, 300, {"tp_type": "rr", "tp_value": 2}),
    ],
    edges=[
        _e("n1", "prices", "n2", "source"),
        _e("n1", "prices", "n3", "source"),
        _e("n0", "close", "n4", "a"),
        _e("n2", "value", "n4", "b"),
        _e("n0", "close", "n5", "a"),
        _e("n3", "value", "n5", "b"),
        _e("n4", "result", "n6", "condition"),
        _e("n5", "result", "n7", "condition"),
    ],
    settings={"symbol": "BANKNIFTY", "interval": "1m", "max_positions": 3, "max_daily_trades": 10},
    tags=["scalping", "ema", "fast"],
)


# ─── Template 9: ICT Silver Bullet ───

T_ICT = _dsl(
    name="ICT Silver Bullet",
    desc="ICT Silver Bullet strategy. Trades the 10-11am NY window with FVG and order block confluence.",
    nodes=[
        _n("source.candle", 50, 50),
        _n("source.close_history", 50, 200, {"max_length": 100}),
        _n("ict.silver_bullet", 300, 50),
        _n("ict.fvg", 300, 200, {"min_gap_ticks": 2}),
        _n("smc.order_block", 300, 350, {"lookback": 8}),
        _n("logic.and", 550, 50),
        _n("order.buy", 750, 50, {"quantity": 50, "reason": "ICT Silver Bullet BUY"}),
        _n("order.sell", 750, 200, {"quantity": 50, "reason": "ICT Silver Bullet SELL"}),
    ],
    edges=[
        _e("n2", "is_active", "n5", "a"),
        _e("n3", "bullish", "n5", "b"),
        _e("n4", "bullish", "n5", "c"),
        _e("n5", "result", "n6", "condition"),
    ],
    settings={"symbol": "NIFTY", "interval": "5m", "max_positions": 1},
    tags=["ict", "silver-bullet", "fvg"],
)


# ─── Template 10: Expiry Hunter ───

T_EXPIRY = _dsl(
    name="Expiry Hunter",
    desc="Sells options premium on expiry day. Short straddle/strangle when IV is high.",
    nodes=[
        _n("source.candle", 50, 50),
        _n("source.market_time", 50, 200),
        _n("greek.iv", 300, 50),
        _n("time.day_of_week", 300, 200),
        _n("time.time_range", 300, 350, {"start_hour": 10, "start_min": 0, "end_hour": 14, "end_min": 0}),
        _n("logic.and", 550, 50),
        _n("logic.gt", 550, 250, {}),
        _n("order.sell", 750, 50, {"quantity": 50, "reason": "Expiry day short strangle"}),
    ],
    edges=[
        _e("n2", "value", "n6", "a"),
        _e("n3", "is_expiry", "n5", "a"),
        _e("n4", "in_range", "n5", "b"),
        _e("n5", "result", "n7", "condition"),
        _e("n6", "result", "n7", "condition"),
    ],
    settings={"symbol": "NIFTY", "interval": "15m", "max_positions": 2},
    tags=["options", "expiry", "theta"],
)


STRATEGY_TEMPLATES: dict[str, StrategyDSL] = {
    "ema_crossover": T_EMA_CROSS,
    "opening_range_breakout": T_ORB,
    "vwap_mean_reversion": T_VWAP,
    "rsi_mean_reversion": T_RSI,
    "bollinger_bandit": T_BOLLINGER,
    "smc_order_block": T_SMC,
    "macd_cross": T_MACD,
    "scalping": T_SCALP,
    "ict_silver_bullet": T_ICT,
    "expiry_hunter": T_EXPIRY,
}
