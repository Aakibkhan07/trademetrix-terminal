"""
Crypto market-data feed from Binance public WebSocket.
READ-ONLY — no API key needed, no trading capability.
"""
import asyncio
import json
import logging
from datetime import UTC, datetime

from core.models import Tick
from market.data_socket import shared_socket

logger = logging.getLogger(__name__)

BINANCE_STREAM = "wss://stream.binance.com:9443/stream"

CRYPTO_PAIRS = [
    "btcusdt", "ethusdt", "solusdt", "bnbusdt",
    "xrpusdt", "adausdt", "dogeusdt", "avaxusdt",
    "maticusdt", "dotusdt",  "linkusdt", "uniusdt",
    "atomusdt",  "ltcusdt", "bchusdt",  "trxusdt",
]


class CryptoFeed:
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

    @property
    def latest_prices(self) -> dict[str, dict]:
        return dict(self._prices)

    def get_price(self, symbol: str) -> float | None:
        s = symbol.upper()
        data = self._prices.get(s)
        return data["price"] if data else None

    def get_ticker(self, symbol: str) -> dict | None:
        return self._prices.get(symbol.upper())

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info("CryptoFeed started — %d pairs", len(CRYPTO_PAIRS))

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("CryptoFeed stopped")

    async def _run(self):
        import websockets
        while self._running:
            try:
                streams = "/".join(f"{p}@ticker" for p in CRYPTO_PAIRS)
                url = f"{BINANCE_STREAM}?streams={streams}"
                async with websockets.connect(url, ping_interval=20) as ws:
                    async for raw in ws:
                        await self._handle(raw)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("CryptoFeed reconnect: %s", e)
                await asyncio.sleep(3)

    async def _handle(self, raw: str):
        try:
            data = json.loads(raw)
            payload = data.get("data", data)
            symbol = payload.get("s", "").upper()
            price = float(payload.get("c", 0))
            if price <= 0 or not symbol:
                return

            ticker = {
                "price": price,
                "change": float(payload.get("p", 0)),
                "change_pct": float(payload.get("P", 0)),
                "high": float(payload.get("h", 0)),
                "low": float(payload.get("l", 0)),
                "open": float(payload.get("o", 0)),
                "volume": float(payload.get("v", 0)),
                "timestamp": datetime.now(UTC).isoformat(),
            }
            self._prices[symbol] = ticker

            tick = Tick(
                symbol=symbol,
                last_price=price,
                change=float(payload.get("p", 0)),
                change_pct=float(payload.get("P", 0)),
                volume=float(payload.get("v", 0)),
                high=float(payload.get("h", 0)),
                low=float(payload.get("l", 0)),
                close=price,
                broker="crypto",
                timestamp=datetime.now(UTC),
            )
            await shared_socket.broadcast_tick(tick)
        except Exception as e:
            logger.error("CryptoFeed parse: %s", e)


crypto_feed = CryptoFeed()
