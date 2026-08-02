"""BrokerPort (v2 interface) + BrokerAdapterBase (backward-compatible adapter).

BrokerPort is the canonical interface every broker adapter exposes — the engine, OMS,
strategies, UI and backtest talk to it and never to broker-specific code.

BrokerAdapterBase implements the v2 surface on top of the legacy BaseBroker methods
(get_orders → get_orderbook, get_historical_data → get_historical,
subscribe_market_data → stream, …). Any v2 method without a legacy counterpart
(get_profile, refresh_token, get_option_chain, exit_position, …) raises the typed
UnsupportedFeatureError instead of failing unpredictably — until the adapter overrides it.

The trading engine therefore never needs to know which broker is connected:
broker.place_order(...) works identically for every registered broker.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

from brokers.sdk.capabilities import BrokerCapabilities, CapabilityFlag
from brokers.sdk.errors import UnsupportedFeatureError
from core.models import Candle, Funds, Holding, NormalizedOrder, OrderResult, Position, Quote, Session, Tick


@runtime_checkable
class BrokerPort(Protocol):
    """The unified broker interface (v2). Every broker implements all methods."""

    broker_name: str

    # lifecycle
    async def connect(self, credentials: dict) -> Session: ...
    async def disconnect(self) -> None: ...
    async def refresh_token(self, credentials: dict) -> Session: ...

    # account
    async def get_profile(self) -> dict: ...
    async def get_funds(self) -> Funds: ...
    async def get_holdings(self) -> list[Holding]: ...
    async def get_positions(self) -> list[Position]: ...

    # orders
    async def get_orders(self) -> list[NormalizedOrder]: ...
    async def place_order(self, order: NormalizedOrder) -> OrderResult: ...
    async def modify_order(self, order_id: str, changes: dict) -> OrderResult: ...
    async def cancel_order(self, order_id: str) -> OrderResult: ...
    async def exit_position(self, symbol: str, quantity: int) -> OrderResult: ...

    # market data
    async def get_quotes(self, symbols: list[str]) -> list[Quote]: ...
    async def get_option_chain(self, symbol: str, expiry: str | None = None) -> dict: ...
    async def get_historical_data(
        self,
        symbol: str,
        interval: str,
        start: str | None = None,
        end: str | None = None,
        range: str | None = None,
    ) -> list[Candle]: ...
    async def subscribe_market_data(self, symbols: list[str], on_tick: Callable[[Tick], None]) -> None: ...
    async def unsubscribe_market_data(self, symbols: list[str] | None = None) -> None: ...

    # introspection
    async def health(self) -> dict: ...
    def capabilities(self) -> BrokerCapabilities: ...


class BrokerAdapterBase:
    """Mixin giving legacy BaseBroker adapters the v2 BrokerPort surface.

    Legacy adapters already implement: authenticate, place_order, modify_order,
    cancel_order, get_orderbook, get_positions, get_holdings, get_funds, get_quotes,
    get_historical, stream, unsubscribe_symbols, disconnect.

    This mixin bridges the v2 names onto those. v2 methods with no legacy counterpart
    (get_profile, refresh_token, get_option_chain, exit_position) raise the typed
    UnsupportedFeatureError until the adapter overrides them.

    Include as: `class FyersAdapter(BaseBroker, BrokerAdapterBase)` — order matters:
    BrokerAdapterBase must be last so BaseBroker abstract requirements win, and the
    concrete adapter class wins for same-name methods.
    """

    broker_name: str = ""

    @property
    def _capabilities(self) -> BrokerCapabilities:
        from brokers.sdk.registry import registry

        return registry.capabilities(self.broker_name)

    # ── lifecycle ───────────────────────────────────────────────────

    async def connect(self, credentials: dict) -> Session:
        """Default: legacy authenticate()."""

        return await self.authenticate(credentials)

    async def refresh_token(self, credentials: dict) -> Session:
        raise UnsupportedFeatureError("refresh_token", broker=self.broker_name)

    # ── account ─────────────────────────────────────────────────────

    async def get_profile(self) -> dict:
        raise UnsupportedFeatureError("get_profile", broker=self.broker_name)

    # ── orders ──────────────────────────────────────────────────────

    async def get_orders(self) -> list[NormalizedOrder]:
        return await self.get_orderbook()

    async def exit_position(self, symbol: str, quantity: int) -> OrderResult:
        raise UnsupportedFeatureError("exit_position", broker=self.broker_name)

    # ── market data ─────────────────────────────────────────────────

    async def get_option_chain(self, symbol: str, expiry: str | None = None) -> dict:
        raise UnsupportedFeatureError("get_option_chain", broker=self.broker_name)

    async def get_historical_data(
        self,
        symbol: str,
        interval: str,
        start: str | None = None,
        end: str | None = None,
        range: str | None = None,
    ) -> list[Candle]:
        return await self.get_historical(symbol, interval, start, end, range)

    async def subscribe_market_data(self, symbols: list[str], on_tick: Callable[[Tick], None]) -> None:
        await self.stream(symbols, on_tick)

    async def unsubscribe_market_data(self, symbols: list[str] | None = None) -> None:
        unsub = getattr(self, "unsubscribe_symbols", None)
        if unsub is None:
            raise UnsupportedFeatureError("unsubscribe_market_data", broker=self.broker_name)
        unsub(symbols)

    # ── introspection ───────────────────────────────────────────────

    async def health(self) -> dict:
        return {
            "broker": self.broker_name,
            "connected": bool(getattr(self, "_authenticated", False)),
        }

    def capabilities(self) -> BrokerCapabilities:
        return self._capabilities

    def require(self, capability: CapabilityFlag | str) -> None:
        """Gate a call on a capability; raises UnsupportedFeatureError when missing."""

        self._capabilities.require(capability)


__all__ = ["BrokerPort", "BrokerAdapterBase", "CapabilityFlag"]
