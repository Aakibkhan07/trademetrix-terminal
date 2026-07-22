from abc import ABC, abstractmethod
from collections.abc import Callable

import httpx

from core.config import settings
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
    _http_client: httpx.AsyncClient | None = None

    async def _get_http_client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(
                    settings.broker_request_timeout,
                    connect=settings.broker_connect_timeout,
                ),
                limits=httpx.Limits(
                    max_connections=20,
                    max_keepalive_connections=5,
                    keepalive_expiry=30.0,
                ),
            )
        return self._http_client

    async def close_http_client(self) -> None:
        if self._http_client:
            try:
                await self._http_client.aclose()
            except Exception:
                pass
            self._http_client = None

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

    def unsubscribe_symbols(self, symbols: list[str] | None = None) -> None:
        pass
