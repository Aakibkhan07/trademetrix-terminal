from builder.models import BlockCategory, BlockDef, DataType, ParamDef, PortDef


def _p(name: str, label: str, **kw) -> ParamDef:
    return ParamDef(name=name, label=label, **kw)


def _i(name: str, label: str = "", **kw) -> PortDef:
    return PortDef(name=name, label=label or name, **kw)


def _o(name: str, type: DataType = DataType.ANY, label: str = "", **kw) -> PortDef:
    return PortDef(name=name, type=type, label=label or name, **kw)


BLOCK_DEFINITIONS: dict[str, BlockDef] = {}


def _reg(type_: str, name: str, cat: BlockCategory, desc: str = "", **kw):
    d = BlockDef(type=type_, name=name, category=cat, description=desc, **kw)
    BLOCK_DEFINITIONS[type_] = d
    return d


# ─── Input / Source Blocks ───

_reg("source.candle", "Candle", BlockCategory.INPUT,
    "Input candle data from the market",
    outputs=[_o("open", DataType.NUMBER), _o("high", DataType.NUMBER), _o("low", DataType.NUMBER),
             _o("close", DataType.NUMBER), _o("volume", DataType.NUMBER), _o("oi", DataType.NUMBER),
             _o("candle", DataType.CANDLE)])

_reg("source.tick", "Tick", BlockCategory.INPUT,
    "Input tick data from the market",
    outputs=[_o("last_price", DataType.NUMBER), _o("bid", DataType.NUMBER), _o("ask", DataType.NUMBER),
             _o("volume", DataType.NUMBER), _o("oi", DataType.NUMBER), _o("change_pct", DataType.NUMBER)])

_reg("source.close_history", "Price History", BlockCategory.INPUT,
    "Accumulated close prices as a series",
    params=[_p("max_length", "Max Length", type="number", default=500, min=10, max=10000)],
    outputs=[_o("prices", DataType.SERIES), _o("highs", DataType.SERIES), _o("lows", DataType.SERIES),
             _o("volumes", DataType.SERIES)])

_reg("source.position", "Current Position", BlockCategory.INPUT,
    "Current position data from portfolio",
    outputs=[_o("quantity", DataType.NUMBER), _o("avg_price", DataType.NUMBER), _o("pnl", DataType.NUMBER),
             _o("has_position", DataType.BOOLEAN)])

_reg("source.portfolio", "Portfolio", BlockCategory.INPUT,
    "Portfolio-level metrics",
    outputs=[_o("unrealised_pnl", DataType.NUMBER), _o("realised_pnl", DataType.NUMBER),
             _o("daily_pnl", DataType.NUMBER), _o("available_margin", DataType.NUMBER),
             _o("total_margin", DataType.NUMBER), _o("open_positions", DataType.NUMBER)])

_reg("source.market_time", "Market Time", BlockCategory.INPUT,
    "Current market time and session",
    outputs=[_o("session", DataType.STRING), _o("hour", DataType.NUMBER), _o("minute", DataType.NUMBER),
             _o("day_of_week", DataType.NUMBER), _o("is_market_open", DataType.BOOLEAN)])

# ─── Indicator Blocks ───

_reg("indicator.sma", "SMA", BlockCategory.INDICATOR,
    "Simple Moving Average",
    params=[_p("period", "Period", type="number", default=20, min=1, max=500)],
    inputs=[_i("source", "Source Series", type=DataType.SERIES)],
    outputs=[_o("value", DataType.NUMBER), _o("series", DataType.SERIES)])

_reg("indicator.ema", "EMA", BlockCategory.INDICATOR,
    "Exponential Moving Average",
    params=[_p("period", "Period", type="number", default=20, min=1, max=500)],
    inputs=[_i("source", "Source Series", type=DataType.SERIES)],
    outputs=[_o("value", DataType.NUMBER), _o("series", DataType.SERIES)])

_reg("indicator.rsi", "RSI", BlockCategory.INDICATOR,
    "Relative Strength Index",
    params=[_p("period", "Period", type="number", default=14, min=1, max=100),
            _p("oversold", "Oversold Threshold", type="number", default=30, min=1, max=100),
            _p("overbought", "Overbought Threshold", type="number", default=70, min=1, max=100)],
    inputs=[_i("source", "Source Series", type=DataType.SERIES)],
    outputs=[_o("value", DataType.NUMBER), _o("series", DataType.SERIES),
             _o("is_oversold", DataType.BOOLEAN), _o("is_overbought", DataType.BOOLEAN)])

_reg("indicator.macd", "MACD", BlockCategory.INDICATOR,
    "Moving Average Convergence Divergence",
    params=[_p("fast", "Fast Period", type="number", default=12, min=1, max=100),
            _p("slow", "Slow Period", type="number", default=26, min=1, max=200),
            _p("signal", "Signal Period", type="number", default=9, min=1, max=100)],
    inputs=[_i("source", "Source Series", type=DataType.SERIES)],
    outputs=[_o("macd_line", DataType.NUMBER), _o("signal_line", DataType.NUMBER),
             _o("histogram", DataType.NUMBER), _o("series_macd", DataType.SERIES),
             _o("series_signal", DataType.SERIES)])

_reg("indicator.bollinger", "Bollinger Bands", BlockCategory.INDICATOR,
    "Bollinger Bands with squeeze detection",
    params=[_p("period", "Period", type="number", default=20, min=1, max=200),
            _p("std_dev", "Std Deviation", type="number", default=2.0, min=0.1, max=5.0, step=0.1)],
    inputs=[_i("source", "Source Series", type=DataType.SERIES)],
    outputs=[_o("upper", DataType.NUMBER), _o("middle", DataType.NUMBER), _o("lower", DataType.NUMBER),
             _o("bandwidth", DataType.NUMBER), _o("percent_b", DataType.NUMBER),
             _o("is_squeeze", DataType.BOOLEAN)])

_reg("indicator.vwap", "VWAP", BlockCategory.INDICATOR,
    "Volume Weighted Average Price",
    params=[_p("period", "Lookback Period", type="number", default=0, min=0, max=500)],
    outputs=[_o("value", DataType.NUMBER), _o("deviation", DataType.NUMBER),
             _o("deviation_pct", DataType.NUMBER)])

