import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from core.db import get_supabase
from core.models import Candle, Tick, NormalizedOrder, OrderSide, OrderType, ProductType, Exchange
from strategies import get_strategy

logger = logging.getLogger(__name__)


class BacktestResult:
    def __init__(self):
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.total_pnl = 0.0
        self.max_drawdown = 0.0
        self.sharpe_ratio = 0.0
        self.win_rate = 0.0
        self.avg_win = 0.0
        self.avg_loss = 0.0
        self.largest_win = 0.0
        self.largest_loss = 0.0
        self.trades: list[dict] = []
        self.equity_curve: list[dict] = []
        self._peak = 0.0
        self._returns: list[float] = []

    def record_trade(self, symbol: str, side: str, entry_price: float, exit_price: float,
                     quantity: int, entry_time: str, exit_time: str):
        pnl = (exit_price - entry_price) * quantity if side == "BUY" else (entry_price - exit_price) * quantity
        self.total_trades += 1
        if pnl > 0:
            self.winning_trades += 1
            self.avg_win = (self.avg_win * (self.winning_trades - 1) + pnl) / self.winning_trades
            self.largest_win = max(self.largest_win, pnl)
        else:
            self.losing_trades += 1
            self.avg_loss = (self.avg_loss * (self.losing_trades - 1) + abs(pnl)) / self.losing_trades if self.losing_trades > 0 else abs(pnl)
            self.largest_loss = min(self.largest_loss, pnl)
        self.total_pnl += pnl
        self._returns.append(pnl)
        self.trades.append({
            "symbol": symbol, "side": side,
            "entry_price": entry_price, "exit_price": exit_price,
            "quantity": quantity, "pnl": round(pnl, 2),
            "entry_time": entry_time, "exit_time": exit_time,
        })

    def update_equity(self, equity: float, timestamp: str):
        self.equity_curve.append({"equity": round(equity, 2), "timestamp": timestamp})
        if equity > self._peak:
            self._peak = equity
        dd = self._peak - equity if self._peak > 0 else 0
        self.max_drawdown = max(self.max_drawdown, dd)

    def finalize(self, initial_capital: float):
        self.win_rate = (self.winning_trades / self.total_trades * 100) if self.total_trades > 0 else 0
        if len(self._returns) > 1:
            avg_r = sum(self._returns) / len(self._returns)
            std_r = (sum((r - avg_r) ** 2 for r in self._returns) / len(self._returns)) ** 0.5
            self.sharpe_ratio = (avg_r / std_r) * (252 ** 0.5) if std_r > 0 else 0

    def to_dict(self) -> dict:
        return {
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": round(self.win_rate, 2),
            "total_pnl": round(self.total_pnl, 2),
            "max_drawdown": round(self.max_drawdown, 2),
            "sharpe_ratio": round(self.sharpe_ratio, 2),
            "avg_win": round(self.avg_win, 2),
            "avg_loss": round(self.avg_loss, 2),
            "largest_win": round(self.largest_win, 2),
            "largest_loss": round(self.largest_loss, 2),
            "trades": self.trades,
            "equity_curve": self.equity_curve,
        }


class BacktestEngine:
    def __init__(self, strategy_type: str, config: dict, initial_capital: float = 100000):
        strategy_cls = get_strategy(strategy_type)
        if not strategy_cls:
            raise ValueError(f"Unknown strategy: {strategy_type}")
        self.strategy = strategy_cls(config)
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.result = BacktestResult()
        self._open_positions: dict[str, dict] = {}

    async def run(self, candles: list[dict]) -> BacktestResult:
        await self.strategy.on_start()

        for i, c in enumerate(candles):
            candle = Candle(**c)
            signal = await self.strategy.on_candle(candle)

            if signal and signal.orders:
                for order in signal.orders:
                    await self._handle_order(order, candle)

            self.result.update_equity(self.capital, candle.timestamp.isoformat() if hasattr(candle.timestamp, 'isoformat') else str(candle.timestamp))

        for sym, pos in list(self._open_positions.items()):
            if candles:
                last = candles[-1]
                exit_price = float(last.get("close", 0))
                self.result.record_trade(
                    symbol=sym, side=pos["side"],
                    entry_price=pos["entry_price"],
                    exit_price=exit_price,
                    quantity=pos["quantity"],
                    entry_time=pos["entry_time"],
                    exit_time=last.get("timestamp", ""),
                )
                pnl = (exit_price - pos["entry_price"]) * pos["quantity"] if pos["side"] == "BUY" else (pos["entry_price"] - exit_price) * pos["quantity"]
                self.capital += pnl

        await self.strategy.on_stop()
        self.result.finalize(self.initial_capital)
        return self.result

    async def _handle_order(self, order: NormalizedOrder, candle: Candle):
        price = candle.close if order.order_type == OrderType.MARKET else order.price
        cost = price * order.quantity

        if order.side == OrderSide.BUY:
            if cost <= self.capital:
                self._open_positions[order.symbol] = {
                    "side": "BUY", "entry_price": price,
                    "quantity": order.quantity,
                    "entry_time": candle.timestamp.isoformat() if hasattr(candle.timestamp, 'isoformat') else str(candle.timestamp),
                }
                self.capital -= cost
        else:
            pos = self._open_positions.pop(order.symbol, None)
            if pos:
                entry_price = pos["entry_price"]
                pnl = (price - entry_price) * order.quantity
                self.capital += price * order.quantity
                self.result.record_trade(
                    symbol=order.symbol, side=pos["side"],
                    entry_price=entry_price, exit_price=price,
                    quantity=order.quantity,
                    entry_time=pos["entry_time"],
                    exit_time=candle.timestamp.isoformat() if hasattr(candle.timestamp, 'isoformat') else str(candle.timestamp),
                )


async def fetch_historical_data(symbol: str, exchange: str = "NSE", interval: str = "15m",
                                 days: int = 60) -> list[dict]:
    supabase = get_supabase()
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()
    result = supabase.table("symbol_master") \
        .select("*") \
        .eq("symbol", symbol) \
        .eq("exchange", exchange) \
        .limit(1) \
        .execute()
    if not result.data:
        logger.warning("Symbol %s not found in master, using synthesized data", symbol)
        return _synthesize_candles(symbol, days, interval)
    return _synthesize_candles(symbol, days, interval)


def _synthesize_candles(symbol: str, days: int, interval: str) -> list[dict]:
    import random
    import math
    candles = []
    base_price = random.uniform(500, 5000)
    now = datetime.utcnow()
    interval_min = int(interval.replace("m", "").replace("min", "")) if interval.endswith("m") else 15
    total = days * 24 * 60 // interval_min
    price = base_price
    for i in range(total):
        ts = now - timedelta(minutes=(total - i) * interval_min)
        change = price * random.uniform(-0.015, 0.015)
        o = price
        h = o + abs(change) * random.uniform(0.5, 1.5)
        l = o - abs(change) * random.uniform(0.5, 1.5)
        c = o + change
        price = c
        candles.append({
            "symbol": symbol,
            "exchange": "NSE",
            "interval": interval,
            "open": round(o, 2),
            "high": round(h, 2),
            "low": round(l, 2),
            "close": round(c, 2),
            "volume": random.randint(10000, 500000),
            "timestamp": ts.isoformat(),
            "oi": random.randint(100000, 5000000),
        })
    return candles
