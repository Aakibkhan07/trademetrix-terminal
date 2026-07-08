from collections import deque
from datetime import datetime
from typing import TypedDict

from pydantic import BaseModel, Field

from core.models import Exchange, InstrumentType, OptionType, Tick


class NormalizedTick(Tick):
    last_quantity: int = 0
    oi_change: int = 0
    iv: float = 0.0
    source: str = "live"


class TickBuffer:
    def __init__(self, maxlen: int = 1000):
        self._ticks: deque = deque(maxlen=maxlen)

    def append(self, tick: NormalizedTick) -> None:
        self._ticks.append(tick)

    def flush(self) -> list[NormalizedTick]:
        result = list(self._ticks)
        self._ticks.clear()
        return result

    def __len__(self) -> int:
        return len(self._ticks)

    def clear(self) -> None:
        self._ticks.clear()


class SubscriptionKey(TypedDict, total=False):
    symbol: str
    exchange: str
    instrument_type: str


class OptionChainEntry(BaseModel):
    strike: float
    option_type: OptionType
    last_price: float = 0.0
    bid: float = 0.0
    ask: float = 0.0
    volume: int = 0
    oi: int = 0
    oi_change: int = 0
    iv: float = 0.0
    expiry: str = ""
    underlying: str = ""
    change: float = 0.0
    change_pct: float = 0.0
    synthetic: bool = False


class MarketStatus(BaseModel):
    is_open: bool = False
    open_time: str = ""
    close_time: str = ""
    next_open: str = ""
    next_holiday: str = ""
    last_check: datetime = Field(default_factory=datetime.utcnow)