_reg("indicator.atr", "ATR", BlockCategory.INDICATOR,
    "Average True Range",
    params=[_p("period", "Period", type="number", default=14, min=1, max=200)],
    inputs=[_i("high", "High Series", type=DataType.SERIES), _i("low", "Low Series", type=DataType.SERIES),
            _i("close", "Close Series", type=DataType.SERIES)],
    outputs=[_o("value", DataType.NUMBER), _o("series", DataType.SERIES)])

_reg("indicator.supertrend", "SuperTrend", BlockCategory.INDICATOR,
    "Super Trend indicator",
    params=[_p("period", "ATR Period", type="number", default=10, min=1, max=100),
            _p("multiplier", "Multiplier", type="number", default=3.0, min=0.5, max=10.0, step=0.1)],
    inputs=[_i("high", "High Series", type=DataType.SERIES), _i("low", "Low Series", type=DataType.SERIES),
            _i("close", "Close Series", type=DataType.SERIES)],
    outputs=[_o("value", DataType.NUMBER), _o("direction", DataType.NUMBER),
             _o("is_up", DataType.BOOLEAN), _o("is_down", DataType.BOOLEAN)])

_reg("indicator.stoch", "Stochastic", BlockCategory.INDICATOR,
    "Stochastic Oscillator",
    params=[_p("k_period", "%K Period", type="number", default=14, min=1, max=100),
            _p("k_smooth", "%K Smoothing", type="number", default=3, min=1, max=50),
            _p("d_period", "%D Period", type="number", default=3, min=1, max=50)],
    inputs=[_i("high", "High Series", type=DataType.SERIES), _i("low", "Low Series", type=DataType.SERIES),
            _i("close", "Close Series", type=DataType.SERIES)],
    outputs=[_o("k", DataType.NUMBER), _o("d", DataType.NUMBER)])

_reg("indicator.adx", "ADX", BlockCategory.INDICATOR,
    "Average Directional Index",
    params=[_p("period", "Period", type="number", default=14, min=1, max=100)],
    inputs=[_i("high", "High Series", type=DataType.SERIES), _i("low", "Low Series", type=DataType.SERIES),
            _i("close", "Close Series", type=DataType.SERIES)],
    outputs=[_o("adx", DataType.NUMBER), _o("plus_di", DataType.NUMBER), _o("minus_di", DataType.NUMBER)])

_reg("indicator.ichimoku", "Ichimoku Cloud", BlockCategory.INDICATOR,
    "Ichimoku Kinko Hyo",
    params=[_p("tenkan", "Tenkan Period", type="number", default=9, min=1, max=100),
            _p("kijun", "Kijun Period", type="number", default=26, min=1, max=200),
            _p("senkou", "Senkou Period", type="number", default=52, min=1, max=500)],
    inputs=[_i("high", "High Series", type=DataType.SERIES), _i("low", "Low Series", type=DataType.SERIES)],
    outputs=[_o("tenkan", DataType.NUMBER), _o("kijun", DataType.NUMBER),
             _o("senkou_a", DataType.NUMBER), _o("senkou_b", DataType.NUMBER),
             _o("chikou", DataType.NUMBER)])

_reg("indicator.psar", "Parabolic SAR", BlockCategory.INDICATOR,
    "Parabolic Stop and Reverse",
    params=[_p("start", "Start AF", type="number", default=0.02, min=0.001, max=0.5, step=0.001),
            _p("increment", "AF Increment", type="number", default=0.02, min=0.001, max=0.5, step=0.001),
            _p("maximum", "Max AF", type="number", default=0.2, min=0.01, max=1.0, step=0.01)],
    inputs=[_i("high", "High Series", type=DataType.SERIES), _i("low", "Low Series", type=DataType.SERIES)],
    outputs=[_o("value", DataType.NUMBER), _o("is_above", DataType.BOOLEAN)])

_reg("indicator.heikin_ashi", "Heikin Ashi", BlockCategory.INDICATOR,
    "Heikin Ashi candles",
    inputs=[_i("open", "Open Series", type=DataType.SERIES), _i("high", "High Series", type=DataType.SERIES),
            _i("low", "Low Series", type=DataType.SERIES), _i("close", "Close Series", type=DataType.SERIES)],
    outputs=[_o("ha_open", DataType.NUMBER), _o("ha_high", DataType.NUMBER),
             _o("ha_low", DataType.NUMBER), _o("ha_close", DataType.NUMBER)])

_reg("indicator.pivot", "Pivot Points", BlockCategory.INDICATOR,
    "Classic pivot points",
    inputs=[_i("high", "High Series", type=DataType.SERIES), _i("low", "Low Series", type=DataType.SERIES),
            _i("close", "Close Series", type=DataType.SERIES)],
    outputs=[_o("pivot", DataType.NUMBER), _o("r1", DataType.NUMBER), _o("r2", DataType.NUMBER),
             _o("r3", DataType.NUMBER), _o("s1", DataType.NUMBER), _o("s2", DataType.NUMBER),
             _o("s3", DataType.NUMBER)])

_reg("indicator.linear_reg", "Linear Regression", BlockCategory.INDICATOR,
    "Linear regression line",
    params=[_p("period", "Period", type="number", default=20, min=2, max=500)],
    inputs=[_i("source", "Source Series", type=DataType.SERIES)],
    outputs=[_o("value", DataType.NUMBER), _o("slope", DataType.NUMBER), _o("r_squared", DataType.NUMBER)])

_reg("indicator.zscore", "Z-Score", BlockCategory.INDICATOR,
    "Z-score / standard score",
    params=[_p("period", "Period", type="number", default=20, min=2, max=500)],
    inputs=[_i("source", "Source Series", type=DataType.SERIES)],
    outputs=[_o("value", DataType.NUMBER)])

_reg("indicator.kalman", "Kalman Filter", BlockCategory.INDICATOR,
    "Kalman filter smoothing",
    params=[_p("noise", "Measurement Noise", type="number", default=0.01, min=0.001, max=1.0, step=0.001)],
    inputs=[_i("source", "Source Series", type=DataType.SERIES)],
    outputs=[_o("filtered", DataType.NUMBER), _o("series", DataType.SERIES)])

