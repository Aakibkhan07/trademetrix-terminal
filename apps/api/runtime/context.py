import logging
from datetime import UTC, datetime, timedelta, timezone

from core.models import Candle, Tick
from market.cache import market_cache
from market.status import market_status_service
from portfolio.manager import portfolio_manager
from runtime.models import RuntimeConfig

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))


class RuntimeContext:
    def __init__(self, config: RuntimeConfig):
        self._config = config

    async def build(self, tick: Tick | None = None, candle: Candle | None = None) -> dict:
        user_id = self._config.user_id
        broker = self._config.broker
        symbol = self._config.symbol
        interval = self._config.interval

        context = {
            "config": self._config.model_dump(),
            "symbol": symbol,
            "exchange": self._config.exchange,
            "interval": interval,
            "timestamp": datetime.now(UTC),
            "market_open": market_status_service.is_market_open(),
            "trading_session": self._get_trading_session(),
        }

        context["tick"] = self._build_tick_context(tick)
        context["candle"] = self._build_candle_context(candle)
        context["indicators"] = self._build_indicator_context(symbol, interval)
        context["portfolio"] = await self._build_portfolio_context(user_id, broker)
        context["variables"] = self._config.variables

        return context

    def _build_tick_context(self, tick: Tick | None) -> dict:
        if tick:
            return {
                "symbol": tick.symbol,
                "last_price": tick.last_price,
                "bid": tick.bid,
                "ask": tick.ask,
                "volume": tick.volume,
                "oi": tick.oi,
                "change": tick.change,
                "change_pct": tick.change_pct,
                "timestamp": tick.timestamp.isoformat() if tick.timestamp else "",
            }

        cached = market_cache.get_quote(self._config.symbol)
        if cached:
            return {
                "symbol": self._config.symbol,
                "last_price": cached.get("last_price", 0),
                "bid": cached.get("bid", 0),
                "ask": cached.get("ask", 0),
                "volume": cached.get("volume", 0),
                "oi": cached.get("oi", 0),
                "change": cached.get("change", 0),
                "change_pct": cached.get("change_pct", 0),
            }
        return {}

    def _build_candle_context(self, candle: Candle | None) -> dict | None:
        if candle:
            return {
                "symbol": candle.symbol,
                "open": candle.open,
                "high": candle.high,
                "low": candle.low,
                "close": candle.close,
                "volume": candle.volume,
                "oi": candle.oi,
                "timestamp": candle.timestamp.isoformat() if candle.timestamp else "",
            }
        return None

    def _build_indicator_context(self, symbol: str, interval: str) -> dict:
        candles = getattr(market_cache, '_candles', {}).get(f"{symbol}:{interval}", []) or []
        prices = [c.close for c in candles] if candles else []

        context = {"prices": prices, "highs": [c.high for c in candles] if candles else [],
                   "lows": [c.low for c in candles] if candles else [],
                   "volumes": [c.volume for c in candles] if candles else [],
                   "timestamps": [c.timestamp.isoformat() if c.timestamp else "" for c in candles] if candles else [],
                   "current": candles[-1] if candles else None}

        if len(prices) >= 2:
            context["change"] = prices[-1] - prices[-2]
            context["change_pct"] = ((prices[-1] - prices[-2]) / prices[-2] * 100) if prices[-2] != 0 else 0
        if prices:
            context["high"] = max(prices)
            context["low"] = min(prices)
            context["avg"] = sum(prices) / len(prices)

        return context

    async def _build_portfolio_context(self, user_id: str, broker: str) -> dict:
        try:
            positions = await portfolio_manager.get_positions(user_id, broker)
            pnl = await portfolio_manager.get_pnl(user_id, broker)
            funds = await portfolio_manager.get_margin(user_id, broker)

            return {
                "positions": [p.model_dump() for p in positions],
                "open_positions": [p for p in positions if p.quantity != 0],
                "position_count": len(positions),
                "open_position_count": sum(1 for p in positions if p.quantity != 0),
                "unrealised_pnl": pnl.unrealised_pnl,
                "realised_pnl": pnl.realised_pnl,
                "daily_pnl": pnl.daily_pnl,
                "overall_pnl": pnl.overall_pnl,
                "drawdown_pct": pnl.drawdown_pct,
                "total_margin": funds.total_margin,
                "used_margin": funds.used_margin,
                "available_margin": funds.available_margin,
            }
        except Exception as e:
            logger.debug("Failed to build portfolio context: %s", e)
            return {}

    @staticmethod
    def _get_trading_session() -> str:
        now = datetime.now(IST)
        hour = now.hour
        minute = now.minute
        current = hour * 60 + minute

        if current < 555:
            return "PRE_MARKET"
        elif current < 915:
            return "OPENING"
        elif current < 930:
            return "EARLY"
        elif current < 1500:
            return "REGULAR"
        elif current < 1530:
            return "CLOSING"
        elif current < 1555:
            return "POST_CLOSE"
        return "CLOSED"
