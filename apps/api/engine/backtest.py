import logging
import random
from datetime import UTC, datetime, timedelta

from backtest.performance import compute_sharpe_ratio
from core.models import Candle, NormalizedOrder, OrderSide, OrderType
from strategies import get_strategy

logger = logging.getLogger(__name__)


class BacktestResult:
    def __init__(self, slippage_pct: float = 0.05, brokerage_pct: float = 0.03,
                 stt_pct: float = 0.025, exchange_pct: float = 0.003):
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
        self._slippage_pct = slippage_pct
        self._brokerage_pct = brokerage_pct
        self._stt_pct = stt_pct
        self._exchange_pct = exchange_pct

    def _apply_costs(self, side: str, entry_price: float, exit_price: float, quantity: int) -> tuple[float, float]:
        """Round-trip charges through the canonical cost engine (backtest.costs).

        The legacy percentage knobs (slippage/brokerage/stt/exchange) map onto
        a BacktestCostConfig so this path shares the SINGLE fee implementation
        used by run-v2/v3 — segment rates, GST, SEBI and stamp duty included.
        """
        from backtest.costs import (
            BacktestCostConfig,
            CostSegment,
            estimate_round_trip,
        )

        entry_value = entry_price * quantity
        exit_value = exit_price * quantity
        cfg = BacktestCostConfig(
            slippage_pct=self._slippage_pct,
            commission_pct=self._brokerage_pct,
            commission_min=0.0,
            stt_pct_override=self._stt_pct,
            exchange_tc_pct_override=self._exchange_pct,
        )
        est = estimate_round_trip(
            side=side,
            entry_value=entry_value,
            exit_value=exit_value,
            segment=CostSegment.EQUITY_INTRADAY,
            qty=quantity,
            slippage_entry=entry_value * self._slippage_pct / 100,
            slippage_exit=exit_value * self._slippage_pct / 100,
            config=cfg,
        )
        return est.total, round(est.brokerage + est.exchange_tc, 2)

    def record_trade(self, symbol: str, side: str, entry_price: float, exit_price: float,
                     quantity: int, entry_time: str, exit_time: str):
        costs, _ = self._apply_costs(side, entry_price, exit_price, quantity)
        gross_pnl = (exit_price - entry_price) * quantity if side == "BUY" else (entry_price - exit_price) * quantity
        pnl = gross_pnl - costs
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
        # Canonical Sharpe: sample-stdev over equity-curve period returns,
        # annualized by sqrt(252) — identical to PerformanceAnalytics.
        self.sharpe_ratio = compute_sharpe_ratio(self._equity_returns())

    def _equity_returns(self) -> list[float]:
        returns = []
        for i in range(1, len(self.equity_curve)):
            prev = self.equity_curve[i - 1]["equity"]
            curr = self.equity_curve[i]["equity"]
            if prev > 0:
                returns.append((curr - prev) / prev)
        return returns

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
    def __init__(self, strategy_type: str, config: dict, initial_capital: float = 100000,
                 slippage_pct: float = 0.05, brokerage_pct: float = 0.03,
                 stt_pct: float = 0.025, exchange_pct: float = 0.003):
        strategy_cls = get_strategy(strategy_type)
        if not strategy_cls:
            raise ValueError(f"Unknown strategy: {strategy_type}")
        self.strategy = strategy_cls(config)
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.result = BacktestResult(
            slippage_pct=slippage_pct, brokerage_pct=brokerage_pct,
            stt_pct=stt_pct, exchange_pct=exchange_pct,
        )
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
                self.capital += price * order.quantity
                self.result.record_trade(
                    symbol=order.symbol, side=pos["side"],
                    entry_price=entry_price, exit_price=price,
                    quantity=order.quantity,
                    entry_time=pos["entry_time"],
                    exit_time=candle.timestamp.isoformat() if hasattr(candle.timestamp, 'isoformat') else str(candle.timestamp),
                )


async def fetch_historical_data(symbol: str, exchange: str = "NSE", interval: str = "15m",
                                 days: int = 60, user_id: str | None = None) -> list[dict]:
    """Real-candle loader: durable store first, then broker (Fyers), then Yahoo.

    Synthetic candles are a last resort and are clearly logged — a backtest
    must never silently run on fabricated data when real data exists.
    """
    try:
        from backtest.historical import backtest_historical

        candles = await backtest_historical.load(
            symbol=symbol, exchange=exchange, interval=interval,
            days=days, user_id=user_id,
        )
        if candles:
            logger.info("Backtest using %d real candles for %s", len(candles), symbol)
            return candles
    except Exception as e:
        logger.warning("Failed to fetch real data for backtest (%s)", e)

    raise ValueError(
        f"No real market data available for {symbol} ({interval}, {days}d) — "
        "backtests never run on fabricated candles. Verify the symbol or retry later."
    )


def _parse_interval_minutes(interval: str) -> int:
    interval = interval.lower().strip()
    try:
        if interval.endswith("min"):
            return int(interval.replace("min", ""))
        if interval.endswith("h"):
            return int(interval.replace("h", "")) * 60
        if interval.endswith("d"):
            return int(interval.replace("d", "")) * 1440
        if interval.endswith("m"):
            return int(interval.replace("m", ""))
        if interval.endswith("s"):
            return max(1, int(interval.replace("s", "")) // 60)
        return int(interval)
    except (ValueError, AttributeError):
        return 15


def _synthesize_candles(symbol: str, days: int = 30, interval: str = "15m") -> list[dict]:
    candles = []
    interval_minutes = max(1, int(interval.replace("m", "").replace("min", "")) if "m" in interval else 60)
    total = days * (6 * 60 // interval_minutes)  # ~6 trading hours per day
    now = datetime.now(UTC)
    base_price = 24000.0
    drift = 0.0001  # slight upward bias per candle
    volatility = 0.002  # base volatility per candle
    price = base_price

    # Pre-generate daily trend shifts for realistic movement
    daily_trends = [random.uniform(-0.003, 0.005) for _ in range(days)]

    candle_idx = 0
    for day in range(days):
        day_trend = daily_trends[day]
        day_vol = volatility * random.uniform(0.5, 2.0)
        for _ in range(total // days):
            open_p = price
            # Simulate intraday pattern: higher vol at open/close, lower midday
            intraday_vol = day_vol * random.uniform(0.7, 1.5)
            ret = drift + day_trend + random.gauss(0, intraday_vol)
            close_p = open_p * (1 + ret)
            high_p = max(open_p, close_p) * (1 + abs(random.gauss(0, intraday_vol * 0.6)))
            low_p = min(open_p, close_p) * (1 - abs(random.gauss(0, intraday_vol * 0.6)))
            # Volume: higher at open, tapering off
            vol_mult = max(0.3, 1.0 - (candle_idx % (total // days)) / (total // days) * 0.6)
            vol = int(random.randint(5000, 100000) * vol_mult)

            ts = now - timedelta(minutes=(total - candle_idx) * interval_minutes)
            candles.append({
                "symbol": symbol,
                "exchange": "NSE",
                "interval": interval,
                "open": round(open_p, 2),
                "high": round(high_p, 2),
                "low": round(low_p, 2),
                "close": round(close_p, 2),
                "volume": vol,
                "timestamp": ts,
                "oi": random.randint(100000, 500000),
            })
            price = close_p
            candle_idx += 1

    return candles