# ─── Candle Pattern Blocks ───

_reg("candle.bullish", "Bullish Candle", BlockCategory.PATTERN,
    "Check if current candle is bullish",
    inputs=[_i("open", "Open", type=DataType.NUMBER), _i("close", "Close", type=DataType.NUMBER)],
    outputs=[_o("result", DataType.BOOLEAN)])

_reg("candle.bearish", "Bearish Candle", BlockCategory.PATTERN,
    "Check if current candle is bearish",
    inputs=[_i("open", "Open", type=DataType.NUMBER), _i("close", "Close", type=DataType.NUMBER)],
    outputs=[_o("result", DataType.BOOLEAN)])

_reg("candle.doji", "Doji", BlockCategory.PATTERN,
    "Doji candle pattern",
    params=[_p("body_pct", "Max Body %", type="number", default=5.0, min=0.1, max=50.0)],
    inputs=[_i("open", "Open", type=DataType.NUMBER), _i("close", "Close", type=DataType.NUMBER)],
    outputs=[_o("result", DataType.BOOLEAN)])

_reg("candle.hammer", "Hammer", BlockCategory.PATTERN,
    "Hammer / inverted hammer pattern",
    params=[_p("wick_ratio", "Min Wick Ratio", type="number", default=2.0, min=1.0, max=10.0)],
    inputs=[_i("open", "Open", type=DataType.NUMBER), _i("high", "High", type=DataType.NUMBER),
            _i("low", "Low", type=DataType.NUMBER), _i("close", "Close", type=DataType.NUMBER)],
    outputs=[_o("result", DataType.BOOLEAN)])

_reg("candle.shooting_star", "Shooting Star", BlockCategory.PATTERN,
    "Shooting star / inverted hammer",
    params=[_p("wick_ratio", "Min Wick Ratio", type="number", default=2.0, min=1.0, max=10.0)],
    inputs=[_i("open", "Open", type=DataType.NUMBER), _i("high", "High", type=DataType.NUMBER),
            _i("low", "Low", type=DataType.NUMBER), _i("close", "Close", type=DataType.NUMBER)],
    outputs=[_o("result", DataType.BOOLEAN)])

_reg("candle.engulfing", "Engulfing", BlockCategory.PATTERN,
    "Bullish / bearish engulfing pattern",
    inputs=[_i("open", "Open Series", type=DataType.SERIES), _i("close", "Close Series", type=DataType.SERIES)],
    outputs=[_o("bullish", DataType.BOOLEAN), _o("bearish", DataType.BOOLEAN)])

_reg("candle.morning_star", "Morning Star", BlockCategory.PATTERN,
    "Morning star reversal pattern",
    inputs=[_i("open", "Open Series", type=DataType.SERIES), _i("close", "Close Series", type=DataType.SERIES)],
    outputs=[_o("result", DataType.BOOLEAN)])

_reg("candle.evening_star", "Evening Star", BlockCategory.PATTERN,
    "Evening star reversal pattern",
    inputs=[_i("open", "Open Series", type=DataType.SERIES), _i("close", "Close Series", type=DataType.SERIES)],
    outputs=[_o("result", DataType.BOOLEAN)])

_reg("candle.pin_bar", "Pin Bar", BlockCategory.PATTERN,
    "Pin bar / rejection candle",
    params=[_p("wick_ratio", "Min Wick Ratio", type="number", default=2.0, min=1.0, max=10.0)],
    inputs=[_i("open", "Open", type=DataType.NUMBER), _i("high", "High", type=DataType.NUMBER),
            _i("low", "Low", type=DataType.NUMBER), _i("close", "Close", type=DataType.NUMBER)],
    outputs=[_o("result", DataType.BOOLEAN), _o("direction", DataType.STRING)])

_reg("candle.inside_bar", "Inside Bar", BlockCategory.PATTERN,
    "Inside bar (range contraction)",
    inputs=[_i("high", "High Series", type=DataType.SERIES), _i("low", "Low Series", type=DataType.SERIES)],
    outputs=[_o("result", DataType.BOOLEAN)])

_reg("candle.outside_bar", "Outside Bar", BlockCategory.PATTERN,
    "Outside bar (range expansion)",
    inputs=[_i("high", "High Series", type=DataType.SERIES), _i("low", "Low Series", type=DataType.SERIES)],
    outputs=[_o("result", DataType.BOOLEAN)])

_reg("candle.range", "Candle Range", BlockCategory.PATTERN,
    "Current candle range",
    inputs=[_i("high", "High", type=DataType.NUMBER), _i("low", "Low", type=DataType.NUMBER)],
    outputs=[_o("value", DataType.NUMBER)])

_reg("candle.body", "Candle Body", BlockCategory.PATTERN,
    "Candle body size",
    inputs=[_i("open", "Open", type=DataType.NUMBER), _i("close", "Close", type=DataType.NUMBER)],
    outputs=[_o("value", DataType.NUMBER), _o("pct", DataType.NUMBER)])

_reg("candle.wick", "Candle Wick", BlockCategory.PATTERN,
    "Upper and lower wick sizes",
    inputs=[_i("open", "Open", type=DataType.NUMBER), _i("high", "High", type=DataType.NUMBER),
            _i("low", "Low", type=DataType.NUMBER), _i("close", "Close", type=DataType.NUMBER)],
    outputs=[_o("upper", DataType.NUMBER), _o("lower", DataType.NUMBER)])

# ─── Math Blocks ───

for _op, _name, _desc in [
    ("add", "Add", "Addition: a + b"),
    ("sub", "Subtract", "Subtraction: a - b"),
    ("mul", "Multiply", "Multiplication: a * b"),
    ("div", "Divide", "Division: a / b"),
]:
    _reg(f"math.{_op}", _name, BlockCategory.MATH, _desc,
         inputs=[_i("a", "Input A", type=DataType.NUMBER), _i("b", "Input B", type=DataType.NUMBER)],
         outputs=[_o("result", DataType.NUMBER)])

