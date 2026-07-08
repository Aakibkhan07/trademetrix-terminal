import asyncio
import logging
import random

logger = logging.getLogger(__name__)


class MarketSimulator:
    def __init__(self):
        self._prices: dict[str, float] = {}
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self, symbols: list[str]) -> None:
        for s in symbols:
            if s not in self._prices:
                self._prices[s] = random.uniform(100, 50000)
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._run_loop())
        logger.info("MarketSimulator started with %d symbols", len(self._prices))

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("MarketSimulator stopped")

    async def _run_loop(self) -> None:
        while self._running:
            for sym in self._prices:
                change = random.uniform(-0.005, 0.005)
                self._prices[sym] *= 1 + change
            await asyncio.sleep(1)
