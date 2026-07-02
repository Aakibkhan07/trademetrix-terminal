import asyncio
import logging
import random
from datetime import UTC, datetime

from core.models import Exchange, Tick
from market.data_socket import shared_socket

logger = logging.getLogger(__name__)

REALISTIC_PRICES: dict[str, float] = {
    "NSE:NIFTY50-INDEX": 24200, "NSE:NIFTYBANK-INDEX": 52000, "NSE:FINNIFTY-INDEX": 22500,
    "BSE:SENSEX-INDEX": 80500, "NSE:MIDCPNIFTY-INDEX": 17500, "NSE:INDIAVIX-INDEX": 13,
    "NSE:NIFTYIT-INDEX": 38000, "NSE:NIFTYPHARMA-INDEX": 20000, "NSE:NIFTYAUTO-INDEX": 22500,
    "NSE:NIFTYFMCG-INDEX": 18500, "NSE:NIFTYMETAL-INDEX": 9500, "NSE:NIFTYREALTY-INDEX": 750,
    "NSE:NIFTYENERGY-INDEX": 15000, "NSE:NIFTYMEDIA-INDEX": 2000, "NSE:NIFTYPSUBANK-INDEX": 5500,
    "NSE:NIFTYPVTBANK-INDEX": 25000, "NSE:NIFTYCONSR-INDEX": 14000, "NSE:NIFTYOILGAS-INDEX": 11000,
    "NSE:NIFTYDIVOP-INDEX": 5000, "NSE:NIFTYGSEC-INDEX": 2100,
    "NSE:RELIANCE-EQ": 2850, "NSE:TCS-EQ": 3800, "NSE:HDFCBANK-EQ": 1650,
    "NSE:INFY-EQ": 1700, "NSE:ICICIBANK-EQ": 1250, "NSE:SBIN-EQ": 800,
    "NSE:BHARTIARTL-EQ": 1400, "NSE:KOTAKBANK-EQ": 1800, "NSE:ITC-EQ": 430,
    "NSE:WIPRO-EQ": 450, "NSE:HCLTECH-EQ": 1500, "NSE:LT-EQ": 3450,
    "NSE:TITAN-EQ": 3300, "NSE:MARUTI-EQ": 11800, "NSE:ASIANPAINT-EQ": 2800,
    "NSE:BAJFINANCE-EQ": 6800, "NSE:AXISBANK-EQ": 1200, "NSE:DMART-EQ": 4200,
    "NSE:SUNPHARMA-EQ": 1500, "NSE:ULTRACEMCO-EQ": 11000, "NSE:NTPC-EQ": 350,
    "NSE:POWERGRID-EQ": 300, "NSE:ONGC-EQ": 260, "NSE:COALINDIA-EQ": 450,
    "NSE:ADANIENT-EQ": 2800, "NSE:ADANIPORTS-EQ": 1400, "NSE:BAJAJ-AUTO-EQ": 8800,
    "NSE:BAJAJFINSV-EQ": 1650, "NSE:BRITANNIA-EQ": 5300, "NSE:CIPLA-EQ": 1450,
    "NSE:DRREDDY-EQ": 4800, "NSE:EICHERMOT-EQ": 4500, "NSE:GRASIM-EQ": 2500,
    "NSE:HDFCLIFE-EQ": 600, "NSE:HEROMOTOCO-EQ": 4800, "NSE:HINDALCO-EQ": 650,
    "NSE:HINDUNILVR-EQ": 2500, "NSE:INDUSINDBK-EQ": 1400, "NSE:JSWSTEEL-EQ": 900,
    "NSE:M&M-EQ": 2800, "NSE:NESTLEIND-EQ": 25000, "NSE:TATACONSUM-EQ": 1150,
    "NSE:TATAMOTORS-EQ": 950, "NSE:TATASTEEL-EQ": 150, "NSE:TECHM-EQ": 1450,
}


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
            base = REALISTIC_PRICES.get(s, random.uniform(50, 50000))
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
