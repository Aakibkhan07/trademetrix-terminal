import asyncio
import inspect
import json
import logging
import re
from collections.abc import Callable
from datetime import UTC, datetime

import httpx

from brokers.base import BaseBroker
from core.config import settings
from core.http_client import get_http_client
from core.models import (
    Candle,
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


class KotakNeoAdapter(BaseBroker):
    broker_name = "kotakneo"

    def __init__(self):
        self._client: httpx.AsyncClient | None = None
        self._access_token: str = ""
        self._consumer_key: str = ""
        self._base_url = "https://gw-napi.kotaksecurities.com"
        self._running = False

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = await get_http_client()
        return self._client

    async def authenticate(self, credentials: dict) -> Session:
        self._access_token = credentials.get("access_token") or credentials.get("secret_key") or ""
        self._consumer_key = credentials.get("client_id") or credentials.get("api_key") or ""

        if not self._access_token and self._consumer_key:
            secret = credentials.get("secret_key", "")
            if secret:
                client = await self._get_client()
                resp = await client.post(
                    f"{self._base_url}/api/v1/auth/token",
                    json={
                        "consumer_key": self._consumer_key,
                        "consumer_secret": secret,
                        "grant_type": "client_credentials",
                    },
                    headers={"Content-Type": "application/json"},
                    timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
                )
                data = resp.json()
                self._access_token = data.get("access_token", data.get("token", ""))
                if not self._access_token:
                    raise ValueError(f"Kotak Neo auth failed: {data.get('message', data.get('error', ''))}")

        if not self._access_token:
            raise ValueError("access_token required for Kotak Neo authentication")

        return Session(
            access_token=self._access_token,
            user_id=self._consumer_key,
            broker=self.broker_name,
            authenticated=True,
        )

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _ensure_neo_symbol(self, symbol: str) -> str:
        if ":" not in symbol and "|" not in symbol:
            return f"NSE:{symbol}"
        return symbol.replace("|", ":")

    async def place_order(self, order: NormalizedOrder) -> OrderResult:
        client = await self._get_client()
        payload = {
            "instrument_token": self._ensure_neo_symbol(order.symbol),
            "transaction_type": self._map_side(order.side),
            "quantity": order.quantity,
            "price": order.price or 0,
            "trigger_price": order.trigger_price or 0,
            "order_type": self._map_order_type(order.order_type),
            "product": self._map_product(order.product),
            "validity": "DAY",
            "disclosed_quantity": order.disclosed_quantity or 0,
        }
        resp = await client.post(
            f"{self._base_url}/api/v1/orders",
            json=payload,
            headers=self._headers(),
            timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
        )
        data = resp.json()
        success = data.get("status") == "success" or data.get("s") == "ok"
        return OrderResult(
            success=success,
            broker_order_id=data.get("data", {}).get("order_id", data.get("nOrdNo", "")),
            message=data.get("message", data.get("emsg", "")),
        )

    async def modify_order(self, order_id: str, changes: dict) -> OrderResult:
        client = await self._get_client()
        payload = {
            "order_id": order_id,
            "quantity": changes.get("quantity", 0),
            "price": changes.get("price", 0),
            "trigger_price": changes.get("trigger_price", 0),
            "order_type": self._map_order_type_str(changes.get("order_type", "MARKET")),
            "validity": "DAY",
        }
        resp = await client.put(
            f"{self._base_url}/api/v1/orders/{order_id}",
            json=payload,
            headers=self._headers(),
            timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
        )
        data = resp.json()
        return OrderResult(
            success=data.get("status") == "success",
            broker_order_id=order_id,
            message=data.get("message", ""),
        )

    async def cancel_order(self, order_id: str) -> OrderResult:
        client = await self._get_client()
        resp = await client.delete(
            f"{self._base_url}/api/v1/orders/{order_id}",
            headers=self._headers(),
            timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
        )
        data = resp.json()
        return OrderResult(
            success=True,
            broker_order_id=order_id,
            message=data.get("message", ""),
        )

    async def get_orderbook(self) -> list[NormalizedOrder]:
        client = await self._get_client()
        resp = await client.get(f"{self._base_url}/api/v1/orders", headers=self._headers(), timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout))
        data = resp.json()
        items = data.get("data", data.get("orders", data.get("result", [])))
        if isinstance(items, dict):
            items = list(items.values())
        return [self._normalize_order(item) for item in (items or [])]

    async def get_positions(self) -> list[Position]:
        client = await self._get_client()
        resp = await client.get(f"{self._base_url}/api/v1/positions", headers=self._headers(), timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout))
        data = resp.json()
        items = data.get("data", data.get("positions", data.get("result", [])))
        if isinstance(items, dict):
            items = list(items.values())
        return [self._normalize_position(item) for item in (items or [])]

    async def get_holdings(self) -> list[Holding]:
        client = await self._get_client()
        resp = await client.get(f"{self._base_url}/api/v1/holdings", headers=self._headers(), timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout))
        data = resp.json()
        items = data.get("data", data.get("holdings", data.get("result", [])))
        if isinstance(items, dict):
            items = list(items.values())
        return [self._normalize_holding(item) for item in (items or [])]

    async def get_funds(self) -> Funds:
        client = await self._get_client()
        resp = await client.get(f"{self._base_url}/api/v1/user/limits", headers=self._headers(), timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout))
        data = resp.json()
        limits = data.get("data", data.get("limits", data.get("result", {})))
        if isinstance(limits, list) and limits:
            limits = limits[0]
        return Funds(
            total_margin=float(limits.get("total_margin", limits.get("TotalMargin", limits.get("total", 0)))),
            used_margin=float(limits.get("used_margin", limits.get("UsedMargin", limits.get("used", 0)))),
            available_margin=float(limits.get("available_margin", limits.get("AvailableMargin", limits.get("cash", 0)))),
            broker=self.broker_name,
        )

    async def get_quotes(self, symbols: list[str]) -> list[Quote]:
        client = await self._get_client()
        keys = ",".join(self._ensure_neo_symbol(s) for s in symbols)
        resp = await client.get(
            f"{self._base_url}/api/v1/market/quote",
            params={"instrument_key": keys},
            headers=self._headers(),
            timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
        )
        data = resp.json()
        quotes = []
        items = data.get("data", data.get("quotes", data.get("result", {})))
        if isinstance(items, dict):
            for sym, item in items.items():
                quotes.append(self._normalize_quote(item, sym))
        elif isinstance(items, list):
            for item in items:
                quotes.append(self._normalize_quote(item))
        return quotes

    async def get_historical(
        self, symbol: str, interval: str, start: str | None = None, end: str | None = None, range: str | None = None
    ) -> list[Candle]:
        client = await self._get_client()
        key = self._ensure_neo_symbol(symbol)
        interval_map = {
            "1minute": "1m", "3minute": "3m", "5minute": "5m", "10minute": "10m",
            "15minute": "15m", "30minute": "30m", "1hour": "1h", "4hour": "4h",
            "1day": "1d", "1week": "1w", "1month": "1M",
        }
        mapped = interval_map.get(interval, interval)
        if not end:
            end = datetime.now(UTC).strftime("%Y-%m-%d")
        if not start:
            start = datetime.now(UTC).replace(day=1).strftime("%Y-%m-%d")
        resp = await client.get(
            f"{self._base_url}/api/v1/market/historical/{key}/{mapped}",
            params={"from": start, "to": end},
            headers=self._headers(),
            timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
        )
        data = resp.json()
        candles = []
        items = data.get("data", data.get("candles", data.get("result", [])))
        if isinstance(items, dict):
            items = items.get("candles", [])
        for item in items:
            if isinstance(item, list):
                ts = item[0]
                if isinstance(ts, str):
                    ts = ts.replace("T", " ").split("+")[0].split(".")[0]
                    try:
                        ts = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S") if " " in ts else datetime.strptime(ts, "%Y-%m-%d")
                    except ValueError:
                        ts = datetime.now(UTC)
                candles.append(
                    Candle(
                        symbol=symbol,
                        exchange=Exchange.NSE,
                        interval=interval,
                        open=float(item[1]),
                        high=float(item[2]),
                        low=float(item[3]),
                        close=float(item[4]),
                        volume=int(item[5]) if len(item) > 5 else 0,
                        timestamp=ts,
                    )
                )
        return candles

    async def stream(self, symbols: list[str], on_tick: Callable[[Tick], None]) -> None:
        import websockets

        if not self._access_token:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        self._running = True
        retry_delay = 1

        subscribe_msg = json.dumps({
            "action": "subscribe",
            "instruments": symbols,
        })

        while self._running:
            try:
                ws_headers = {
                    "Authorization": f"Bearer {self._access_token}",
                }
                async for ws in websockets.connect(
                    f"{self._base_url}/ws/market",
                    additional_headers=ws_headers,
                    ping_interval=30,
                ):
                    retry_delay = 1
                    try:
                        await ws.send(subscribe_msg)
                        async for raw in ws:
                            if not self._running:
                                break
                            if isinstance(raw, bytes):
                                raw = raw.decode("utf-8")
                            line = raw.strip()
                            if not line:
                                continue
                            try:
                                data = json.loads(line)
                                tick = self._parse_tick(data)
                                if tick:
                                    if inspect.iscoroutinefunction(on_tick):
                                        await on_tick(tick)
                                    else:
                                        on_tick(tick)
                            except json.JSONDecodeError:
                                continue
                    except websockets.ConnectionClosed:
                        logger.info("Kotak Neo WS disconnected, reconnecting...")
            except Exception as e:
                logger.error("Kotak Neo WS error: %s, reconnecting in %ds", e, retry_delay)
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 30)

    async def disconnect(self) -> None:
        self._running = False
        self._client = None

    def _parse_tick(self, data: dict) -> Tick | None:
        try:
            return Tick(
                symbol=data.get("symbol", data.get("tk", data.get("tradingsymbol", ""))),
                exchange=Exchange(data.get("exchange", "NSE")),
                last_price=float(data.get("ltp", data.get("lp", 0))),
                bid=float(data.get("bid", data.get("bp", 0))),
                ask=float(data.get("ask", data.get("sp", 0))),
                bid_qty=int(data.get("bid_qty", data.get("bc", 0))),
                ask_qty=int(data.get("ask_qty", data.get("sc", 0))),
                volume=int(data.get("volume", data.get("v", 0))),
                oi=int(data.get("oi", 0)),
                timestamp=datetime.now(UTC),
                broker=self.broker_name,
            )
        except (ValueError, KeyError, TypeError) as e:
            logger.warning("Failed to parse Kotak Neo tick: %s", e)
            return None

    @staticmethod
    def _map_side(side: OrderSide) -> str:
        return "BUY" if side == OrderSide.BUY else "SELL"

    @staticmethod
    def _map_order_type(ot: OrderType) -> str:
        mapping = {OrderType.MARKET: "MARKET", OrderType.LIMIT: "LIMIT", OrderType.SL: "STOP_LOSS", OrderType.SLM: "STOP_LOSS_MARKET"}
        return mapping.get(ot, "MARKET")

    @staticmethod
    def _map_order_type_str(ot: str) -> str:
        mapping = {"MARKET": "MARKET", "LIMIT": "LIMIT", "SL": "STOP_LOSS", "SLM": "STOP_LOSS_MARKET"}
        return mapping.get(ot, "MARKET")

    @staticmethod
    def _map_product(p: ProductType) -> str:
        mapping = {ProductType.INTRADAY: "INTRADAY", ProductType.DELIVERY: "DELIVERY", ProductType.MIS: "INTRADAY", ProductType.NRML: "NRML"}
        return mapping.get(p, "INTRADAY")

    def _normalize_order(self, item: dict) -> NormalizedOrder:
        inst = self._parse_instrument(item.get("tradingsymbol", item.get("symbol", "")))
        return NormalizedOrder(
            id=item.get("order_id", item.get("nOrdNo", item.get("orderId", ""))),
            broker_order_id=item.get("order_id", item.get("nOrdNo", "")),
            symbol=item.get("tradingsymbol", item.get("symbol", item.get("instrument_token", ""))),
            exchange=Exchange(item.get("exchange", "NSE")),
            side=OrderSide.BUY if item.get("transaction_type", "").upper() == "BUY" else OrderSide.SELL,
            order_type=OrderType(item.get("order_type", "MARKET").upper()),
            product=self._unmap_product(item.get("product", "INTRADAY")),
            quantity=int(item.get("quantity", item.get("qty", 0))),
            price=float(item.get("price", item.get("prc", 0))),
            trigger_price=float(item.get("trigger_price", item.get("trgprc", 0))) if item.get("trigger_price", item.get("trgprc")) else None,
            status=self._map_status(item.get("status", item.get("orderStatus", ""))),
            filled_quantity=int(item.get("filled_quantity", item.get("fillshares", item.get("exeqty", 0)))),
            average_price=float(item.get("average_price", item.get("avgprc", item.get("averagePrice", 0)))),
            broker=self.broker_name,
            instrument_type=inst["instrument_type"],
            strike_price=inst["strike_price"],
            expiry_date=inst["expiry_date"],
            option_type=inst["option_type"],
        )

    def _normalize_position(self, item: dict) -> Position:
        inst = self._parse_instrument(item.get("tradingsymbol", item.get("symbol", "")))
        qty = int(item.get("net_qty", item.get("netqty", item.get("quantity", 0))))
        buy_qty = int(item.get("buy_qty", item.get("buyqty", 0)))
        sell_qty = int(item.get("sell_qty", item.get("sellqty", 0)))
        return Position(
            symbol=item.get("tradingsymbol", item.get("symbol", "")),
            exchange=Exchange(item.get("exchange", "NSE")),
            quantity=qty,
            buy_quantity=buy_qty,
            sell_quantity=sell_qty,
            average_buy_price=float(item.get("buy_avg_price", item.get("buyavgprc", 0))),
            average_sell_price=float(item.get("sell_avg_price", item.get("sellavgprc", 0))),
            unrealised_pnl=float(item.get("unrealised_pnl", item.get("urmtom", 0))),
            realised_pnl=float(item.get("realised_pnl", item.get("rpnl", 0))),
            product=self._unmap_product(item.get("product", "INTRADAY")),
            broker=self.broker_name,
            instrument_type=inst["instrument_type"],
            strike_price=inst["strike_price"],
            expiry_date=inst["expiry_date"],
            option_type=inst["option_type"],
        )

    def _normalize_holding(self, item: dict) -> Holding:
        return Holding(
            symbol=item.get("tradingsymbol", item.get("symbol", "")),
            exchange=Exchange.NSE,
            quantity=int(item.get("quantity", item.get("hold_qty", 0))),
            average_price=float(item.get("average_price", item.get("avg_price", 0))),
            current_price=float(item.get("last_price", item.get("ltp", 0))),
            pnl=float(item.get("pnl", item.get("profit_loss", 0))),
            broker=self.broker_name,
        )

    def _normalize_quote(self, item: dict, symbol: str = "") -> Quote:
        ohlc = item.get("ohlc", {})
        sym = symbol or item.get("tradingsymbol", item.get("symbol", item.get("instrument_token", "")))
        inst = self._parse_instrument(sym)
        return Quote(
            symbol=sym,
            exchange=Exchange(item.get("exchange", "NSE")),
            last_price=float(item.get("last_price", item.get("ltp", 0))),
            open=float(ohlc.get("open", 0)),
            high=float(ohlc.get("high", 0)),
            low=float(ohlc.get("low", 0)),
            close=float(ohlc.get("close", 0)),
            volume=int(item.get("volume", item.get("v", 0))),
            bid=float(item.get("bid", item.get("bp", 0))),
            ask=float(item.get("ask", item.get("sp", 0))),
            timestamp=datetime.now(UTC),
            broker=self.broker_name,
            instrument_type=inst["instrument_type"],
            strike_price=inst["strike_price"],
            expiry_date=inst["expiry_date"],
            option_type=inst["option_type"],
        )

    @staticmethod
    def _unmap_product(prod: str) -> ProductType:
        mapping = {"INTRADAY": ProductType.INTRADAY, "DELIVERY": ProductType.DELIVERY, "MIS": ProductType.INTRADAY, "NRML": ProductType.NRML}
        return mapping.get(prod, ProductType.INTRADAY)

    @staticmethod
    def _parse_instrument(symbol: str) -> dict:
        m = re.match(r'^([A-Z]+)(\d{2})([A-Z]{3})(\d+)(CE|PE)$', symbol.upper())
        if m:
            yy = int(m.group(2))
            month_code = m.group(3)
            months = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
            month_num = months.get(month_code, 1)
            return {
                "instrument_type": InstrumentType.OPT,
                "strike_price": float(m.group(4)),
                "expiry_date": f"{2000+yy}-{month_num:02d}",
                "option_type": OptionType(m.group(5)),
            }
        m = re.match(r'^([A-Z]+)(\d{2})([A-Z]{3})$', symbol.upper())
        if m:
            return {"instrument_type": InstrumentType.FUT, "strike_price": None, "expiry_date": None, "option_type": None}
        return {"instrument_type": InstrumentType.EQ, "strike_price": None, "expiry_date": None, "option_type": None}

    @staticmethod
    def _map_status(status: str) -> OrderStatus:
        mapping = {
            "PENDING": OrderStatus.PENDING,
            "OPEN": OrderStatus.OPEN,
            "COMPLETE": OrderStatus.FILLED,
            "FILLED": OrderStatus.FILLED,
            "CANCELLED": OrderStatus.CANCELLED,
            "CANCELED": OrderStatus.CANCELLED,
            "REJECTED": OrderStatus.REJECTED,
            "TRIGGER_PENDING": OrderStatus.PENDING,
        }
        return mapping.get(status.upper(), OrderStatus.PENDING)
