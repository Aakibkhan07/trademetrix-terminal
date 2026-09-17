"""Binance broker adapter — connect-flow scaffold (credential storage + typed unsupported surface).

Honesty contract: Binance (binance.com) publishes a public REST API but this platform
is India-focused; crypto integrations require separate auth flows and market-coverage
review. This adapter therefore implements the FULL broker surface as typed failures:

- Credentials CAN be saved/activated through the normal /brokers connect flow
  (registry metadata + encrypted storage) so users are ready the day an API ships.
- Every trading/data method raises UnsupportedFeatureError — never a network error,
  never fabricated data.

Activating live trading later = implementing the methods against real endpoints +
flipping the capability row in brokers/sdk/capabilities.py.
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
    "Binance (binance.com) has a public REST API but is not activated in this "
    "India-focused platform. Credentials are stored via the connect flow but live "
    "calls stay disabled until a crypto integration is certified. "
    "Track https://binance.com for API availability."
)

_REQUIRED_CREDENTIALS = ("api_key", "secret_key")


class BinanceAdapter(BaseBroker, BrokerAdapterBase):
    """Binance scaffold — stores nothing itself (repo owns encrypted storage);
    every runtime capability is a typed UnsupportedFeatureError until the crypto
    integration is certified."""

    broker_name = "binance"

    def __init__(self):
        self._authenticated = False

    async def _unsupported(self, feature: str):
        raise UnsupportedFeatureError(feature, broker=self.broker_name, detail=_PENDING_API_DETAIL)

    # ── lifecycle ───────────────────────────────────────────────────

    async def authenticate(self, credentials: dict) -> Session:
        missing = [k for k in _REQUIRED_CREDENTIALS if not (credentials.get(k) or "").strip()]
        if missing:
            raise ValueError(f"Binance requires {', '.join(_REQUIRED_CREDENTIALS)} (missing: {', '.join(missing)})")
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
