"""
Forex market-data feed from free exchange-rate API (fawazahmed0/exchange-api).
No API key needed. Daily-updated rates, polled every 60s.
READ-ONLY — no trading capability here.
"""
import asyncio
import logging
from datetime import UTC, datetime

import httpx

from core.models import Tick
from market.data_socket import shared_socket

logger = logging.getLogger(__name__)

FOREX_PRIMARY = "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/usd.min.json"
FOREX_FALLBACK = "https://latest.currency-api.pages.dev/v1/currencies/usd.min.json"

FOREX_PAIRS = {
    "EURUSD": ("eur", False),
    "GBPUSD": ("gbp", False),
    "USDJPY": ("jpy", True),
    "USDCHF": ("chf", True),
    "AUDUSD": ("aud", False),
    "USDCAD": ("cad", True),
    "NZDUSD": ("nzd", False),
}


class ForexFeed:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._running = False
        self._task: asyncio.Task | None = None
        self._prices: dict[str, dict] = {}
        self._poll_interval = 60
        self._client: httpx.AsyncClient | None = None

    @property
    def latest_prices(self) -> dict[str, dict]:
        return dict(self._prices)

    def get_price(self, symbol: str) -> float | None:
        s = symbol.upper()
        data = self._prices.get(s)
        return data["price"] if data else None

    def get_ticker(self, symbol: str) -> dict | None:
        return self._prices.get(symbol.upper())

    @property
    def poll_interval_seconds(self) -> int:
        return self._poll_interval

    async def start(self):
        if self._running:
            return
        self._client = httpx.AsyncClient(timeout=10)
        self._running = True
        self._task = asyncio.create_task(self._poll())
        logger.info("ForexFeed started (poll every %ds)", self._poll_interval)

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        if self._client:
            await self._client.aclose()
            self._client = None
        logger.info("ForexFeed stopped")

    async def _poll(self):
        while self._running:
            try:
                await self._fetch()
            except Exception as e:
                logger.error("ForexFeed poll: %s", e)
            await asyncio.sleep(self._poll_interval)

    async def _fetch(self):
        client = self._client
        if not client:
            return
        try:
            r = await client.get(FOREX_PRIMARY)
            if r.status_code != 200:
                raise RuntimeError(f"Primary {r.status_code}")
            data = r.json()
        except Exception:
            if not client:
                return
            try:
                r = await client.get(FOREX_FALLBACK)
                if r.status_code != 200:
                    return
                data = r.json()
            except Exception as e:
                logger.warning("ForexFeed both sources failed: %s", e)
                return

        rates = data.get("usd", {})
        now = datetime.now(UTC)

        for pair, (quote_key, direct) in FOREX_PAIRS.items():
            rate = rates.get(quote_key)
            if rate is None or float(rate) <= 0:
                continue
            price = float(rate) if direct else 1.0 / float(rate)
            price = round(price, 6)

            ticker = {
                "price": price,
                "change": 0.0,
                "change_pct": 0.0,
                "high": price,
                "low": price,
                "open": price,
                "volume": 0,
                "timestamp": now.isoformat(),
            }
            self._prices[pair] = ticker

            tick = Tick(
                symbol=pair,
                last_price=price,
                close=price,
                broker="forex",
                timestamp=now,
            )
            await shared_socket.broadcast_tick(tick)

        logger.debug("ForexFeed: %d pairs updated", len(self._prices))


forex_feed = ForexFeed()
