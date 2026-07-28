import asyncio
import logging
import time
from typing import Any

from brokers.base import BaseBroker
from core.models import Candle, Funds, Holding, NormalizedOrder, OrderResult, Position, Quote, Session, Tick
from core.resilience import CircuitBreaker, _get_breaker

logger = logging.getLogger(__name__)


class CircuitBreakerBroker(BaseBroker):
    def __init__(self, inner: BaseBroker, breaker_name: str | None = None):
        self._inner = inner
        self._inner_broker_name = inner.broker_name
        self._breaker_name = breaker_name or f"broker_{self._inner_broker_name}"
        self._breaker = _get_breaker(self._breaker_name)

    @property
    def broker_name(self) -> str:
        return self._inner_broker_name

    async def _call(self, fn, *args, fallback=None, **kwargs):
        return await self._breaker.call(fn, *args, fallback=fallback, **kwargs)

    async def authenticate(self, credentials: dict) -> Session:
        return await self._breaker.call(self._inner.authenticate, credentials)

    async def place_order(self, order: NormalizedOrder) -> OrderResult:
        return await self._breaker.call(self._inner.place_order, order)

    async def modify_order(self, order_id: str, changes: dict) -> OrderResult:
        return await self._breaker.call(self._inner.modify_order, order_id, changes)

    async def cancel_order(self, order_id: str) -> OrderResult:
        return await self._breaker.call(self._inner.cancel_order, order_id)

    async def get_orderbook(self) -> list[NormalizedOrder]:
        return await self._breaker.call(self._inner.get_orderbook, fallback=[])

    async def get_positions(self) -> list[Position]:
        return await self._breaker.call(self._inner.get_positions, fallback=[])

    async def get_holdings(self) -> list[Holding]:
        return await self._breaker.call(self._inner.get_holdings, fallback=[])

    async def get_funds(self) -> Funds:
        from core.models import Funds as FundsModel
        return await self._breaker.call(self._inner.get_funds, fallback=FundsModel(broker=self.broker_name))

    async def get_quotes(self, symbols: list[str]) -> list[Quote]:
        return await self._breaker.call(self._inner.get_quotes, symbols, fallback=[])

    async def get_historical(self, symbol: str, interval: str, start: str | None = None, end: str | None = None, range: str | None = None) -> list[Candle]:
        return await self._breaker.call(self._inner.get_historical, symbol, interval, start, end, range, fallback=[])

    async def stream(self, symbols: list[str], on_tick, **kwargs) -> None:
        return await self._breaker.call(self._inner.stream, symbols, on_tick, **kwargs)

    async def disconnect(self) -> None:
        try:
            await self._breaker.call(self._inner.disconnect)
        except Exception as e:
            logger.warning("CircuitBreakerBroker[%s] disconnect error: %s", self._breaker_name, e)

    async def get_margin_estimate(self, legs: list[dict]) -> dict:
        return await self._breaker.call(self._inner.get_margin_estimate, legs, fallback={"supported": False, "broker": self.broker_name})
