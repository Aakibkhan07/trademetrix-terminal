import logging
import random
from datetime import UTC, datetime, timedelta

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
        self._returns: list[float] = []
        self._slippage_pct = slippage_pct
        self._brokerage_pct = brokerage_pct
        self._stt_pct = stt_pct
        self._exchange_pct = exchange_pct

    def _apply_costs(self, entry_price: float, exit_price: float, quantity: int) -> tuple[float, float]:
        trade_value_entry = entry_price * quantity
        trade_value_exit = exit_price * quantity
        slippage = (entry_price + exit_price) * quantity * (self._slippage_pct / 100)
        brokerage = (trade_value_entry + trade_value_exit) * (self._brokerage_pct / 100)
        stt = trade_value_exit * (self._stt_pct / 100)
        exchange_fee = (trade_value_entry + trade_value_exit) * (self._exchange_pct / 100)
        total_cost = slippage + brokerage + stt + exchange_fee
        return total_cost, brokerage + exchange_fee

    def record_trade(self, symbol: str, side: str, entry_price: float, exit_price: float,
                     quantity: int, entry_time: str, exit_time: str):
        costs, _ = self._apply_costs(entry_price, exit_price, quantity)
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
    if user_id:
        try:
            from core.db import async_supabase, get_supabase
            from core.security import decrypt_broker_credentials
            supabase = get_supabase()
            cred = await async_supabase(lambda: supabase.table("broker_credentials").select("*").eq("user_id", user_id).eq("broker", "fyers").single().execute())
            if cred.data:
                row = cred.data
                client_id = decrypt_broker_credentials(row["encrypted_api_key"])
                raw_token = decrypt_broker_credentials(row["encrypted_access_token"])

                fyers_symbol = _map_to_fyers_symbol(symbol, exchange)

                fyers_interval = _resolve_fyers_interval(interval)
                import time
                now = int(time.time())
                start_ts = str(now - days * 86400)

                from brokers.fyers_adapter import FyersAdapter
                adapter = FyersAdapter()
                await adapter.authenticate({"client_id": client_id, "access_token": raw_token})
                candles = await adapter.get_historical(fyers_symbol, fyers_interval, start_ts, str(now))
                if candles:
                    logger.info("Backtest using %d real candles from Fyers for %s", len(candles), fyers_symbol)
                    return [_candle_to_dict(c) for c in candles]
                logger.warning("Fyers returned 0 candles for %s", fyers_symbol)
        except Exception as e:
            logger.warning("Failed to fetch real data from Fyers (%s)", e)

    logger.warning("No broker data available — using synthetic data for backtest")
    syn = _synthesize_candles(symbol, days, interval)
    logger.info("Generated %d synthetic candles for %s", len(syn), symbol)
    return syn


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


def _map_to_fyers_symbol(symbol: str, exchange: str) -> str:
    if ":" in symbol:
        return symbol
    mapping = {
        "NIFTY": "NSE:NIFTY50-INDEX",
        "BANKNIFTY": "NSE:NIFTYBANK-INDEX",
        "FINNIFTY": "NSE:FINNIFTY-INDEX",
        "SENSEX": "BSE:SENSEX-INDEX",
        "MIDCPNIFTY": "NSE:MIDCPNIFTY-INDEX",
        "NIFTY50": "NSE:NIFTY50-INDEX",
    }
    if symbol.upper() in mapping:
        return mapping[symbol.upper()]
    return f"{exchange}:{symbol}"


def _resolve_fyers_interval(interval: str) -> str:
    mins = _parse_interval_minutes(interval)
    fyers_map = {1: "1", 2: "2", 3: "3", 5: "5", 10: "10", 15: "15", 20: "20", 30: "30", 60: "60",
                  120: "120", 180: "180", 240: "240", 360: "360", 480: "480", 720: "720", 960: "960", 1440: "D"}
    return fyers_map.get(mins, "15")


def _candle_to_dict(c: Candle) -> dict:
    return {
        "symbol": c.symbol,
        "exchange": c.exchange.value if hasattr(c.exchange, "value") else str(c.exchange),
        "interval": c.interval,
        "open": c.open,
        "high": c.high,
        "low": c.low,
        "close": c.close,
        "volume": c.volume,
        "timestamp": c.timestamp.isoformat() if hasattr(c.timestamp, "isoformat") else str(c.timestamp),
    }


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
