"""
Kotak Neo execution adapter (real Trade API).

Implements the Kotak-Neo/Kotak-neo-api-v2 Trade API surface against the
*mnapi* / dynamic trading base url:

  * Session (login) is performed by the connect-layer connector
    (broker_connect/brokers/kotak_neo.py) which stores the resulting
    trade token (edit token), edit sid, server id and trading base url in
    `broker_credentials.additional_params`. This adapter reads them back
    (via TokenManager, which merges additional_params into the session).
  * Every trading call uses the dynamic `base_url` with `Sid` / `Auth`
    headers (edit_sid / edit_token) plus a `sId` query param (hsServerId).
  * Quotes use the consumer_key in the Authorization header.

Order placement / cancel / modify / orderbook / positions / holdings /
funds follow the verified SDK endpoint + field map. Market quotes /
historical / streaming are intentionally NOT implemented here yet — the
platform already falls back to Yahoo Finance for those, so leaving them
unsupported keeps Kotak from fabricating data it cannot produce without
the scrip-master instrument token map.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime

import httpx

from brokers.base import BaseBroker
from brokers.sdk.errors import UnsupportedFeatureError
from brokers.sdk.interface import BrokerAdapterBase
from core.config import settings
from core.http_client import get_http_client
from core.models import (
    Exchange,
    Funds,
    Holding,
    InstrumentType,
    NormalizedOrder,
    OptionType,
    OrderResult,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    ProductType,
    Quote,
    Session,
    Tick,
)

logger = logging.getLogger(__name__)

# From Kotak-neo-api-v2 urls / settings
PROD_BASE_URL = "https://mnapi.kotaksecurities.com"
NEO_FIN_KEY = "neotradeapi"  # neo_utility.NeoUtility.get_neo_fin_key() for prod

# Trading endpoint paths (settings.PROD_URL) appended to the dynamic base_url.
_PATH_PLACE = "quick/order/rule/ms/place"
_PATH_CANCEL = "quick/order/cancel"
_PATH_MODIFY = "quick/order/vr/modify"
_PATH_ORDER_BOOK = "orderapi/1.0/quick/user/orders"
_PATH_TRADE_REPORT = "orderapi/1.0/quick/user/trades"
_PATH_POSITIONS = "orderapi/1.0/quick/user/positions"
_PATH_HOLDINGS = "portfolio/1.0/portfolio/v1/holdings"
_PATH_LIMITS = "orderapi/1.0/quick/user/limits"
_PATH_QUOTES = "script-details/1.0/quotes/neosymbol"

# Our Exchange -> Kotak exchange_segment
_SEGMENTS = {
    ("NSE", False): "nse_cm",
    ("BSE", False): "bse_cm",
    ("NSE", True): "nse_fo",
    ("BSE", True): "bse_fo",
    ("MCX", True): "mcx_fo",
    ("CDS", True): "cde_fo",
}
_SEGMENT_TO_EXCHANGE = {
    "nse_cm": Exchange.NSE,
    "bse_cm": Exchange.BSE,
    "nse_fo": Exchange.NFO,
    "bse_fo": Exchange.NFO,
    "mcx_fo": Exchange.MCX,
    "cde_fo": Exchange.CDS,
}


def _to_float(value, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (ValueError, TypeError):
        return default


def _to_int(value, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except (ValueError, TypeError):
        return default


class KotakNeoAdapter(BaseBroker, BrokerAdapterBase):
    broker_name = "kotakneo"

    def __init__(self, user_id: str | None = None, broker: str = "kotakneo"):
        self.user_id = user_id
        self.broker = broker
        self._client: httpx.AsyncClient | None = None
        self._access_token: str = ""   # edit/trade token
        self._consumer_key: str = ""
        self._sid: str = ""            # edit sid
        self._server_id: str = ""      # hsServerId
        self._base_url = PROD_BASE_URL

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = await get_http_client()
        return self._client

    # ── auth ────────────────────────────────────────────────────────────
    async def authenticate(self, credentials: dict) -> Session:
        creds = credentials or {}
        access_token = creds.get("access_token")
        base_url = creds.get("base_url")
        sid = creds.get("sid")
        server_id = creds.get("serverId")
        consumer_key = (
            creds.get("api_key") or creds.get("consumer_key") or creds.get("client_id") or ""
        )

        # Defensive reload from the store when the slim session lacks the
        # dynamic routing fields (e.g. when authenticate is called directly).
        if not (access_token and base_url and sid and server_id) and self.user_id:
            try:
                from brokers.token_manager import TokenManager

                full = await TokenManager(self.user_id, self.broker)._load_credentials()
                access_token = access_token or full.get("access_token")
                base_url = base_url or full.get("base_url")
                sid = sid or full.get("sid")
                server_id = server_id or full.get("serverId")
                consumer_key = consumer_key or full.get("api_key") or full.get("consumer_key")
            except Exception as e:  # noqa: BLE001
                logger.warning("Kotak Neo credential reload failed: %s", e)

        self._access_token = access_token or ""
        self._consumer_key = consumer_key or ""
        self._sid = sid or ""
        self._server_id = server_id or ""
        self._base_url = base_url or PROD_BASE_URL
        self._authenticated = bool(self._access_token and self._sid and self._base_url)

        return Session(
            access_token=self._access_token,
            user_id=self.user_id or self._consumer_key,
            broker=self.broker_name,
            authenticated=self._authenticated,
        )

    def _trading_headers(self) -> dict:
        return {
            "Sid": self._sid,
            "Auth": self._access_token,
            "Content-Type": "application/x-www-form-urlencoded",
        }

    def _trading_url(self, path: str) -> str:
        base = self._base_url.rstrip("/")
        return f"{base}/{path}"

    # ── symbol helpers ──────────────────────────────────────────────────
    @staticmethod
    def _trading_symbol(symbol: str) -> str:
        return symbol.split(":", 1)[1] if ":" in symbol else symbol

    def _segment(self, order: NormalizedOrder) -> str:
        is_derivative = (
            order.instrument_type in (InstrumentType.OPT, InstrumentType.FUT)
            or order.option_type is not None
            or order.exchange in (Exchange.NFO, Exchange.MCX, Exchange.CDS)
        )
        return _SEGMENTS.get((order.exchange.value, is_derivative), "nse_cm")

    @staticmethod
    def _map_side(side: OrderSide) -> str:
        return "B" if side == OrderSide.BUY else "S"

    @staticmethod
    def _map_order_type(ot: OrderType) -> str:
        return {
            OrderType.MARKET: "MKT",
            OrderType.LIMIT: "L",
            OrderType.SL: "SL",
            OrderType.SLM: "SL-M",
        }.get(ot, "MKT")

    @staticmethod
    def _map_product(p: ProductType) -> str:
        return {
            ProductType.INTRADAY: "MIS",
            ProductType.MIS: "MIS",
            ProductType.DELIVERY: "CNC",
            ProductType.NRML: "NRML",
        }.get(p, "MIS")

    @staticmethod
    def _unmap_status(status: str) -> OrderStatus:
        s = (status or "").lower()
        mapping = {
            "pending": OrderStatus.PENDING,
            "trigger pending": OrderStatus.PENDING,
            "open": OrderStatus.OPEN,
            "complete": OrderStatus.FILLED,
            "traded": OrderStatus.FILLED,
            "filled": OrderStatus.FILLED,
            "partial": OrderStatus.PARTIALLY_FILLED,
            "cancelled": OrderStatus.CANCELLED,
            "rejected": OrderStatus.REJECTED,
            "expired": OrderStatus.EXPIRED,
        }
        return mapping.get(s, OrderStatus.PENDING)

    # ── orders ──────────────────────────────────────────────────────────
    async def place_order(self, order: NormalizedOrder) -> OrderResult:
        client = await self._get_client()
        body = {
            "es": self._segment(order),
            "pc": self._map_product(order.product),
            "pr": str(order.price or 0),
            "pt": self._map_order_type(order.order_type),
            "qt": str(order.quantity),
            "rt": order.validity or "DAY",
            "ts": self._trading_symbol(order.symbol),
            "tt": self._map_side(order.side),
            "tp": str(order.trigger_price or 0),
            "dq": str(order.disclosed_quantity or 0),
            "am": "N",
            "ig": order.reason or "",
        }
        resp = await client.post(
            self._trading_url(_PATH_PLACE),
            data=body,
            params={"sId": self._server_id},
            headers=self._trading_headers(),
            timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
        )
        data = resp.json()
        success = str(data.get("stat", "")).lower() in ("ok", "success")
        return OrderResult(
            success=success,
            broker_order_id=str(data.get("nOrdNo", "")),
            status=str(data.get("stat", "")),
            message=str(data.get("errMsg") or data.get("emsg") or ""),
            avg_price=0.0,
        )

    async def modify_order(self, order_id: str, changes: dict) -> OrderResult:
        client = await self._get_client()
        body = {
            "on": order_id,
            "pr": str(changes.get("price", 0)),
            "qt": str(changes.get("quantity", 0)),
            "tp": str(changes.get("trigger_price", 0)),
            "pt": self._map_order_type_str(changes.get("order_type", "MARKET")),
            "rt": changes.get("validity", "DAY"),
            "dq": str(changes.get("disclosed_quantity", 0)),
            "am": "N",
        }
        resp = await client.post(
            self._trading_url(_PATH_MODIFY),
            data=body,
            params={"sId": self._server_id},
            headers=self._trading_headers(),
            timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
        )
        data = resp.json()
        success = str(data.get("stat", "")).lower() in ("ok", "success")
        return OrderResult(
            success=success,
            broker_order_id=order_id,
            status=str(data.get("stat", "")),
            message=str(data.get("errMsg") or data.get("emsg") or ""),
        )

    async def cancel_order(self, order_id: str) -> OrderResult:
        client = await self._get_client()
        body = {"on": order_id, "am": "N"}
        resp = await client.post(
            self._trading_url(_PATH_CANCEL),
            data=body,
            params={"sId": self._server_id},
            headers=self._trading_headers(),
            timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
        )
        data = resp.json()
        success = str(data.get("stat", "")).lower() in ("ok", "success")
        return OrderResult(
            success=success,
            broker_order_id=order_id,
            status=str(data.get("stat", "")),
            message=str(data.get("errMsg") or data.get("emsg") or ""),
        )

    # ── reads ───────────────────────────────────────────────────────────
    async def get_orderbook(self) -> list[NormalizedOrder]:
        client = await self._get_client()
        resp = await client.get(
            self._trading_url(_PATH_ORDER_BOOK),
            params={"sId": self._server_id},
            headers=self._trading_headers(),
            timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
        )
        data = resp.json()
        items = data.get("data") or []
        if isinstance(items, dict):
            items = list(items.values())
        return [self._normalize_order(i) for i in items]

    async def get_positions(self) -> list[Position]:
        client = await self._get_client()
        resp = await client.get(
            self._trading_url(_PATH_POSITIONS),
            params={"sId": self._server_id},
            headers=self._trading_headers(),
            timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
        )
        data = resp.json()
        items = data.get("data") or []
        if isinstance(items, dict):
            items = list(items.values())
        return [self._normalize_position(i) for i in items]

    async def get_holdings(self) -> list[Holding]:
        client = await self._get_client()
        resp = await client.get(
            self._trading_url(_PATH_HOLDINGS),
            params={"sId": self._server_id},
            headers=self._trading_headers(),
            timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
        )
        data = resp.json()
        items = data.get("data") or []
        if isinstance(items, dict):
            items = list(items.values())
        return [self._normalize_holding(i) for i in items]

    async def get_funds(self) -> Funds:
        client = await self._get_client()
        try:
            resp = await client.post(
                self._trading_url(_PATH_LIMITS),
                data={"seg": "EQ", "exch": "NSE", "prod": "MIS"},
                params={"sId": self._server_id},
                headers=self._trading_headers(),
                timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
            )
            data = resp.json()
            rows = data.get("data") or []
            row = rows[0] if isinstance(rows, list) and rows else (rows if isinstance(rows, dict) else {})

            def pick(*keys: str) -> float:
                lowered = {str(k).lower(): v for k, v in (row or {}).items()}
                for k in keys:
                    if k.lower() in lowered and lowered[k.lower()] not in (None, ""):
                        return _to_float(lowered[k.lower()])
                return 0.0

            return Funds(
                total_margin=pick("TOTAL_MARGIN", "total_margin", "net_margin"),
                used_margin=pick("USED_MARGIN", "used_margin"),
                available_margin=pick("AVAILABLE_MARGIN", "available_margin", "cash"),
                broker=self.broker_name,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("Kotak Neo funds fetch failed: %s", e)
            return Funds(broker=self.broker_name)

    async def get_quotes(self, symbols: list[str]) -> list[Quote]:
        # The quotes endpoint requires instrument tokens (exchange_segment|
        # instrument_token), which need the scrip-master token map. That
        # integration is not wired yet, so we return nothing and let the
        # platform fall back to Yahoo Finance for pricing.
        logger.debug("Kotak Neo broker quotes not implemented; relying on fallback source")
        return []

    async def get_historical(
        self, symbol: str, interval: str, start: str | None = None, end: str | None = None, range: str | None = None
    ) -> list:
        raise UnsupportedFeatureError(
            "Kotak Neo historical candles require instrument-token resolution (scrip master) and are not wired yet.",
            broker=self.broker_name,
        )

    async def stream(self, symbols: list[str], on_tick: Callable[[Tick], None]) -> None:
        raise UnsupportedFeatureError(
            "Kotak Neo market streaming is not wired yet; the platform falls back to other data sources.",
            broker=self.broker_name,
        )

    async def disconnect(self) -> None:
        if self._client:
            try:
                await self._client.aclose()
            except Exception:
                pass
            self._client = None

    # ── normalizers ─────────────────────────────────────────────────────
    def _normalize_order(self, item: dict) -> NormalizedOrder:
        exch = _SEGMENT_TO_EXCHANGE.get(item.get("exSeg", ""), Exchange.NSE)
        sym = item.get("trdSym") or item.get("trading_symbol") or item.get("symbol") or ""
        return NormalizedOrder(
            id=str(item.get("nOrdNo", "")),
            broker_order_id=str(item.get("nOrdNo", "")),
            symbol=f"{exch.value}:{sym}",
            exchange=exch,
            side=OrderSide.BUY if str(item.get("tt", "")).upper() == "B" else OrderSide.SELL,
            order_type=self._unmap_order_type_str(item.get("optT") or item.get("ordTyp") or "L"),
            product=self._unmap_product(item.get("prd") or "MIS"),
            quantity=_to_int(item.get("qty")),
            price=_to_float(item.get("prc")),
            trigger_price=_to_float(item.get("trgPrc")) or None,
            status=self._unmap_status(item.get("ordSt") or item.get("status")),
            filled_quantity=_to_int(item.get("fillQty")),
            average_price=_to_float(item.get("avgPrc")),
            message=str(item.get("rejRsn") or ""),
            broker=self.broker_name,
        )

    def _normalize_position(self, item: dict) -> Position:
        exch = _SEGMENT_TO_EXCHANGE.get(item.get("exSeg", ""), Exchange.NSE)
        sym = item.get("trdSym") or item.get("trading_symbol") or item.get("symbol") or ""
        return Position(
            symbol=f"{exch.value}:{sym}",
            exchange=exch,
            quantity=_to_int(item.get("netQty")),
            buy_quantity=_to_int(item.get("buyQty")),
            sell_quantity=_to_int(item.get("sellQty")),
            average_buy_price=_to_float(item.get("buyAvg")),
            average_sell_price=_to_float(item.get("sellAvg")),
            unrealised_pnl=_to_float(item.get("upld") or item.get("pl")),
            realised_pnl=_to_float(item.get("rpl")),
            product=self._unmap_product(item.get("prd") or "MIS"),
            broker=self.broker_name,
        )

    def _normalize_holding(self, item: dict) -> Holding:
        exch = _SEGMENT_TO_EXCHANGE.get(item.get("exSeg", ""), Exchange.NSE)
        sym = item.get("trdSym") or item.get("trading_symbol") or item.get("symbol") or ""
        return Holding(
            symbol=f"{exch.value}:{sym}",
            exchange=exch,
            quantity=_to_int(item.get("netQty")),
            average_price=_to_float(item.get("avgCst")),
            current_price=_to_float(item.get("ltp")),
            pnl=_to_float(item.get("pl")),
            broker=self.broker_name,
        )

    # ── reverse mappers ─────────────────────────────────────────────────
    @staticmethod
    def _unmap_order_type_str(val: str):
        mapping = {"L": OrderType.LIMIT, "MKT": OrderType.MARKET, "SL": OrderType.SL, "SL-M": OrderType.SLM}
        return mapping.get(str(val).upper(), OrderType.MARKET)

    @staticmethod
    def _map_order_type_str(ot: str) -> str:
        mapping = {"MARKET": "MKT", "LIMIT": "L", "SL": "SL", "SLM": "SL-M"}
        return mapping.get(str(ot).upper(), "MKT")

    @staticmethod
    def _unmap_product(prod: str) -> ProductType:
        mapping = {"MIS": ProductType.MIS, "CNC": ProductType.DELIVERY, "NRML": ProductType.NRML}
        return mapping.get(str(prod).upper(), ProductType.MIS)
