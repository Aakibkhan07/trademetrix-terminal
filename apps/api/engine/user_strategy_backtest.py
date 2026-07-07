"""Backtest engine for user-created visual strategies.

Honest computation: ALL results carry a data_source field ("real" | "simulated").
Real underlying data requires Fyers broker credentials. Option premiums are
estimated using Black-Scholes with historical volatility from real candle data.
"""

import math
import logging
import re
from datetime import UTC, datetime, timedelta

from core.models import (
    ExecutionPlan, OptionType, OrderSide, UserStrategy, UserStrategyLeg,
    UserStrategyStatus,
)
from engine.strategy_compiler import (
    LOT_SIZES, STRIKE_INTERVALS, WEEKDAY_EXPIRY,
    compile_user_strategy, resolve_expiry,
)
from market.historical import historical_engine

logger = logging.getLogger(__name__)

BACKTEST_INTERVAL = "15m"
BACKTEST_MAX_DAYS = 365

def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

def _black_scholes_price(
    S: float, K: float, T: float, r: float, sigma: float, option_type: OptionType
) -> float:
    if T <= 0:
        intrinsic = max(0, S - K) if option_type == OptionType.CE else max(0, K - S)
        return intrinsic
    if sigma <= 0.001:
        return max(0, S - K) if option_type == OptionType.CE else max(0, K - S)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if option_type == OptionType.CE:
        return S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
    else:
        return K * math.exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1)

def _estimate_historical_volatility(close_prices: list[float], window: int = 21) -> float:
    if len(close_prices) < window + 1:
        return 0.25
    log_returns = []
    for i in range(1, len(close_prices)):
        if close_prices[i - 1] > 0:
            log_returns.append(math.log(close_prices[i] / close_prices[i - 1]))
    if len(log_returns) < 2:
        return 0.25
    mean = sum(log_returns) / len(log_returns)
    variance = sum((r - mean) ** 2 for r in log_returns) / (len(log_returns) - 1)
    daily_vol = math.sqrt(variance)
    return min(daily_vol * math.sqrt(252), 1.0)

def _estimate_option_premium(
    S: float, K: float, option_type: OptionType,
    days_to_expiry: int, total_dte: int,
    close_prices: list[float] | None = None,
) -> float:
    r = 0.065
    T = max(days_to_expiry, 0) / 365.0
    sigma = _estimate_historical_volatility(close_prices or [S]) if close_prices else 0.25
    if T <= 0.005:
        intrinsic = max(0, S - K) if option_type == OptionType.CE else max(0, K - S)
        return round(intrinsic, 2)
    premium = _black_scholes_price(S, K, T, r, sigma, option_type)
    return round(max(premium, 0.5), 2)

def _parse_strike_from_symbol(symbol: str) -> tuple[float, OptionType] | None:
    m = re.search(r"(\d+(?:\.\d+)?)(CE|PE)$", symbol)
    if not m:
        return None
    strike = float(m.group(1))
    opt_type = OptionType.CE if m.group(2) == "CE" else OptionType.PE
    return strike, opt_type

def _parse_expiry_from_symbol(symbol: str) -> str | None:
    m = re.search(r"\d{2}[A-Z]{3}\d{4}", symbol)
    return m.group(0) if m else None

class TradeRecord:
    def __init__(self):
        self.leg_entries: dict[int, dict] = {}
        self.trades: list[dict] = []
        self.daily_pnl: dict[str, float] = {}
        self.equity: list[dict] = []
        self.capital = 100000.0
        self.peak = 100000.0
        self.max_drawdown = 0.0

    def add_entry(self, leg_order: int, entry: dict):
        self.leg_entries[leg_order] = entry

    def add_exit(self, leg_order: int, exit_premium: float, exit_time: str, date_key: str):
        entry = self.leg_entries.pop(leg_order, None)
        if not entry:
            return
        pnl = exit_premium - entry["premium"] if entry["position"] == "buy" else entry["premium"] - exit_premium
        self.capital += pnl
        trade = {
            "leg_order": leg_order,
            "symbol": entry["symbol"],
            "position": entry["position"],
            "option_type": entry.get("option_type"),
            "strike": entry.get("strike"),
            "lots": entry["lots"],
            "entry_premium": entry["premium"],
            "exit_premium": exit_premium,
            "pnl": round(pnl, 2),
            "entry_time": entry["entry_time"],
            "exit_time": exit_time,
        }
        self.trades.append(trade)
        self.daily_pnl[date_key] = self.daily_pnl.get(date_key, 0) + pnl

    def snapshot_equity(self, timestamp: str):
        self.equity.append({"equity": round(self.capital, 2), "timestamp": timestamp})
        if self.capital > self.peak:
            self.peak = self.capital
        dd = self.peak - self.capital
        if dd > self.max_drawdown:
            self.max_drawdown = dd

