import asyncio
import logging
import random
from datetime import datetime

from core.models import Tick, Exchange
from market.data_socket import shared_socket

logger = logging.getLogger(__name__)

DEFAULT_SYMBOLS = [
    "NIFTY", "BANKNIFTY", "RELIANCE", "TCS", "HDFCBANK",
    "INFY", "ICICIBANK", "SBIN", "BHARTIARTL", "KOTAKBANK",
]

class MarketSimulator:
    def __init__(self):
        self._prices: dict[str, float] = {}
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self, symbols: list[str] | None = None):
        if self._running:
            return
        self._running = True
        symbols = symbols or DEFAULT_SYMBOLS
        for s in symbols:
            self._prices[s] = random.uniform(100, 5000)
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
            for symbol in symbols:
                price = self._prices.get(symbol, 1000)
                change = price * random.uniform(-0.002, 0.002)
                new_price = round(price + change, 2)
                self._prices[symbol] = new_price

                tick = Tick(
                    symbol=symbol,
                    exchange=Exchange.NSE,
                    last_price=new_price,
                    bid=round(new_price - random.uniform(0.05, 2.0), 2),
                    ask=round(new_price + random.uniform(0.05, 2.0), 2),
                    bid_qty=random.randint(100, 5000),
                    ask_qty=random.randint(100, 5000),
                    volume=random.randint(1000, 50000),
                    oi=random.randint(100000, 5000000),
                    timestamp=datetime.utcnow(),
                    broker="simulator",
                )
                await shared_socket.broadcast_tick(tick)
            await asyncio.sleep(random.uniform(0.5, 2.0))


market_simulator = MarketSimulator()
