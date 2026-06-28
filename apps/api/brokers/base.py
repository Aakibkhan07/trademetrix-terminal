from abc import ABC, abstractmethod
from typing import Callable, List

from core.models import (
    NormalizedOrder,
    OrderResult,
    Position,
    Holding,
    Funds,
    Quote,
    Candle,
    Tick,
    Session,
)


class BaseBroker(ABC):
    broker_name: str = ""

    @abstractmethod
    async def authenticate(self, credentials: dict) -> Session:
        ...

    @abstractmethod
    async def place_order(self, order: NormalizedOrder) -> OrderResult:
        ...

    @abstractmethod
    async def modify_order(self, order_id: str, changes: dict) -> OrderResult:
        ...

    @abstractmethod
    async def cancel_order(self, order_id: str) -> OrderResult:
        ...

    @abstractmethod
    async def get_orderbook(self) -> List[NormalizedOrder]:
        ...

    @abstractmethod
    async def get_positions(self) -> List[Position]:
        ...

    @abstractmethod
    async def get_holdings(self) -> List[Holding]:
        ...

    @abstractmethod
    async def get_funds(self) -> Funds:
        ...

    @abstractmethod
    async def get_quotes(self, symbols: List[str]) -> List[Quote]:
        ...

    @abstractmethod
    async def get_historical(self, symbol: str, interval: str, start: str | None = None, end: str | None = None, range: str | None = None) -> List[Candle]:
        ...

    @abstractmethod
    async def stream(self, symbols: List[str], on_tick: Callable[[Tick], None]) -> None:
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        ...
