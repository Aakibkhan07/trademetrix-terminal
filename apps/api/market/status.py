import asyncio
import logging
from datetime import UTC, datetime, timedelta

import httpx

from market.cache import market_cache

logger = logging.getLogger(__name__)

TRADING_START_HOUR = 9
TRADING_START_MIN = 15
TRADING_END_HOUR = 15
TRADING_END_MIN = 30


class MarketStatusService:
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
        self._holidays: list[str] = []
        self._last_holiday_sync: datetime | None = None

    def is_market_open(self) -> bool:
        now = datetime.now(UTC)
        ist = now + timedelta(hours=5, minutes=30)

        if ist.weekday() >= 5:
            return False

        if self._is_holiday(ist):
            return False

        market_open = ist.replace(hour=TRADING_START_HOUR, minute=TRADING_START_MIN, second=0, microsecond=0)
        market_close = ist.replace(hour=TRADING_END_HOUR, minute=TRADING_END_MIN, second=0, microsecond=0)

        return market_open <= ist <= market_close

    def get_market_status(self) -> dict:
        cached = market_cache.get_market_status()
        if cached:
            return cached

        now = datetime.now(UTC)
        ist = now + timedelta(hours=5, minutes=30)
        is_open = self.is_market_open()

        market_open = ist.replace(hour=TRADING_START_HOUR, minute=TRADING_START_MIN, second=0, microsecond=0)
        market_close = ist.replace(hour=TRADING_END_HOUR, minute=TRADING_END_MIN, second=0, microsecond=0)

        next_open = self._next_market_open(ist)
        next_holiday = self._next_holiday_date(ist)

        status = {
            "is_open": is_open,
            "market": "OPEN" if is_open else "CLOSED",
            "open_time": market_open.isoformat(),
            "close_time": market_close.isoformat(),
            "next_open": next_open.isoformat() if next_open else "",
            "next_holiday": next_holiday,
            "current_time": ist.isoformat(),
        }

        market_cache.put_market_status(status)
        return status

    def _is_holiday(self, dt: datetime) -> bool:
        date_str = dt.strftime("%Y-%m-%d")
        return date_str in self._holidays

    def _next_market_open(self, ist: datetime) -> datetime | None:
        candidate = ist.replace(hour=TRADING_START_HOUR, minute=TRADING_START_MIN, second=0, microsecond=0)
        if ist > candidate:
            candidate += timedelta(days=1)

        for _ in range(14):
            if candidate.weekday() < 5 and not self._is_holiday(candidate):
                return candidate
            candidate += timedelta(days=1)
        return None

    def _next_holiday_date(self, ist: datetime) -> str:
        for h in self._holidays:
            try:
                h_date = datetime.strptime(h, "%Y-%m-%d").replace(tzinfo=UTC)
                h_date_ist = h_date + timedelta(hours=5, minutes=30)
                if h_date_ist > ist:
                    return h
            except Exception:
                continue
        return ""

    async def sync_holidays(self) -> int:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    "https://www.nseindia.com/api/holiday-master?type=trading",
                    headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    holidays = []
                    for entry in data:
                        if isinstance(entry, dict):
                            holiday_date = entry.get("tradingDate") or entry.get("date", "")
                            if holiday_date:
                                holidays.append(holiday_date)
                    self._holidays = holidays
                    self._last_holiday_sync = datetime.now(UTC)
                    logger.info("Synced %d NSE holidays", len(holidays))
                    return len(holidays)
        except Exception as e:
            logger.warning("Failed to sync NSE holidays: %s", e)
        return 0


market_status_service = MarketStatusService()
