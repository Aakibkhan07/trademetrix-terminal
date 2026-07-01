import asyncio
import logging
import random
from datetime import UTC, date, datetime, time, timedelta, timezone

from core.models import Exchange, Tick
from market.data_socket import shared_socket

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))
MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)


def _is_market_hours() -> bool:
    now_ist = datetime.now(IST)
    if now_ist.weekday() >= 5:
        return False
    return MARKET_OPEN <= now_ist.time() <= MARKET_CLOSE


class MarketSimulator:
    def __init__(self):
        self._prices: dict[str, float] = {}
        self._prev_close: dict[str, float] = {}
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self, symbols: list[str] | None = None):
        if self._running:
            await self.stop()
        self._running = True
        symbols = symbols or []
        for s in symbols:
            base = random.uniform(50, 50000)
            self._prices[s] = base
            self._prev_close[s] = base * random.uniform(0.97, 1.03)
        self._task = asyncio.create_task(self._tick_loop(symbols))
        logger.info("MarketSimulator started with %d symbols", len(symbols))

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("MarketSimulator stopped")

    async def _tick_loop(self, symbols: list[str]):
        while self._running:
            if not _is_market_hours():
                await asyncio.sleep(30)
                continue

            for symbol in symbols:
                price = self._prices.get(symbol, 1000)
                change = price * random.uniform(-0.003, 0.003)
                new_price = round(price + change, 2)
                self._prices[symbol] = new_price

                prev_close = self._prev_close.get(symbol, price)
                delta_day = round(new_price - prev_close, 2)
                delta_day_pct = round((delta_day / prev_close * 100), 2) if prev_close else 0

                tick = Tick(
                    symbol=symbol,
                    exchange=Exchange.NSE,
                    last_price=new_price,
                    change=delta_day,
                    change_pct=delta_day_pct,
                    bid=round(new_price - random.uniform(0.05, 5.0), 2),
                    ask=round(new_price + random.uniform(0.05, 5.0), 2),
                    bid_qty=random.randint(100, 5000),
                    ask_qty=random.randint(100, 5000),
                    volume=random.randint(1000, 500000),
                    oi=random.randint(100000, 5000000),
                    timestamp=datetime.now(UTC),
                    broker="simulator",
                )
                await shared_socket.broadcast_tick(tick)
            await asyncio.sleep(random.uniform(0.5, 1.5))


market_simulator = MarketSimulator()