_reg("math.min", "Min", BlockCategory.MATH,
    "Minimum of two values",
    inputs=[_i("a", "Input A", type=DataType.NUMBER), _i("b", "Input B", type=DataType.NUMBER)],
    outputs=[_o("result", DataType.NUMBER)])

_reg("math.max", "Max", BlockCategory.MATH,
    "Maximum of two values",
    inputs=[_i("a", "Input A", type=DataType.NUMBER), _i("b", "Input B", type=DataType.NUMBER)],
    outputs=[_o("result", DataType.NUMBER)])

_reg("math.avg", "Average", BlockCategory.MATH,
    "Average of two values",
    inputs=[_i("a", "Input A", type=DataType.NUMBER), _i("b", "Input B", type=DataType.NUMBER)],
    outputs=[_o("result", DataType.NUMBER)])

_reg("math.abs", "Absolute", BlockCategory.MATH,
    "Absolute value",
    inputs=[_i("value", "Value", type=DataType.NUMBER)],
    outputs=[_o("result", DataType.NUMBER)])

_reg("math.round", "Round", BlockCategory.MATH,
    "Round to decimal places",
    params=[_p("decimals", "Decimals", type="number", default=2, min=0, max=10)],
    inputs=[_i("value", "Value", type=DataType.NUMBER)],
    outputs=[_o("result", DataType.NUMBER)])

_reg("math.sqrt", "Square Root", BlockCategory.MATH,
    "Square root",
    inputs=[_i("value", "Value", type=DataType.NUMBER)],
    outputs=[_o("result", DataType.NUMBER)])

_reg("math.pct_change", "Percent Change", BlockCategory.MATH,
    "Percentage change between values",
    inputs=[_i("current", "Current", type=DataType.NUMBER), _i("previous", "Previous", type=DataType.NUMBER)],
    outputs=[_o("result", DataType.NUMBER)])

_reg("math.scale", "Scale / Normalize", BlockCategory.MATH,
    "Scale value from one range to another",
    params=[_p("in_min", "Input Min", type="number", default=0),
            _p("in_max", "Input Max", type="number", default=100),
            _p("out_min", "Output Min", type="number", default=0),
            _p("out_max", "Output Max", type="number", default=1)],
    inputs=[_i("value", "Value", type=DataType.NUMBER)],
    outputs=[_o("result", DataType.NUMBER)])

_reg("math.sum", "Sum Series", BlockCategory.MATH,
    "Sum of series values",
    inputs=[_i("series", "Series", type=DataType.SERIES)],
    outputs=[_o("result", DataType.NUMBER)])

_reg("math.highest", "Highest", BlockCategory.MATH,
    "Highest value in series over period",
    params=[_p("period", "Period", type="number", default=20, min=1, max=500)],
    inputs=[_i("source", "Source Series", type=DataType.SERIES)],
    outputs=[_o("value", DataType.NUMBER)])

_reg("math.lowest", "Lowest", BlockCategory.MATH,
    "Lowest value in series over period",
    params=[_p("period", "Period", type="number", default=20, min=1, max=500)],
    inputs=[_i("source", "Source Series", type=DataType.SERIES)],
    outputs=[_o("value", DataType.NUMBER)])

_reg("math.sign", "Sign", BlockCategory.MATH,
    "Sign of value (-1, 0, 1)",
    inputs=[_i("value", "Value", type=DataType.NUMBER)],
    outputs=[_o("result", DataType.NUMBER)])

_reg("math.pow", "Power", BlockCategory.MATH,
    "Power / exponentiation",
    inputs=[_i("base", "Base", type=DataType.NUMBER), _i("exponent", "Exponent", type=DataType.NUMBER)],
    outputs=[_o("result", DataType.NUMBER)])

_reg("math.log", "Logarithm", BlockCategory.MATH,
    "Natural logarithm",
    inputs=[_i("value", "Value", type=DataType.NUMBER)],
    outputs=[_o("result", DataType.NUMBER)])

_reg("math.mod", "Modulo", BlockCategory.MATH,
    "Modulo / remainder",
    inputs=[_i("a", "Dividend", type=DataType.NUMBER), _i("b", "Divisor", type=DataType.NUMBER)],
    outputs=[_o("result", DataType.NUMBER)])

_reg("math.clamp", "Clamp", BlockCategory.MATH,
    "Clamp value between min and max",
    inputs=[_i("value", "Value", type=DataType.NUMBER), _i("min", "Min", type=DataType.NUMBER),
            _i("max", "Max", type=DataType.NUMBER)],
    outputs=[_o("result", DataType.NUMBER)])

# ─── Logic Blocks ───

for _op, _name, _desc in [
    ("and", "AND", "Logical AND"),
    ("or", "OR", "Logical OR"),
]:
    _reg(f"logic.{_op}", _name, BlockCategory.LOGIC, _desc,
         inputs=[_i("a", "Input A", type=DataType.BOOLEAN), _i("b", "Input B", type=DataType.BOOLEAN)],
         outputs=[_o("result", DataType.BOOLEAN)])

_reg("logic.not", "NOT", BlockCategory.LOGIC,
    "Logical NOT",
    inputs=[_i("value", "Value", type=DataType.BOOLEAN)],
    outputs=[_o("result", DataType.BOOLEAN)])

for _op, _name, _desc in [
    ("gt", "Greater Than", "a > b"),
    ("lt", "Less Than", "a < b"),
    ("gte", "Greater or Equal", "a >= b"),
    ("lte", "Less or Equal", "a <= b"),
    ("eq", "Equal", "a == b"),
    ("neq", "Not Equal", "a != b"),
]:
    _reg(f"logic.{_op}", _name, BlockCategory.LOGIC, _desc,
         inputs=[_i("a", "Input A", type=DataType.NUMBER), _i("b", "Input B", type=DataType.NUMBER)],
         outputs=[_o("result", DataType.BOOLEAN)])

_reg("logic.if_else", "If/Else", BlockCategory.LOGIC,
    "Conditional: if condition then a else b",
    inputs=[_i("condition", "Condition", type=DataType.BOOLEAN),
            _i("then", "Then Value", type=DataType.ANY),
            _i("else", "Else Value", type=DataType.ANY)],
    outputs=[_o("result", DataType.ANY)])

