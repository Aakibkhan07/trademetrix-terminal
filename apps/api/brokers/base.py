from abc import ABC, abstractmethod
from collections.abc import Callable

from core.models import (
    Candle,
    Funds,
    Holding,
    NormalizedOrder,
    OrderResult,
    Position,
    Quote,
    Session,
    Tick,
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
    async def get_orderbook(self) -> list[NormalizedOrder]:
        ...

    @abstractmethod
    async def get_positions(self) -> list[Position]:
        ...

    @abstractmethod
    async def get_holdings(self) -> list[Holding]:
        ...

    @abstractmethod
    async def get_funds(self) -> Funds:
        ...

    @abstractmethod
    async def get_quotes(self, symbols: list[str]) -> list[Quote]:
        ...

    @abstractmethod
    async def get_historical(self, symbol: str, interval: str, start: str | None = None, end: str | None = None, range: str | None = None) -> list[Candle]:
        ...

    @abstractmethod
    async def stream(self, symbols: list[str], on_tick: Callable[[Tick], None]) -> None:
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        ...

    async def get_margin_estimate(self, legs: list[dict]) -> dict:
        return {"supported": False, "broker": self.broker_name}