async def run_user_strategy_backtest(
    strategy: UserStrategy,
    from_date: str,
    to_date: str,
    user_id: str | None = None,
) -> dict:
    days = (datetime.strptime(to_date, "%Y-%m-%d") - datetime.strptime(from_date, "%Y-%m-%d")).days
    if days < 1:
        return {"error": "to_date must be after from_date", "data_source": "simulated"}
    if days > BACKTEST_MAX_DAYS:
        return {"error": f"max backtest range is {BACKTEST_MAX_DAYS} days", "data_source": "simulated"}

    raw_candles = await historical_engine.get_historical(
        symbol=strategy.index_symbol,
        interval=BACKTEST_INTERVAL,
        days=days + 10,
        user_id=user_id,
    )
    if not raw_candles:
        return {"error": "no historical data available", "data_source": "simulated"}

    data_source = "real" if _has_real_data(raw_candles) else "simulated"
    all_close = [float(c.get("close", 0)) for c in raw_candles if c.get("close")]

    candles_by_date: dict[str, list[dict]] = {}
    for c in raw_candles:
        ts = c.get("timestamp", "")
        d = ts[:10] if isinstance(ts, str) else ""
        if d:
            candles_by_date.setdefault(d, []).append(c)

    spot = _estimate_spot_from_candles(raw_candles)
    plan = compile_user_strategy(strategy, spot_price=spot, is_simulated=(data_source != "real"))

    option_candles_cache: dict[str, list[dict]] = {}
    if user_id and data_source == "real":
        for leg in strategy.legs:
            leg_order = leg.leg_order
            order = plan.orders[leg_order - 1] if leg_order <= len(plan.orders) else None
            if not order:
                continue
            opt_symbol = f"NSE:{order.symbol.replace('/', '')}" if ":" not in order.symbol else order.symbol
            opt_candles = await historical_engine.get_historical(
                symbol=opt_symbol,
                interval=BACKTEST_INTERVAL,
                days=days + 10,
                user_id=user_id,
            )
            if opt_candles and len(opt_candles) > 5:
                option_candles_cache[order.symbol] = opt_candles
                logger.info("Fetched %d real option candles for %s", len(opt_candles), order.symbol)

    tr = TradeRecord()
    lot_size = LOT_SIZES.get(strategy.index_symbol, 65)

    from_date_dt = datetime.strptime(from_date, "%Y-%m-%d")
    to_date_dt = datetime.strptime(to_date, "%Y-%m-%d")
    day_count = 0
    current = from_date_dt
    while current <= to_date_dt:
        date_key = current.strftime("%Y-%m-%d")
        dow = current.weekday() + 1
        if dow in (strategy.days_of_week or [1, 2, 3, 4, 5]) and date_key in candles_by_date:
            day_candles = candles_by_date[date_key]
            entry_time = strategy.entry_time
            exit_time = strategy.exit_time
            entry_candle = _find_candle_at_time(day_candles, entry_time)
            exit_candle = _find_candle_at_time(day_candles, exit_time)
            if entry_candle and exit_candle:
                entry_spot = float(entry_candle.get("close", entry_candle.get("open", spot)))
                exit_spot = float(exit_candle.get("close", exit_candle.get("open", spot)))
                for leg in strategy.legs:
                    leg_order = leg.leg_order
                    order = plan.orders[leg_order - 1] if leg_order <= len(plan.orders) else None
                    if not order:
                        continue
                    leg_info = _parse_strike_from_symbol(order.symbol)
                    if not leg_info:
                        continue
                    strike, opt_type = leg_info
                    total_dte = _estimate_days_to_expiry(order.symbol)

                    opt_candles_for_symbol = option_candles_cache.get(order.symbol)
                    entry_price = _find_option_price_at_time(opt_candles_for_symbol, f"{date_key}T{entry_time}") if opt_candles_for_symbol else None
                    exit_price = _find_option_price_at_time(opt_candles_for_symbol, f"{date_key}T{exit_time}") if opt_candles_for_symbol else None

                    if entry_price is not None and exit_price is not None:
                        entry_premium = entry_price
                        exit_premium = exit_price
                        data_source = "real"
                    else:
                        entry_premium = _estimate_option_premium(entry_spot, strike, opt_type, total_dte, total_dte, all_close)
                        exit_premium = _estimate_option_premium(exit_spot, strike, opt_type, 0, total_dte, all_close)

                    tr.add_entry(leg_order, {
                        "symbol": order.symbol,
                        "position": "buy" if leg.position.value == "buy" else "sell",
                        "option_type": opt_type.value,
                        "strike": strike,
                        "lots": leg.lots,
                        "premium": entry_premium * leg.lots * lot_size,
                        "entry_time": f"{date_key}T{entry_time}",
                    })
                    tr.add_exit(leg_order, exit_premium * leg.lots * lot_size, f"{date_key}T{exit_time}", date_key)
                tr.snapshot_equity(f"{date_key}T{exit_time}")
                day_count += 1
        current += timedelta(days=1)

    if day_count == 0:
        return {"error": "no trading days in range", "data_source": data_source, "total_trades": 0}

    return _compute_results(tr, day_count, data_source)

