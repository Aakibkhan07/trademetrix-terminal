"""Lightweight technical indicators for strategy calculations."""


def ema(values: list[float], period: int) -> float:
    if len(values) < period:
        return values[-1] if values else 0.0
    multiplier = 2.0 / (period + 1)
    result = sum(values[:period]) / period
    for v in values[period:]:
        result = (v - result) * multiplier + result
    return result


def sma(values: list[float], period: int) -> float:
    if len(values) < period or period < 1:
        return values[-1] if values else 0.0
    return sum(values[-period:]) / period


def vwap(bars: list[tuple[float, float]]) -> float:
    pv = sum(p * v for p, v in bars)
    vol = sum(v for _, v in bars)
    return pv / vol if vol else 0.0


def atr(candles: list, period: int = 14) -> float:
    if len(candles) < period + 1:
        return 0.0
    trs = []
    for i in range(1, len(candles)):
        high = candles[i].high if hasattr(candles[i], "high") else candles[i][2]
        low = candles[i].low if hasattr(candles[i], "low") else candles[i][3]
        prev_close = candles[i - 1].close if hasattr(candles[i - 1], "close") else candles[i - 1][4]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    if not trs:
        return 0.0
    return sma(trs, min(period, len(trs)))


def adx(candles: list, period: int = 14) -> float:
    if len(candles) < period + 1:
        return 0.0
    plus_dms = []
    minus_dms = []
    trs = []
    for i in range(1, len(candles)):
        high = candles[i].high if hasattr(candles[i], "high") else candles[i][2]
        low = candles[i].low if hasattr(candles[i], "low") else candles[i][3]
        prev_high = candles[i - 1].high if hasattr(candles[i - 1], "high") else candles[i - 1][2]
        prev_low = candles[i - 1].low if hasattr(candles[i - 1], "low") else candles[i - 1][3]
        prev_close = candles[i - 1].close if hasattr(candles[i - 1], "close") else candles[i - 1][4]

        up_move = high - prev_high
        down_move = prev_low - low
        plus_dm = up_move if up_move > down_move and up_move > 0 else 0.0
        minus_dm = down_move if down_move > up_move and down_move > 0 else 0.0
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        plus_dms.append(plus_dm)
        minus_dms.append(minus_dm)
        trs.append(tr)

    if len(trs) < period:
        return 0.0
    avg_tr = sum(trs[-period:]) / period
    if avg_tr <= 0:
        return 0.0
    avg_plus = sum(plus_dms[-period:]) / period
    avg_minus = sum(minus_dms[-period:]) / period
    plus_di = 100 * avg_plus / avg_tr
    minus_di = 100 * avg_minus / avg_tr
    dx = abs(plus_di - minus_di) / (plus_di + minus_di) * 100 if (plus_di + minus_di) > 0 else 0
    return dx


def supertrend(candles: list, period: int = 10, multiplier: float = 3.0) -> tuple[float, bool]:
    if len(candles) < period + 1:
        return 0.0, True
    atr_val = atr(candles, period)
    if atr_val <= 0:
        return 0.0, True
    close = candles[-1].close if hasattr(candles[-1], "close") else candles[-1][4]
    hl2 = (candles[-1].high + candles[-1].low) / 2 if hasattr(candles[-1], "high") else (candles[-1][2] + candles[-1][3]) / 2
    upper = hl2 + multiplier * atr_val
    lower = hl2 - multiplier * atr_val
    prev_close = candles[-2].close if hasattr(candles[-2], "close") else candles[-2][4]
    return upper, close > prev_close
