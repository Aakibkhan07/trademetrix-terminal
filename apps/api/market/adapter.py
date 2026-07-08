import logging
from typing import Any, Optional

from brokers.base import BaseBroker
from core.models import Candle, Quote

logger = logging.getLogger(__name__)


class MarketDataAdapter:
    def __init__(self, broker_adapter: BaseBroker, broker_type: str):
        self._adapter = broker_adapter
        self._broker_type = broker_type
        self._authenticated = False

    @property
    def broker_type(self) -> str:
        return self._broker_type

    @property
    def is_authenticated(self) -> bool:
        return self._authenticated

    async def connect(self, config: dict) -> bool:
        try:
            session = await self._adapter.authenticate(config)
            self._authenticated = session.authenticated
            return self._authenticated
        except Exception as e:
            logger.error("Adapter connect failed for %s: %s", self._broker_type, e)
            return False

    async def disconnect(self) -> None:
        try:
            await self._adapter.disconnect()
        except Exception as e:
            logger.warning("Adapter disconnect error for %s: %s", self._broker_type, e)
        self._authenticated = False

    async def subscribe(self, symbols: list[str]) -> None:
        pass

    async def unsubscribe(self, symbols: list[str]) -> None:
        pass

    async def get_ltp(self, symbol: str) -> Optional[float]:
        quotes = await self._adapter.get_quotes([symbol])
        if quotes:
            return quotes[0].last_price
        return None

    async def get_quote(self, symbol: str) -> Quote | None:
        quotes = await self._adapter.get_quotes([symbol])
        return quotes[0] if quotes else None

    async def get_quotes(self, symbols: list[str]) -> list[Quote]:
        return await self._adapter.get_quotes(symbols)

    async def get_option_chain(self, symbol: str, expiry: str = "") -> dict | None:
        raise NotImplementedError(f"{self._broker_type} does not support get_option_chain")

    async def get_historical_data(
        self, symbol: str, interval: str, days: int, start: str | None = None, end: str | None = None
    ) -> list[Candle]:
        try:
            return await self._adapter.get_historical(symbol, interval, start, end)
        except Exception as e:
            logger.warning("Historical data error for %s/%s: %s", self._broker_type, symbol, e)
            return []

    async def get_market_status(self) -> dict:
        return {"broker": self._broker_type, "status": "unknown"}


class MarketDataAdapterRegistry:
    def __init__(self):
        self._adapters: dict[str, type[MarketDataAdapter]] = {}

    def register(self, broker_type: str, adapter_cls: type[MarketDataAdapter]) -> None:
        self._adapters[broker_type] = adapter_cls

    def get_adapter_class(self, broker_type: str) -> type[MarketDataAdapter] | None:
        return self._adapters.get(broker_type)

    def get_supported_brokers(self) -> list[str]:
        return list(self._adapters.keys())


_adapter_registry = MarketDataAdapterRegistry()


def register_market_data_adapter(broker_type: str, adapter_cls: type[MarketDataAdapter]) -> None:
    _adapter_registry.register(broker_type, adapter_cls)


def get_market_data_adapter(broker_type: str) -> type[MarketDataAdapter] | None:
    return _adapter_registry.get_adapter_class(broker_type)


def create_market_data_adapter(broker_type: str, broker_adapter: BaseBroker) -> MarketDataAdapter:
    cls = _adapter_registry.get_adapter_class(broker_type)
    if cls:
        return cls(broker_adapter, broker_type)
    return MarketDataAdapter(broker_adapter, broker_type)
