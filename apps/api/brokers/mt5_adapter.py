"""MT5 broker adapter — connect-flow scaffold for MT5-based forex/CFD brokers.

MT5 (MetaTrader 5) is the protocol used by XM, Exness, FBS, HF Markets, FXTM,
RoboForex, LiteFinance, and many other forex/CFD brokers. This adapter provides
the scaffold: credential storage + typed unsupported surface. Real MT5 trading
requires either the official MetaTrader5 Python package (Windows-only) or a
cross-platform MT5 gateway — both are certification-gated.

Honesty contract:
- Credentials CAN be saved/activated through the normal /brokers connect flow
- Every trading/data method raises UnsupportedFeatureError — never fabricated data
- Activating live trading later = implementing against real MT5 endpoints +
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
    "MT5 (MetaTrader 5) is the protocol used by XM, Exness, FBS, HF Markets, "
    "FXTM, RoboForex, LiteFinance, and many other forex/CFD brokers. This adapter "
    "provides credential storage only — live trading activates when a cross-platform "
    "MT5 integration is certified. Track https://www.mql5.com for MT5 API availability."
)

# Per-broker MT5 server config (scaffold — fill when you have real accounts)
#
# **Keys must match the `value` slugs in `registry.py`'s MT5 metadata exactly, case
# included.** They are looked up with `_MT5_BROKER_CONFIG.get(broker_key, {})`, so a
# mismatch does not raise — it returns `{}` and every field silently falls back to its
# generic default. This dict already had `"fxTM"` where the registry says `"fxtm"`, so
# FXTM resolved to nothing at all. `test_broker_mt5_config.py` now asserts the two agree.
#
# **Read this before assuming a field is live.** The only field anything reads is
# `mt5_server` (in `__init__`), and `mt5_server` is a *required* credential — `authenticate`
# rejects a payload without it and then overwrites the default with the user's value. So in
# practice this dict contributes nothing to a live session: `display_name` and `description`
# are read by nobody, and the server default is always replaced. It is kept as scaffolding
# for the MT5 certification work, and the fields are here so that work has a starting shape.
# Do not treat `display_name` as something the frontend already shows — it is not.
_MT5_BROKER_CONFIG: dict[str, dict] = {
    "xm": {
        "display_name": "XM",
        "mt5_server": "XM Server",  # placeholder — real server name from XM account
        "description": "Forex/CFD broker via MT5 protocol",
    },
    "exness": {
        "display_name": "Exness",
        "mt5_server": "Exness Server",
        "description": "Forex/CFD broker via MT5 protocol",
    },
    "fbs": {
        "display_name": "FBS",
        "mt5_server": "FBS Server",
        "description": "Forex/CFD broker via MT5 protocol",
    },
    "hfmarkets": {
        "display_name": "HF Markets",
        "mt5_server": "HFM Server",
        "description": "Forex/CFD broker via MT5 protocol",
    },
    "ifx": {
        "display_name": "IBFX",
        "mt5_server": "IBFX Server",
        "description": "Forex/CFD broker via MT5 protocol",
    },
    "fxtm": {  # was "fxTM" — never matched the registry's "fxtm"
        "display_name": "FXTM",
        "mt5_server": "FXTM Server",
        "description": "Forex/CFD broker via MT5 protocol",
    },
    "roboforex": {
        "display_name": "RoboForex",
        "mt5_server": "RoboForex Server",
        "description": "Forex/CFD broker via MT5 protocol",
    },
    "litefinance": {
        "display_name": "LiteFinance",
        "mt5_server": "LiteFinance Server",
        "description": "Forex/CFD broker via MT5 protocol",
    },
}


class MT5Adapter(BaseBroker, BrokerAdapterBase):
    """MT5 scaffold — stores nothing itself (repo owns encrypted storage);
    every runtime capability is a typed UnsupportedFeatureError until the MT5
    integration is certified."""

    broker_name = "mt5"

    def __init__(self, broker_key: str = "mt5"):
        self._authenticated = False
        self._broker_key = broker_key
        self._config = _MT5_BROKER_CONFIG.get(broker_key, {})
        self._mt5_server = self._config.get("mt5_server", "MT5 Server")
        self._login: str = ""
        self._password: str = ""

    async def _unsupported(self, feature: str):
        raise UnsupportedFeatureError(
            feature,
            broker=self._broker_key,
            detail=_PENDING_API_DETAIL,
        )

    # ── lifecycle ───────────────────────────────────────────────────

    async def authenticate(self, credentials: dict) -> Session:
        missing = [k for k in ("mt5_server", "login", "password") if not (credentials.get(k) or "").strip()]
        if missing:
            raise ValueError(f"MT5 requires {', '.join(missing)} (missing: {', '.join(missing)})")
        self._mt5_server = credentials.get("mt5_server", self._mt5_server)
        self._login = credentials["login"]
        self._password = credentials["password"]
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
