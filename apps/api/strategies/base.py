from abc import ABC, abstractmethod

from pydantic import BaseModel

from core.models import Candle, NormalizedOrder, Tick


class SignalResult(BaseModel):
    orders: list[NormalizedOrder]
    reason: str = ""


class BaseStrategy(ABC):
    name: str = ""
    description: str = ""

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self._position: dict = {}

    @abstractmethod
    async def on_tick(self, tick: Tick) -> SignalResult | None:
        ...

    @abstractmethod
    async def on_candle(self, candle: Candle) -> SignalResult | None:
        ...

    @abstractmethod
    async def on_start(self) -> None:
        ...

    @abstractmethod
    async def on_stop(self) -> None:
        ...

    def update_position(self, symbol: str, quantity: int) -> None:
        self._position[symbol] = self._position.get(symbol, 0) + quantity