_reg("logic.switch", "Switch / Multi-Condition", BlockCategory.LOGIC,
    "Evaluate multiple conditions in order",
    params=[_p("condition_count", "Number of Conditions", type="number", default=3, min=1, max=10)],
    outputs=[_o("result", DataType.ANY)])

# ─── SMC Blocks ───

_reg("smc.order_block", "Order Block", BlockCategory.SMC,
    "Detect bullish/bearish order blocks",
    params=[_p("lookback", "Lookback", type="number", default=10, min=3, max=100),
            _p("min_body_ratio", "Min Body Ratio", type="number", default=0.3, min=0.1, max=1.0, step=0.1)],
    inputs=[_i("open", "Open Series", type=DataType.SERIES), _i("high", "High Series", type=DataType.SERIES),
            _i("low", "Low Series", type=DataType.SERIES), _i("close", "Close Series", type=DataType.SERIES)],
    outputs=[_o("bullish", DataType.BOOLEAN), _o("bearish", DataType.BOOLEAN),
             _o("level", DataType.NUMBER)])

_reg("smc.liquidity_grab", "Liquidity Grab", BlockCategory.SMC,
    "Detect liquidity grabs above highs / below lows",
    params=[_p("lookback", "Lookback", type="number", default=6, min=3, max=100)],
    inputs=[_i("high", "High Series", type=DataType.SERIES), _i("low", "Low Series", type=DataType.SERIES),
            _i("close", "Close Series", type=DataType.SERIES)],
    outputs=[_o("bullish", DataType.BOOLEAN), _o("bearish", DataType.BOOLEAN),
             _o("grab_level", DataType.NUMBER)])

_reg("smc.fvg", "Fair Value Gap", BlockCategory.SMC,
    "Detect fair value gaps (FVG)",
    params=[_p("min_gap_pct", "Min Gap %", type="number", default=0.05, min=0.01, max=5.0, step=0.01)],
    inputs=[_i("high", "High Series", type=DataType.SERIES), _i("low", "Low Series", type=DataType.SERIES)],
    outputs=[_o("bullish", DataType.BOOLEAN), _o("bearish", DataType.BOOLEAN),
             _o("gap_high", DataType.NUMBER), _o("gap_low", DataType.NUMBER)])

_reg("smc.breaker", "Breaker Block", BlockCategory.SMC,
    "Detect breaker blocks",
    params=[_p("lookback", "Lookback", type="number", default=10, min=3, max=100)],
    inputs=[_i("high", "High Series", type=DataType.SERIES), _i("low", "Low Series", type=DataType.SERIES),
            _i("close", "Close Series", type=DataType.SERIES)],
    outputs=[_o("bullish", DataType.BOOLEAN), _o("bearish", DataType.BOOLEAN)])

_reg("smc.mss", "Market Structure Shift", BlockCategory.SMC,
    "Detect market structure shift (MSS / CHoCH)",
    params=[_p("lookback", "Lookback", type="number", default=5, min=2, max=100)],
    inputs=[_i("high", "High Series", type=DataType.SERIES), _i("low", "Low Series", type=DataType.SERIES)],
    outputs=[_o("bullish", DataType.BOOLEAN), _o("bearish", DataType.BOOLEAN)])

_reg("smc.bos", "Break of Structure", BlockCategory.SMC,
    "Detect break of structure (BOS)",
    params=[_p("lookback", "Lookback", type="number", default=5, min=2, max=100)],
    inputs=[_i("high", "High Series", type=DataType.SERIES), _i("low", "Low Series", type=DataType.SERIES)],
    outputs=[_o("bullish", DataType.BOOLEAN), _o("bearish", DataType.BOOLEAN)])

_reg("smc.discount", "Discount / Premium", BlockCategory.SMC,
    "Calculate if price is in discount or premium zone",
    inputs=[_i("high", "Range High", type=DataType.NUMBER), _i("low", "Range Low", type=DataType.NUMBER),
            _i("price", "Current Price", type=DataType.NUMBER)],
    outputs=[_o("is_discount", DataType.BOOLEAN), _o("is_premium", DataType.BOOLEAN),
             _o("position_pct", DataType.NUMBER)])

# ─── ICT Blocks ───

_reg("ict.fvg", "ICT Fair Value Gap", BlockCategory.ICT,
    "ICT Fair Value Gap detection with mitigation",
    params=[_p("min_gap_ticks", "Min Gap Ticks", type="number", default=2, min=1, max=100)],
    inputs=[_i("high", "High Series", type=DataType.SERIES), _i("low", "Low Series", type=DataType.SERIES)],
    outputs=[_o("bullish", DataType.BOOLEAN), _o("bearish", DataType.BOOLEAN),
             _o("mitigated", DataType.BOOLEAN)])

_reg("ict.ob", "ICT Order Block", BlockCategory.ICT,
    "ICT Order Block with premium/discount",
    params=[_p("lookback", "Lookback", type="number", default=10, min=3, max=100)],
    inputs=[_i("open", "Open Series", type=DataType.SERIES), _i("high", "High Series", type=DataType.SERIES),
            _i("low", "Low Series", type=DataType.SERIES), _i("close", "Close Series", type=DataType.SERIES)],
    outputs=[_o("bullish", DataType.BOOLEAN), _o("bearish", DataType.BOOLEAN),
             _o("level", DataType.NUMBER)])

_reg("ict.liquidity", "ICT Liquidity", BlockCategory.ICT,
    "ICT liquidity sweep detection",
    params=[_p("lookback", "Lookback", type="number", default=10, min=3, max=100)],
    inputs=[_i("high", "High Series", type=DataType.SERIES), _i("low", "Low Series", type=DataType.SERIES)],
    outputs=[_o("buy_sweep", DataType.BOOLEAN), _o("sell_sweep", DataType.BOOLEAN),
             _o("sweep_level", DataType.NUMBER)])

_reg("ict.killzone", "ICT Killzone", BlockCategory.ICT,
    "ICT killzone time windows",
    outputs=[_o("asian", DataType.BOOLEAN), _o("london_open", DataType.BOOLEAN),
             _o("ny_open", DataType.BOOLEAN), _o("london_close", DataType.BOOLEAN),
             _o("active_killzone", DataType.STRING)])