def _has_real_data(candles: list[dict]) -> bool:
    if len(candles) < 10:
        return False
    from market.historical import historical_engine
    import random
    sample = candles[:5]
    for c in sample:
        o, h, l, cl = float(c.get("open", 0)), float(c.get("high", 0)), float(c.get("low", 0)), float(c.get("close", 0))
        if abs(o - cl) < 0.001 and abs(h) > 0 and abs(l) > 0:
            continue
        if o != cl:
            return True
    return False

def _estimate_spot_from_candles(candles: list[dict]) -> float:
    for c in reversed(candles):
        price = c.get("close") or c.get("open")
        if price:
            return float(price)
    return 24000.0

def _find_option_price_at_time(candles: list[dict] | None, target_time_str: str) -> float | None:
    if not candles:
        return None
    target_h, target_m = target_time_str.split("T")[1][:5].split(":")
    target_total = int(target_h) * 60 + int(target_m)
    best = None
    best_diff = 9999
    for c in candles:
        ts = c.get("timestamp", "")
        if isinstance(ts, str) and "T" in ts:
            time_part = ts.split("T")[1][:5]
        elif isinstance(ts, str) and len(ts) >= 16:
            time_part = ts[11:16]
        else:
            continue
        h, m = time_part.split(":")
        total = int(h) * 60 + int(m)
        diff = abs(total - target_total)
        if diff < best_diff:
            best_diff = diff
            best = c
    if best is None:
        return None
    return float(best.get("close", 0))

def _find_candle_at_time(candles: list[dict], target_time: str) -> dict | None:
    target_h, target_m = target_time.split(":")
    target_total = int(target_h) * 60 + int(target_m)
    best = None
    best_diff = 9999
    for c in candles:
        ts = c.get("timestamp", "")
        if isinstance(ts, str) and "T" in ts:
            time_part = ts.split("T")[1][:5]
        elif isinstance(ts, str) and len(ts) >= 16:
            time_part = ts[11:16]
        else:
            continue
        h, m = time_part.split(":")
        total = int(h) * 60 + int(m)
        diff = abs(total - target_total)
        if diff < best_diff:
            best_diff = diff
            best = c
    return best

def _estimate_days_to_expiry(expiry_str: str | None) -> int:
    from datetime import datetime
    expiry = _parse_expiry_from_symbol(expiry_str or "")
    if not expiry:
        return 20
    try:
        exp_dt = datetime.strptime(expiry, "%d%b%Y")
        now = datetime.now()
        remaining = (exp_dt - now).days
        return max(remaining, 1)
    except ValueError:
        return 20

def _compute_results(tr: TradeRecord, day_count: int, data_source: str) -> dict:
    total_trades = len(tr.trades)
    winning = [t for t in tr.trades if t["pnl"] > 0]
    losing = [t for t in tr.trades if t["pnl"] <= 0]
    win_rate = round(len(winning) / total_trades * 100, 2) if total_trades > 0 else 0
    total_pnl = sum(t["pnl"] for t in tr.trades)
    max_dd = round(tr.max_drawdown, 2)
    avg_win = round(sum(t["pnl"] for t in winning) / len(winning), 2) if winning else 0
    avg_loss = round(abs(sum(t["pnl"] for t in losing)) / len(losing), 2) if losing else 0

    monthly: dict[str, dict] = {}
    for t in tr.trades:
        month_key = t["entry_time"][:7]
        m = monthly.setdefault(month_key, {"trades": 0, "pnl": 0.0, "wins": 0})
        m["trades"] += 1
        m["pnl"] += t["pnl"]
        if t["pnl"] > 0:
            m["wins"] += 1
    monthly_returns = [{"month": k, **v, "pnl": round(v["pnl"], 2)} for k, v in sorted(monthly.items())]

    start_equity = 100000.0
    end_equity = round(tr.capital, 2)
    returns_pct = round((end_equity - start_equity) / start_equity * 100, 2)

    return {
        "data_source": data_source,
        "total_trades": total_trades,
        "winning_trades": len(winning),
        "losing_trades": len(losing),
        "win_rate": win_rate,
        "total_pnl": round(total_pnl, 2),
        "max_drawdown": max_dd,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "total_days": day_count,
        "start_equity": start_equity,
        "end_equity": end_equity,
        "returns_pct": returns_pct,
        "trades": tr.trades,
        "equity_curve": tr.equity,
        "monthly_returns": monthly_returns,
    }
