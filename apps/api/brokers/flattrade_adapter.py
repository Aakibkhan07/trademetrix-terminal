import asyncio
import inspect
import hashlib
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


class FlattradeAdapter(BaseBroker):
    broker_name = "flattrade"

    def __init__(self):
        self._client: httpx.AsyncClient | None = None
        self._access_token: str = ""
        self._user_id: str = ""
        self._base_url = "https://piconnect.flattrade.in/PiConnectTP"
        self._ws_url = "wss://piconnect.flattrade.in/PiConnectWSTP"
        self._running = False
        self._susertoken: str = ""

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = await get_http_client()
        return self._client

    async def authenticate(self, credentials: dict) -> Session:
        uid = credentials.get("client_code") or credentials.get("client_id") or credentials.get("api_key") or ""
        pwd = credentials.get("secret_key") or ""
        factor2 = credentials.get("additional_params", {}).get("totp_secret", credentials.get("totp_secret", ""))

        self._user_id = uid
        self._access_token = credentials.get("access_token") or ""

        if not self._access_token and uid and pwd:
            apk = ""
            imei = "1234567890"
            vc = f"{uid}_FLATTRADE_TP"
            client = await self._get_client()
            pwd_encoded = hashlib.sha256(pwd.encode()).hexdigest()
            if factor2 and len(factor2) <= 8:
                import pyotp
                try:
                    factor2 = pyotp.TOTP(factor2).now()
                except Exception as e:
                    logger.warning("TOTP factor2 generation failed: %s", e)
            payload = {
                "uid": uid,
                "pwd": pwd_encoded,
                "factor2": factor2,
                "vc": vc,
                "apk": apk,
                "imei": imei,
                "source": "API",
            }
            resp = await client.post(f"{self._base_url}/QuickAuth", data=payload, timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout))
            data = resp.json()
            if data.get("stat") != "Ok":
                raise ValueError(f"Flattrade login failed: {data.get('emsg', '')}")
            self._susertoken = data.get("susertoken", "")
            self._access_token = self._susertoken
            self._user_id = data.get("uid", uid)

        if not self._access_token:
            raise ValueError("access_token required for Flattrade authentication")

        return Session(
            access_token=self._access_token,
            user_id=self._user_id,
            broker=self.broker_name,
            authenticated=True,
        )

    async def _noren_post(self, endpoint: str, payload: dict) -> dict:
        client = await self._get_client()
        payload["uid"] = self._user_id
        data_str = json.dumps(payload)
        resp = await client.post(
            f"{self._base_url}/{endpoint}",
            content=data_str,
            headers={
                "Content-Type": "text/plain",
                "Authorization": self._access_token,
            },
            timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
        )
        return resp.json()

    async def place_order(self, order: NormalizedOrder) -> OrderResult:
        payload = {
            "trantype": self._map_side(order.side),
            "prc": str(order.price or 0),
            "qty": str(order.quantity),
            "prctyp": self._map_order_type(order.order_type),
            "dscqty": str(order.disclosed_quantity or 0),
            "trgprc": str(order.trigger_price or 0),
            "exch": self._map_exchange(order.exchange),
            "tsym": order.symbol,
            "pcode": self._map_product(order.product),
            "ret": "DAY",
            "actid": self._user_id,
        }
        data = await self._noren_post("PlaceOrder", payload)
        success = data.get("stat") == "Ok"
        return OrderResult(
            success=success,
            broker_order_id=data.get("norenordno", data.get("result", "")),
            message=data.get("emsg", data.get("result", "")),
        )

    async def modify_order(self, order_id: str, changes: dict) -> OrderResult:
        payload = {
            "norenordno": order_id,
            "qty": str(changes.get("quantity", 0)),
            "prc": str(changes.get("price", 0)),
            "trgprc": str(changes.get("trigger_price", 0)),
            "prctyp": self._map_order_type_str(changes.get("order_type", "MARKET")),
        }
        data = await self._noren_post("ModifyOrder", payload)
        return OrderResult(
            success=data.get("stat") == "Ok",
            broker_order_id=order_id,
            message=data.get("emsg", ""),
        )

    async def cancel_order(self, order_id: str) -> OrderResult:
        payload = {"norenordno": order_id}
        data = await self._noren_post("CancelOrder", payload)
        return OrderResult(
            success=data.get("stat") == "Ok",
            broker_order_id=order_id,
            message=data.get("emsg", ""),
        )

    async def get_orderbook(self) -> list[NormalizedOrder]:
        data = await self._noren_post("OrderBook", {})
        items = data if isinstance(data, list) else data.get("data", [])
        return [self._normalize_order(item) for item in items]

    async def get_positions(self) -> list[Position]:
        data = await self._noren_post("PositionBook", {})
        items = data if isinstance(data, list) else data.get("data", [])
        return [self._normalize_position(item) for item in items]

    async def get_holdings(self) -> list[Holding]:
        data = await self._noren_post("Holdings", {"actid": self._user_id})
        items = data if isinstance(data, list) else data.get("data", data.get("holdings", []))
        return [self._normalize_holding(item) for item in items]

    async def get_funds(self) -> Funds:
        data = await self._noren_post("Limits", {})
        return Funds(
            total_margin=float(data.get("cash", data.get("total", 0))),
            used_margin=float(data.get("used", 0)),
            available_margin=float(data.get("cash", 0)),
            broker=self.broker_name,
        )

    async def get_quotes(self, symbols: list[str]) -> list[Quote]:
        quotes = []
        for sym in symbols:
            data = await self._noren_post("GetQuotes", {"exch": "NSE", "tsym": sym})
            if data.get("stat") == "Ok":
                quotes.append(self._normalize_quote(data, sym))
        return quotes

    async def get_historical(
        self, symbol: str, interval: str, start: str | None = None, end: str | None = None, range: str | None = None
    ) -> list[Candle]:
        interval_map = {
            "1minute": "1", "3minute": "3", "5minute": "5", "10minute": "10",
            "15minute": "15", "30minute": "30", "60minute": "60", "1hour": "60",
            "1day": "D", "1week": "W",
        }
        data = await self._noren_post("GetTPSeries", {
            "exch": "NSE",
            "tsym": symbol,
            "intrv": interval_map.get(interval, "1"),
        })
        items = data if isinstance(data, list) else data.get("data", [])
        candles = []
        for item in items:
            try:
                ts = datetime.fromtimestamp(int(item.get("time", 0)))
            except (ValueError, TypeError):
                ts = datetime.now(UTC)
            candles.append(
                Candle(
                    symbol=symbol,
                    exchange=Exchange.NSE,
                    interval=interval,
                    open=float(item.get("into", 0)),
                    high=float(item.get("inth", 0)),
                    low=float(item.get("intl", 0)),
                    close=float(item.get("intc", 0)),
                    volume=int(item.get("intv", 0)),
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

        while self._running:
            try:
                ws_url = f"{self._ws_url}?susertoken={self._access_token}&uid={self._user_id}"
                async for ws in websockets.connect(ws_url, ping_interval=30):
                    retry_delay = 1

                    sub_msg = json.dumps({"t": "s", "k": symbols})
                    await ws.send(sub_msg)

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
                            if "Touchline" in data:
                                data = data["Touchline"]
                            tick = self._parse_tick(data)
                            if tick:
                                if inspect.iscoroutinefunction(on_tick):
                                    await on_tick(tick)
                                else:
                                    on_tick(tick)
                        except json.JSONDecodeError:
                            continue
            except Exception as e:
                logger.error("Shoonya WS error: %s, reconnecting in %ds", e, retry_delay)
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 30)

    async def disconnect(self) -> None:
        self._running = False
        self._client = None

    def _headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _parse_tick(self, data: dict) -> Tick | None:
        try:
            return Tick(
                symbol=data.get("tsym", data.get("sym", "")),
                exchange=Exchange(data.get("exch", "NSE")),
                last_price=float(data.get("lp", data.get("ltp", 0))),
                bid=float(data.get("bp", 0)),
                ask=float(data.get("sp", 0)),
                bid_qty=int(data.get("bc", 0)),
                ask_qty=int(data.get("sc", 0)),
                volume=int(data.get("v", data.get("vol", 0))),
                oi=int(data.get("oi", 0)),
                timestamp=datetime.now(UTC),
                broker=self.broker_name,
            )
        except (ValueError, KeyError, TypeError) as e:
            logger.warning("Failed to parse Flattrade tick: %s", e)
            return None

    @staticmethod
    def _map_side(side: OrderSide) -> str:
        return "B" if side == OrderSide.BUY else "S"

    @staticmethod
    def _map_order_type(ot: OrderType) -> str:
        mapping = {OrderType.MARKET: "MKT", OrderType.LIMIT: "LMT", OrderType.SL: "SL", OrderType.SLM: "SL-M"}
        return mapping.get(ot, "MKT")

    @staticmethod
    def _map_order_type_str(ot: str) -> str:
        mapping = {"MARKET": "MKT", "LIMIT": "LMT", "SL": "SL", "SLM": "SL-M"}
        return mapping.get(ot, "MKT")

    @staticmethod
    def _map_product(p: ProductType) -> str:
        mapping = {ProductType.INTRADAY: "MIS", ProductType.DELIVERY: "CNC", ProductType.MIS: "MIS", ProductType.NRML: "NRML"}
        return mapping.get(p, "MIS")

    @staticmethod
    def _map_exchange(exchange: Exchange) -> str:
        mapping = {Exchange.NSE: "NSE", Exchange.BSE: "BSE", Exchange.NFO: "NFO", Exchange.MCX: "MCX"}
        return mapping.get(exchange, "NSE")

    def _normalize_order(self, item: dict) -> NormalizedOrder:
        inst = self._parse_instrument(item.get("tsym", ""))
        return NormalizedOrder(
            id=item.get("norenordno", item.get("ordid", "")),
            broker_order_id=item.get("norenordno", ""),
            symbol=item.get("tsym", ""),
            exchange=Exchange(item.get("exch", "NSE")),
            side=OrderSide.BUY if item.get("trantype") == "B" else OrderSide.SELL,
            order_type=self._unmap_order_type(item.get("prctyp", "MKT")),
            product=self._unmap_product(item.get("pcode", "MIS")),
            quantity=int(item.get("qty", 0)),
            price=float(item.get("prc", 0)),
            trigger_price=float(item.get("trgprc", 0)) if item.get("trgprc") else None,
            status=self._map_status(item.get("status", "")),
            filled_quantity=int(item.get("fillshares", item.get("exeqty", 0))),
            average_price=float(item.get("avgprc", item.get("flprc", 0))),
            broker=self.broker_name,
            instrument_type=inst["instrument_type"],
            strike_price=inst["strike_price"],
            expiry_date=inst["expiry_date"],
            option_type=inst["option_type"],
        )

    def _normalize_position(self, item: dict) -> Position:
        inst = self._parse_instrument(item.get("tsym", ""))
        qty = int(item.get("netqty", item.get("quantity", 0)))
        buy_qty = int(item.get("buyqty", 0))
        sell_qty = int(item.get("sellqty", 0))
        return Position(
            symbol=item.get("tsym", ""),
            exchange=Exchange(item.get("exch", "NSE")),
            quantity=qty,
            buy_quantity=buy_qty,
            sell_quantity=sell_qty,
            average_buy_price=float(item.get("buyavgprc", item.get("buyavg", 0))),
            average_sell_price=float(item.get("sellavgprc", item.get("sellavg", 0))),
            unrealised_pnl=float(item.get("urmtom", 0)),
            realised_pnl=float(item.get("rpnl", 0)),
            product=self._unmap_product(item.get("pcode", "MIS")),
            broker=self.broker_name,
            instrument_type=inst["instrument_type"],
            strike_price=inst["strike_price"],
            expiry_date=inst["expiry_date"],
            option_type=inst["option_type"],
        )

    def _normalize_quote(self, item: dict, symbol: str = "") -> Quote:
        inst = self._parse_instrument(symbol or item.get("tsym", ""))
        return Quote(
            symbol=symbol or item.get("tsym", ""),
            exchange=Exchange(item.get("exch", "NSE")),
            last_price=float(item.get("lp", 0)),
            open=float(item.get("opn", 0)),
            high=float(item.get("hgh", 0)),
            low=float(item.get("low", 0)),
            close=float(item.get("cls", 0)),
            volume=int(item.get("v", 0)),
            bid=float(item.get("bp", 0)),
            ask=float(item.get("sp", 0)),
            timestamp=datetime.now(UTC),
            broker=self.broker_name,
            instrument_type=inst["instrument_type"],
            strike_price=inst["strike_price"],
            expiry_date=inst["expiry_date"],
            option_type=inst["option_type"],
        )

    @staticmethod
    def _unmap_product(prod: str) -> ProductType:
        mapping = {"MIS": ProductType.INTRADAY, "CNC": ProductType.DELIVERY, "NRML": ProductType.NRML}
        return mapping.get(prod, ProductType.INTRADAY)

    @staticmethod
    def _unmap_order_type(ot: str) -> OrderType:
        mapping = {"MKT": OrderType.MARKET, "LMT": OrderType.LIMIT, "SL": OrderType.SL, "SL-M": OrderType.SLM}
        return mapping.get(ot, OrderType.MARKET)

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
