"""Delta Exchange broker adapter — connect-flow scaffold for crypto derivatives.

Delta Exchange (delta.exchange) is a crypto derivatives exchange offering futures
and perpetual contracts on Bitcoin, Ethereum, and altcoins. This adapter provides
the scaffold: credential storage + typed unsupported surface. Real Delta trading
requires implementing against their REST API — certification-gated.

Honesty contract:
- Credentials CAN be saved/activated through the normal /brokers connect flow
- Every trading/data method raises UnsupportedFeatureError — never fabricated data
- Activating live trading later = implementing against real Delta endpoints +
  flipping the capability row in brokers/sdk/capabilities.py
"""

import logging

from brokers.base import BaseBroker
from brokers.sdk.errors import UnsupportedFeatureError
from brokers.sdk.interface import BrokerAdapterBase
from core.models import (
    Candle,
    Funds,
    Holding,
    NormalizedOrder,
    OrderResult,
    Position,
    Quote,
    Session,
)

logger = logging.getLogger(__name__)

_PENDING_API_DETAIL = (
    "Delta Exchange (delta.exchange) offers crypto derivatives (futures, perpetuals) "
    "via a public REST API. This adapter provides credential storage only — live "
    "trading activates when the Delta Exchange integration is certified."
)

_REQUIRED_CREDENTIALS = ("api_key", "secret_key")


class DeltaExchangeAdapter(BaseBroker, BrokerAdapterBase):
    """Delta Exchange scaffold — stores nothing itself (repo owns encrypted storage);
    every runtime capability is a typed UnsupportedFeatureError until the Delta
    integration is certified."""

    broker_name = "delta"

    def __init__(self):
        self._authenticated = False
        self._api_key: str = ""
        self._secret_key: str = ""
        self._base_url = "https://testnet-delta.exchange"  # testnet by default

    async def _unsupported(self, feature: str):
        raise UnsupportedFeatureError(
            feature,
            broker=self.broker_name,
            detail=_PENDING_API_DETAIL,
        )

    # ── lifecycle ───────────────────────────────────────────────────

    async def authenticate(self, credentials: dict) -> Session:
        missing = [k for k in _REQUIRED_CREDENTIALS if not (credentials.get(k) or "").strip()]
        if missing:
            raise ValueError(f"Delta Exchange requires {', '.join(missing)} (missing: {', '.join(missing)})")
        self._api_key = credentials["api_key"]
        self._secret_key = credentials["secret_key"]
        env = credentials.get("environment", "testnet")
        self._base_url = "https://api.delta.exchange" if env == "production" else "https://testnet-delta.exchange"
        await self._unsupported("authenticate")

    async def disconnect(self) -> None:
        self._authenticated = False

    # ── orders ──────────────────────────────────────────────────────

    async def place_order(self, order: NormalizedOrder) -> OrderResult:
        await self._unsupported("place_order")

    async def modify_order(self, order_id: str, changes: dict) -> OrderResult:
        await self._unsupported("modify_order")

    async def cancel_order(self, order_id: str) -> OrderResult:
        await self._unsupported("cancel_order")

    async def get_orderbook(self) -> list[NormalizedOrder]:
        await self._unsupported("get_orderbook")

    # ── account ─────────────────────────────────────────────────────

    async def get_positions(self) -> list[Position]:
        await self._unsupported("get_positions")

    async def get_holdings(self) -> list[Holding]:
        await self._unsupported("get_holdings")

    async def get_funds(self) -> Funds:
        await self._unsupported("get_funds")

    # ── market data ─────────────────────────────────────────────────

    async def get_quotes(self, symbols: list[str]) -> list[Quote]:
        await self._unsupported("get_quotes")

    async def get_historical(self, symbol: str, interval: str, start=None, end=None, range=None) -> list[Candle]:
        await self._unsupported("get_historical")

    async def stream(self, symbols: list[str], on_tick) -> None:
        await self._unsupported("stream")