_reg("ict.silver_bullet", "Silver Bullet", BlockCategory.ICT,
    "ICT Silver Bullet window (10am-11am NY)",
    outputs=[_o("is_active", DataType.BOOLEAN), _o("minutes_left", DataType.NUMBER)])

_reg("ict.ote", "Optimal Trade Entry", BlockCategory.ICT,
    "ICT Optimal Trade Entry (OTE) zone (0.5-0.618 retracement)",
    inputs=[_i("high", "Swing High", type=DataType.NUMBER), _i("low", "Swing Low", type=DataType.NUMBER),
            _i("price", "Current Price", type=DataType.NUMBER)],
    outputs=[_o("in_ote", DataType.BOOLEAN), _o("retracement_pct", DataType.NUMBER)])

# ─── Greek Blocks ───

_reg("greek.delta", "Option Delta", BlockCategory.GREEK,
    "Option delta (for options strategies)",
    params=[_p("strike", "Strike Price", type="number"),
            _p("spot", "Spot Price", type="number"),
            _p("time_to_expiry", "Days to Expiry", type="number", default=7),
            _p("iv", "Implied Volatility %", type="number", default=20),
            _p("option_type", "Option Type", type="select", default="CE", options=["CE", "PE"])],
    outputs=[_o("value", DataType.NUMBER)])

_reg("greek.gamma", "Option Gamma", BlockCategory.GREEK,
    "Option gamma",
    params=[_p("strike", "Strike Price", type="number"),
            _p("spot", "Spot Price", type="number"),
            _p("time_to_expiry", "Days to Expiry", type="number", default=7),
            _p("iv", "Implied Volatility %", type="number", default=20),
            _p("option_type", "Option Type", type="select", default="CE", options=["CE", "PE"])],
    outputs=[_o("value", DataType.NUMBER)])

_reg("greek.theta", "Option Theta", BlockCategory.GREEK,
    "Option theta (time decay)",
    params=[_p("strike", "Strike Price", type="number"),
            _p("spot", "Spot Price", type="number"),
            _p("time_to_expiry", "Days to Expiry", type="number", default=7),
            _p("iv", "Implied Volatility %", type="number", default=20),
            _p("option_type", "Option Type", type="select", default="CE", options=["CE", "PE"])],
    outputs=[_o("value", DataType.NUMBER)])

_reg("greek.vega", "Option Vega", BlockCategory.GREEK,
    "Option vega (volatility sensitivity)",
    params=[_p("strike", "Strike Price", type="number"),
            _p("spot", "Spot Price", type="number"),
            _p("time_to_expiry", "Days to Expiry", type="number", default=7),
            _p("iv", "Implied Volatility %", type="number", default=20),
            _p("option_type", "Option Type", type="select", default="CE", options=["CE", "PE"])],
    outputs=[_o("value", DataType.NUMBER)])

_reg("greek.iv", "Implied Volatility", BlockCategory.GREEK,
    "Estimate implied volatility from candle range",
    inputs=[_i("high", "High", type=DataType.NUMBER), _i("low", "Low", type=DataType.NUMBER),
            _i("close", "Close", type=DataType.NUMBER)],
    outputs=[_o("value", DataType.NUMBER)])

_reg("greek.premium", "Option Premium", BlockCategory.GREEK,
    "Option premium calculation",
    params=[_p("option_type", "Option Type", type="select", default="CE", options=["CE", "PE"])],
    inputs=[_i("intrinsic", "Intrinsic Value", type=DataType.NUMBER),
            _i("time_value", "Time Value", type=DataType.NUMBER)],
    outputs=[_o("value", DataType.NUMBER)])

# ─── OI Blocks ───

_reg("oi.change", "OI Change", BlockCategory.OI,
    "Change in open interest",
    inputs=[_i("current_oi", "Current OI", type=DataType.NUMBER),
            _i("prev_oi", "Previous OI", type=DataType.NUMBER)],
    outputs=[_o("change", DataType.NUMBER), _o("pct_change", DataType.NUMBER),
             _o("increasing", DataType.BOOLEAN), _o("decreasing", DataType.BOOLEAN)])

_reg("oi.trend", "OI Trend", BlockCategory.OI,
    "Open interest trend direction",
    params=[_p("lookback", "Lookback", type="number", default=5, min=2, max=100)],
    inputs=[_i("oi_series", "OI Series", type=DataType.SERIES)],
    outputs=[_o("trend", DataType.STRING), _o("strength", DataType.NUMBER)])

_reg("oi.pcr", "Put-Call Ratio", BlockCategory.OI,
    "Put-Call ratio from OI data",
    inputs=[_i("pe_oi", "PE OI", type=DataType.NUMBER), _i("ce_oi", "CE OI", type=DataType.NUMBER)],
    outputs=[_o("value", DataType.NUMBER), _o("is_bearish", DataType.BOOLEAN),
             _o("is_bullish", DataType.BOOLEAN)])

_reg("oi.coi", "Change in OI", BlockCategory.OI,
    "Change in OI with price action correlation",
    inputs=[_i("oi_change", "OI Change", type=DataType.NUMBER),
            _i("price_change", "Price Change", type=DataType.NUMBER)],
    outputs=[_o("accumulation", DataType.BOOLEAN), _o("distribution", DataType.BOOLEAN)])

# ─── Signal Blocks ───

_reg("signal.cross_above", "Cross Above", BlockCategory.SIGNAL,
    "Detect when series A crosses above series B",
    inputs=[_i("a", "Series A", type=DataType.SERIES), _i("b", "Series B", type=DataType.SERIES)],
    outputs=[_o("triggered", DataType.BOOLEAN), _o("crossover_value", DataType.NUMBER)])

_reg("signal.cross_below", "Cross Below", BlockCategory.SIGNAL,
    "Detect when series A crosses below series B",
    inputs=[_i("a", "Series A", type=DataType.SERIES), _i("b", "Series B", type=DataType.SERIES)],
    outputs=[_o("triggered", DataType.BOOLEAN), _o("crossunder_value", DataType.NUMBER)])

