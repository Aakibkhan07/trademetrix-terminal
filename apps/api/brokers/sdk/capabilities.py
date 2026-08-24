"""Broker capability system.

Single source of truth for what every broker supports. The SDK's BrokerCapabilities
keeps the legacy boolean surface (supports_orders, supports_bracket, …) so existing
consumers (execution layer, paper broker, backtest broker) work unchanged, while adding:

- a canonical Capability enum for capability discovery,
- typed gates: `capabilities.supports(Capability.X)` and
- `capabilities.require(Capability.X)` raising UnsupportedFeatureError.

The matrix here is derived from the production-proven static table that lived in
execution/broker_adapter.py (plus Fyers verification). Change a cell only with
certification evidence.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Iterable, TypeAlias

from brokers.sdk.errors import UnsupportedFeatureError

Capability: TypeAlias = "CapabilityFlag"


class CapabilityFlag(StrEnum):
    ORDERS = "orders"
    ORDER_MODIFICATION = "order_modification"
    ORDER_CANCELLATION = "order_cancellation"
    BRACKET_ORDERS = "bracket_orders"
    COVER_ORDERS = "cover_orders"
    GTT = "gtt"
    MULTI_LEG_ORDERS = "multi_leg_orders"
    OPTION_CHAIN = "option_chain"
    HISTORICAL_DATA = "historical_data"
    WEBSOCKET = "websocket"
    MARKET_DEPTH = "market_depth"
    GREEKS = "greeks"
    INDICES = "indices"
    CURRENCY = "currency"
    COMMODITY = "commodity"
    MARGIN_CALCULATOR = "margin_calculator"
    QUOTES = "quotes"
    POSITIONS = "positions"
    HOLDINGS = "holdings"
    MARKET_DATA_STREAMING = "market_data_streaming"


# Maps the legacy boolean field names to their canonical capability.
_LEGACY_TO_CAPABILITY: dict[str, CapabilityFlag] = {
    "supports_orders": CapabilityFlag.ORDERS,
    "supports_modify": CapabilityFlag.ORDER_MODIFICATION,
    "supports_cancel": CapabilityFlag.ORDER_CANCELLATION,
    "supports_bracket": CapabilityFlag.BRACKET_ORDERS,
    "supports_cover": CapabilityFlag.COVER_ORDERS,
    "supports_gtt": CapabilityFlag.GTT,
    "supports_websocket": CapabilityFlag.WEBSOCKET,
    "supports_option_chain": CapabilityFlag.OPTION_CHAIN,
    "supports_positions": CapabilityFlag.POSITIONS,
    "supports_holdings": CapabilityFlag.HOLDINGS,
}


class BrokerCapabilities:
    """Immutable capability set for one broker.

    Usage:
        caps = registry.capabilities("fyers")
        if caps.supports(Capability.OPTION_CHAIN): ...
        caps.require(Capability.OPTION_CHAIN)  # raises UnsupportedFeatureError
    """

    __slots__ = ("broker", "_caps")

    def __init__(self, broker: str, capabilities: Iterable[CapabilityFlag | str] | None = None) -> None:
        self.broker = broker
        self._caps: frozenset[CapabilityFlag] = frozenset(
            CapabilityFlag(c) if isinstance(c, str) else c for c in (capabilities or ())
        )

    # ── canonical API ──────────────────────────────────────────────

    def supports(self, capability: CapabilityFlag | str) -> bool:
        return CapabilityFlag(capability) in self._caps

    def require(self, capability: CapabilityFlag | str, *, detail: str = "") -> None:
        if not self.supports(capability):
            raise UnsupportedFeatureError(
                CapabilityFlag(capability).value,
                broker=self.broker,
                detail=detail or f"Capability not declared for broker {self.broker}",
            )

    def __contains__(self, capability: CapabilityFlag | str) -> bool:
        return self.supports(capability)

    @property
    def capabilities(self) -> set[str]:
        return {c.value for c in self._caps}

    # ── legacy boolean surface (backward compatible) ───────────────

    @property
    def supports_orders(self) -> bool:
        return self.supports(CapabilityFlag.ORDERS)

    @property
    def supports_modify(self) -> bool:
        return self.supports(CapabilityFlag.ORDER_MODIFICATION)

    @property
    def supports_cancel(self) -> bool:
        return self.supports(CapabilityFlag.ORDER_CANCELLATION)

    @property
    def supports_bracket(self) -> bool:
        return self.supports(CapabilityFlag.BRACKET_ORDERS)

    @property
    def supports_cover(self) -> bool:
        return self.supports(CapabilityFlag.COVER_ORDERS)

    @property
    def supports_gtt(self) -> bool:
        return self.supports(CapabilityFlag.GTT)

    @property
    def supports_websocket(self) -> bool:
        return self.supports(CapabilityFlag.WEBSOCKET)

    @property
    def supports_option_chain(self) -> bool:
        return self.supports(CapabilityFlag.OPTION_CHAIN)

    @property
    def supports_positions(self) -> bool:
        return self.supports(CapabilityFlag.POSITIONS)

    @property
    def supports_holdings(self) -> bool:
        return self.supports(CapabilityFlag.HOLDINGS)

    @property
    def supports_historical(self) -> bool:
        return self.supports(CapabilityFlag.HISTORICAL_DATA)

    @property
    def supports_margin_calculator(self) -> bool:
        return self.supports(CapabilityFlag.MARGIN_CALCULATOR)

    # ── misc ────────────────────────────────────────────────────────

    def as_legacy_dict(self) -> dict[str, bool]:
        return {legacy: self.supports(cap) for legacy, cap in _LEGACY_TO_CAPABILITY.items()}

    def to_dict(self) -> dict[str, Any]:
        return {"broker": self.broker, "capabilities": sorted(self.capabilities)}

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"BrokerCapabilities(broker={self.broker!r}, capabilities={sorted(self.capabilities)!r})"


def capabilities_from_bools(broker: str, bools: dict[str, bool]) -> BrokerCapabilities:
    """Build a capability set from legacy {field: bool} config (used by tests/paper/backtest)."""

    flags: list[CapabilityFlag] = []
    for field, enabled in bools.items():
        capability = _LEGACY_TO_CAPABILITY.get(field)
        if capability and enabled:
            flags.append(capability)
    return BrokerCapabilities(broker=broker, capabilities=flags)


_COMMON = {
    CapabilityFlag.ORDERS,
    CapabilityFlag.ORDER_MODIFICATION,
    CapabilityFlag.ORDER_CANCELLATION,
    CapabilityFlag.HISTORICAL_DATA,
    CapabilityFlag.QUOTES,
    CapabilityFlag.POSITIONS,
    CapabilityFlag.HOLDINGS,
    CapabilityFlag.INDICES,
}

# Authoritative per-broker matrix (see docs/evolution/BROKER_SDK_V2.md §4).
BROKER_CAPABILITY_MATRIX: dict[str, set[CapabilityFlag]] = {
    "fyers": _COMMON
    | {
        CapabilityFlag.BRACKET_ORDERS,
        CapabilityFlag.OPTION_CHAIN,
        CapabilityFlag.WEBSOCKET,
        CapabilityFlag.CURRENCY,
        CapabilityFlag.MARGIN_CALCULATOR,
        CapabilityFlag.MARKET_DATA_STREAMING,
    },
    "angelone": _COMMON
    | {
        CapabilityFlag.BRACKET_ORDERS,
        CapabilityFlag.COVER_ORDERS,
        CapabilityFlag.GTT,
        CapabilityFlag.MULTI_LEG_ORDERS,
        CapabilityFlag.WEBSOCKET,
        CapabilityFlag.MARKET_DEPTH,
        CapabilityFlag.MARKET_DATA_STREAMING,
    },
    "dhan": _COMMON
    | {
        CapabilityFlag.GTT,
        CapabilityFlag.WEBSOCKET,
        CapabilityFlag.MARKET_DEPTH,
        CapabilityFlag.MARKET_DATA_STREAMING,
    },
    "zerodha": _COMMON
    | {
        CapabilityFlag.BRACKET_ORDERS,
        CapabilityFlag.COVER_ORDERS,
        CapabilityFlag.GTT,
    },
    "upstox": _COMMON
    | {
        CapabilityFlag.BRACKET_ORDERS,
        CapabilityFlag.COVER_ORDERS,
        CapabilityFlag.GTT,
        CapabilityFlag.WEBSOCKET,
        CapabilityFlag.MARKET_DEPTH,
        CapabilityFlag.MARKET_DATA_STREAMING,
    },
    "aliceblue": _COMMON
    | {
        CapabilityFlag.WEBSOCKET,
        CapabilityFlag.MARKET_DATA_STREAMING,
    },
    "finvasia": _COMMON
    | {
        CapabilityFlag.WEBSOCKET,
        CapabilityFlag.MARKET_DATA_STREAMING,
    },
    "flattrade": _COMMON
    | {
        CapabilityFlag.WEBSOCKET,
        CapabilityFlag.MARKET_DATA_STREAMING,
    },
    "fivepaisa": _COMMON,
    "kotakneo": _COMMON
    | {
        CapabilityFlag.BRACKET_ORDERS,
        CapabilityFlag.GTT,
        CapabilityFlag.WEBSOCKET,
        CapabilityFlag.MARKET_DATA_STREAMING,
    },
    "groww": _COMMON | {CapabilityFlag.WEBSOCKET, CapabilityFlag.MARKET_DATA_STREAMING},
    # Lemonn: EMPTY set — no public API exists yet (see brokers/lemonn_adapter.py).
    # Every capability-gated call raises UnsupportedFeatureError until real
    # endpoints ship; flip flags there + here together when activating live.
    "lemonn": set(),
    "paper": _COMMON
    | {
        CapabilityFlag.WEBSOCKET,
        CapabilityFlag.MARKET_DATA_STREAMING,
        CapabilityFlag.OPTION_CHAIN,
        CapabilityFlag.MARGIN_CALCULATOR,
        CapabilityFlag.GREEKS,
    },
}


def get_capabilities(broker: str) -> BrokerCapabilities:
    """Return the capability set for a broker (empty set for unknown brokers, never raises)."""

    return BrokerCapabilities(
        broker=broker,
        capabilities=BROKER_CAPABILITY_MATRIX.get(broker, set()),
    )
