"""ICICI Direct broker adapter — credential-storage scaffold (no public API yet).

Honesty contract: ICICI Direct (icicidirect.com) does NOT publish a public
trading REST API — their algo trading offering is hosted only. This adapter
therefore implements the FULL broker surface as typed failures:

- Credentials CAN be saved/activated through the normal /brokers connect flow
  (registry metadata + encrypted storage) so users are ready the day an API ships.
- Every trading/data method raises UnsupportedFeatureError — never a network error,
  never silent fallback, never fabricated data.

Activating live trading later = implementing the methods against real endpoints +
flipping the capability row in brokers/sdk/capabilities.py (currently EMPTY set).
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
    "ICICI Direct (icicidirect.com) has no public trading API yet — credentials "
    "are stored via the connect flow but live calls stay disabled until ICICI Direct "
    "ships one. ICICI Direct's algo trading is hosted-only; track "
    "https://www.icicidirect.com for API availability."
)

_REQUIRED_CREDENTIALS = ("client_code", "secret_key")


class ICICIDirectAdapter(BaseBroker, BrokerAdapterBase):
    """ICICI Direct scaffold — stores nothing itself (repo owns encrypted storage);
    every runtime capability is a typed UnsupportedFeatureError until ICICI Direct
    publishes a public trading API."""

    broker_name = "icici"

    def __init__(self) -> None:
        self._authenticated = False

    async def _unsupported(self, feature: str) -> None:
        raise UnsupportedFeatureError(
            feature, broker=self.broker_name, detail=_PENDING_API_DETAIL
        )

    # ── lifecycle ───────────────────────────────────────────────────

    async def authenticate(self, credentials: dict) -> Session:
        missing = [
            k for k in _REQUIRED_CREDENTIALS if not (credentials.get(k) or "").strip()
        ]
        if missing:
            raise ValueError(
                f"ICICI Direct requires {', '.join(_REQUIRED_CREDENTIALS)} "
                f"(missing: {', '.join(missing)})"
            )
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

    async def get_historical(
        self, symbol: str, interval: str, start=None, end=None, range=None
    ) -> list[Candle]:
        await self._unsupported("get_historical")

    async def stream(self, symbols: list[str], on_tick) -> None:
        await self._unsupported("stream")