_reg("signal.threshold", "Threshold", BlockCategory.SIGNAL,
    "Detect when value crosses threshold",
    params=[_p("direction", "Direction", type="select", default="above", options=["above", "below", "either"])],
    inputs=[_i("value", "Value", type=DataType.NUMBER), _i("threshold", "Threshold", type=DataType.NUMBER)],
    outputs=[_o("triggered", DataType.BOOLEAN)])

_reg("signal.breakout", "Breakout", BlockCategory.SIGNAL,
    "Detect price breakout above resistance or below support",
    params=[_p("lookback", "Lookback", type="number", default=20, min=1, max=500),
            _p("buffer_pct", "Buffer %", type="number", default=0.1, min=0.01, max=5.0)],
    inputs=[_i("high", "High Series", type=DataType.SERIES), _i("low", "Low Series", type=DataType.SERIES),
            _i("close", "Close", type=DataType.NUMBER)],
    outputs=[_o("breakout", DataType.BOOLEAN), _o("breakdown", DataType.BOOLEAN),
             _o("level", DataType.NUMBER)])

_reg("signal.divergence", "Divergence", BlockCategory.SIGNAL,
    "Detect bullish/bearish divergence between price and indicator",
    params=[_p("lookback", "Lookback", type="number", default=10, min=2, max=200)],
    inputs=[_i("price", "Price Series", type=DataType.SERIES),
            _i("indicator", "Indicator Series", type=DataType.SERIES)],
    outputs=[_o("bullish", DataType.BOOLEAN), _o("bearish", DataType.BOOLEAN),
             _o("strength", DataType.NUMBER)])

_reg("signal.confirmation", "Multi-Confirmation", BlockCategory.SIGNAL,
    "Require multiple confirmations before triggering",
    params=[_p("min_confirmations", "Min Confirmations", type="number", default=2, min=1, max=10)],
    outputs=[_o("confirmed", DataType.BOOLEAN), _o("count", DataType.NUMBER)])

# ─── Order Blocks ───

_reg("order.buy", "BUY Signal", BlockCategory.ORDER,
    "Generate a BUY order signal",
    params=[_p("quantity", "Quantity", type="number", default=0, min=0),
            _p("order_type", "Order Type", type="select", default="MARKET", options=["MARKET", "LIMIT"]),
            _p("product", "Product", type="select", default="INTRADAY", options=["INTRADAY", "MIS", "NRML"]),
            _p("reason", "Reason", type="string", default="Strategy signal")],
    outputs=[_o("signal", DataType.SIGNAL)])

_reg("order.sell", "SELL Signal", BlockCategory.ORDER,
    "Generate a SELL order signal",
    params=[_p("quantity", "Quantity", type="number", default=0, min=0),
            _p("order_type", "Order Type", type="select", default="MARKET", options=["MARKET", "LIMIT"]),
            _p("product", "Product", type="select", default="INTRADAY", options=["INTRADAY", "MIS", "NRML"]),
            _p("reason", "Reason", type="string", default="Strategy signal")],
    outputs=[_o("signal", DataType.SIGNAL)])

_reg("order.exit", "EXIT Signal", BlockCategory.ORDER,
    "Exit current position",
    params=[_p("reason", "Reason", type="string", default="Exit signal")],
    outputs=[_o("signal", DataType.SIGNAL)])

_reg("order.reverse", "REVERSE Signal", BlockCategory.ORDER,
    "Reverse current position",
    params=[_p("reason", "Reason", type="string", default="Reversal signal")],
    outputs=[_o("signal", DataType.SIGNAL)])

_reg("order.sl", "Stop Loss", BlockCategory.ORDER,
    "Set stop loss for position",
    params=[_p("sl_type", "SL Type", type="select", default="fixed", options=["fixed", "atr", "percent"]),
            _p("sl_value", "SL Value", type="number", default=0, min=0),
            _p("sl_pct", "SL %", type="number", default=1.0, min=0.1, max=50.0)],
    inputs=[_i("entry_price", "Entry Price", type=DataType.NUMBER),
            _i("atr", "ATR (for ATR-based)", type=DataType.NUMBER, required=False)],
    outputs=[_o("sl_price", DataType.NUMBER)])

_reg("order.target", "Take Profit", BlockCategory.ORDER,
    "Set take profit target",
    params=[_p("tp_type", "TP Type", type="select", default="fixed", options=["fixed", "atr", "percent", "rr"]),
            _p("tp_value", "TP Value (or R:R ratio)", type="number", default=0, min=0),
            _p("tp_pct", "TP %", type="number", default=2.0, min=0.1, max=100.0)],
    inputs=[_i("entry_price", "Entry Price", type=DataType.NUMBER),
            _i("atr", "ATR (for ATR-based)", type=DataType.NUMBER, required=False)],
    outputs=[_o("tp_price", DataType.NUMBER)])

_reg("order.trailing_sl", "Trailing Stop Loss", BlockCategory.ORDER,
    "Trailing stop loss that follows price",
    params=[_p("trail_type", "Trail Type", type="select", default="percent", options=["percent", "atr", "points"]),
            _p("trail_value", "Trail Value", type="number", default=1.0, min=0.01),
            _p("activation_pct", "Activation %", type="number", default=0.5, min=0.0, max=100.0)],
    inputs=[_i("current_price", "Current Price", type=DataType.NUMBER),
            _i("entry_price", "Entry Price", type=DataType.NUMBER),
            _i("atr", "ATR (for ATR-based)", type=DataType.NUMBER, required=False)],
    outputs=[_o("sl_price", DataType.NUMBER)])

# ─── Portfolio / Risk Blocks ───

_reg("portfolio.position_size", "Position Size", BlockCategory.PORTFOLIO,
    "Calculate position size based on risk",
    params=[_p("method", "Method", type="select", default="fixed",
               options=["fixed", "percent_equity", "risk_based", "kelly"]),
            _p("value", "Value", type="number", default=1),
            _p("max_risk_pct", "Max Risk %", type="number", default=1.0, min=0.1, max=100.0)],
    inputs=[_i("equity", "Equity", type=DataType.NUMBER),
            _i("entry_price", "Entry Price", type=DataType.NUMBER, required=False),
            _i("sl_price", "Stop Loss", type=DataType.NUMBER, required=False)],
    outputs=[_o("quantity", DataType.NUMBER)])

_reg("portfolio.open_positions", "Open Positions", BlockCategory.PORTFOLIO,
    "Count and details of open positions",
    outputs=[_o("count", DataType.NUMBER), _o("has_position", DataType.BOOLEAN)])

_reg("portfolio.position_pnl", "Position PnL", BlockCategory.PORTFOLIO,
    "Current PnL of open positions",
    outputs=[_o("realised", DataType.NUMBER), _o("unrealised", DataType.NUMBER),
             _o("total", DataType.NUMBER)])

_reg("portfolio.daily_pnl", "Daily PnL", BlockCategory.PORTFOLIO,
    "Today's profit and loss",
    outputs=[_o("value", DataType.NUMBER)])

_reg("risk.drawdown", "Drawdown Check", BlockCategory.RISK,
    "Check current drawdown against limit",
    params=[_p("max_drawdown_pct", "Max Drawdown %", type="number", default=10.0, min=0.1, max=100.0)],
    outputs=[_o("exceeded", DataType.BOOLEAN), _o("current_dd_pct", DataType.NUMBER)])

_reg("risk.max_loss", "Max Loss Check", BlockCategory.RISK,
    "Check daily loss against limit",
    params=[_p("max_daily_loss", "Max Daily Loss", type="number", default=5000, min=0)],
    outputs=[_o("exceeded", DataType.BOOLEAN), _o("current_loss", DataType.NUMBER)])

_reg("risk.max_trades", "Max Trades Check", BlockCategory.RISK,
    "Check daily trade count against limit",
    params=[_p("max_trades", "Max Trades per Day", type="number", default=5, min=1, max=100)],
    outputs=[_o("exceeded", DataType.BOOLEAN), _o("trade_count", DataType.NUMBER)])

# ─── Time Blocks ───

_reg("time.market_hour", "Market Hour", BlockCategory.TIME,
    "Current market hour (1-24)",
    outputs=[_o("hour", DataType.NUMBER), _o("minute", DataType.NUMBER)])

_reg("time.market_session", "Market Session", BlockCategory.TIME,
    "Current market session",
    outputs=[_o("session", DataType.STRING)])

_reg("time.day_of_week", "Day of Week", BlockCategory.TIME,
    "Current day of week (0=Mon, 6=Sun)",
    outputs=[_o("day", DataType.NUMBER), _o("is_monday", DataType.BOOLEAN),
             _o("is_friday", DataType.BOOLEAN), _o("is_expiry", DataType.BOOLEAN)])

_reg("time.time_range", "Time Range", BlockCategory.TIME,
    "Check if current time is within range",
    params=[_p("start_hour", "Start Hour", type="number", default=9, min=0, max=23),
            _p("start_min", "Start Minute", type="number", default=15, min=0, max=59),
            _p("end_hour", "End Hour", type="number", default=15, min=0, max=23),
            _p("end_min", "End Minute", type="number", default=30, min=0, max=59)],
    outputs=[_o("in_range", DataType.BOOLEAN)])

_reg("time.bar_index", "Bar Index", BlockCategory.TIME,
    "Current bar index since strategy start",
    outputs=[_o("index", DataType.NUMBER)])

_reg("time.bars_since", "Bars Since", BlockCategory.TIME,
    "Bars since last event",
    inputs=[_i("event", "Event Trigger", type=DataType.BOOLEAN)],
    outputs=[_o("count", DataType.NUMBER)])

_reg("time.expiry", "Days to Expiry", BlockCategory.TIME,
    "Days until next weekly/monthly expiry",
    outputs=[_o("days", DataType.NUMBER), _o("is_expiry_week", DataType.BOOLEAN)])

# ─── Variable / Constant Blocks ───

_reg("constant.number", "Number", BlockCategory.VARIABLE,
    "Numeric constant",
    params=[_p("value", "Value", type="number", default=0)],
    outputs=[_o("value", DataType.NUMBER)])

_reg("constant.string", "String", BlockCategory.VARIABLE,
    "String constant",
    params=[_p("value", "Value", type="string", default="")],
    outputs=[_o("value", DataType.STRING)])

_reg("constant.boolean", "Boolean", BlockCategory.VARIABLE,
    "Boolean constant",
    params=[_p("value", "Value", type="select", default="true", options=["true", "false"])],
    outputs=[_o("value", DataType.BOOLEAN)])

_reg("variable.set", "Set Variable", BlockCategory.VARIABLE,
    "Store a value in a named variable",
    params=[_p("name", "Variable Name", type="string", default="var1")],
    inputs=[_i("value", "Value", type=DataType.ANY)],
    outputs=[_o("stored", DataType.ANY)])

_reg("variable.get", "Get Variable", BlockCategory.VARIABLE,
    "Retrieve a named variable",
    params=[_p("name", "Variable Name", type="string", default="var1")],
    outputs=[_o("value", DataType.ANY)])

_reg("variable.list", "List / Array", BlockCategory.VARIABLE,
    "Create a list of values",
    params=[_p("item_count", "Item Count", type="number", default=3, min=1, max=20)],
    outputs=[_o("list", DataType.ANY)])

# ─── Group / Container ───

_reg("group.nested", "Nested Group", BlockCategory.GROUP,
    "Nested group of blocks for modular strategy design",
    params=[_p("name", "Group Name", type="string", default="Sub-strategy")],
    outputs=[_o("result", DataType.ANY)])


def get_block(block_type: str) -> BlockDef | None:
    return BLOCK_DEFINITIONS.get(block_type)


def list_blocks(category: BlockCategory | None = None) -> list[BlockDef]:
    if category:
        return [b for b in BLOCK_DEFINITIONS.values() if b.category == category]
    return list(BLOCK_DEFINITIONS.values())


def list_categories() -> list[dict]:
    seen = set()
    cats = []
    for b in BLOCK_DEFINITIONS.values():
        if b.category not in seen:
            seen.add(b.category)
            cats.append({"key": b.category.value, "name": b.category.name.title(), "count": sum(1 for x in BLOCK_DEFINITIONS.values() if x.category == b.category)})
    return cats
