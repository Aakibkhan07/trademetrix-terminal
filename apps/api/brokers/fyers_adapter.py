import asyncio
import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime

from brokers.base import BaseBroker
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
from fyers_apiv3 import fyersModel

logger = logging.getLogger(__name__)

_FY_ID_CACHE: dict[str, str] = {}


class FyersAdapter(BaseBroker):
    broker_name = "fyers"

    def __init__(self):
        self._client_id: str = ""
        self._access_token: str = ""
        self._user_id: str = ""
        self._fyers: fyersModel.FyersModel | None = None
        self._running = False

    async def authenticate(self, credentials: dict) -> Session:
        client_id = credentials.get("client_id", "")
        raw_token = credentials.get("access_token", "")

        self._client_id = client_id
        self._access_token = raw_token

        if raw_token:
            payload = self._decode_jwt_payload(raw_token)
            self._user_id = payload.get("fy_id", "")
        else:
            auth_code = credentials.get("auth_code", "")
            if not auth_code:
                raise ValueError("auth_code required for Fyers authentication when no access_token is stored")
            app_secret = credentials.get("secret_key", "")
            from fyers_apiv3 import fyersModel as fm

            session = fm.SessionModel(
                client_id=client_id,
                secret_key=app_secret,
                redirect_uri="https://trade.fyers.in/api-login/redirect-uri/index.html",
                grant_type="authorization_code",
            )
            session.set_token(auth_code)
            token_resp = session.generate_token()
            raw_token = token_resp.get("access_token", "")
            self._access_token = raw_token
            payload = self._decode_jwt_payload(raw_token)
            self._user_id = payload.get("fy_id", "")

        self._fyers = fyersModel.FyersModel(
            client_id=client_id,
            token=self._access_token,
            log_path="",
        )
        return Session(
            access_token=raw_token,
            user_id=self._user_id,
            broker=self.broker_name,
            authenticated=True,
        )

    def _ensure_fyers_symbol(self, symbol: str) -> str:
        if ":" not in symbol:
            exchange_prefix = "NSE"
            return f"{exchange_prefix}:{symbol.upper()}"
        return symbol.upper()

    async def place_order(self, order: NormalizedOrder) -> OrderResult:
        if not self._fyers:
            return OrderResult(success=False, message="Not authenticated")
        payload = {
            "symbol": self._ensure_fyers_symbol(order.symbol),
            "qty": order.quantity,
            "type": self._map_order_type(order.order_type),
            "side": 1 if order.side == OrderSide.BUY else -1,
            "productType": self._map_product(order.product),
            "limitPrice": order.price or 0,
            "stopPrice": order.trigger_price or 0,
            "validity": "DAY",
            "offlineOrder": False,
            "stopLoss": 0,
            "takeProfit": 0,
        }
        data = await self._sync(self._fyers.place_order, payload)
        success = data.get("s") == "ok"
        return OrderResult(
            success=success,
            broker_order_id=data.get("id", ""),
            message=data.get("message", ""),
        )

    async def modify_order(self, order_id: str, changes: dict) -> OrderResult:
        if not self._fyers:
            return OrderResult(success=False, message="Not authenticated")
        payload = {"id": order_id, **changes}
        data = await self._sync(self._fyers.modify_order, payload)
        return OrderResult(
            success=data.get("s") == "ok",
            broker_order_id=order_id,
            message=data.get("message", ""),
        )

    async def cancel_order(self, order_id: str) -> OrderResult:
        if not self._fyers:
            return OrderResult(success=False, message="Not authenticated")
        data = await self._sync(self._fyers.cancel_order, {"id": order_id})
        return OrderResult(
            success=data.get("s") == "ok",
            broker_order_id=order_id,
            message=data.get("message", ""),
        )

    async def get_orderbook(self) -> list[NormalizedOrder]:
        if not self._fyers:
            return []
        data = await self._sync(self._fyers.orderbook)
        orders = []
        for item in data.get("orderBook", []):
            orders.append(self._normalize_order(item))
        return orders

    async def get_positions(self) -> list[Position]:
        if not self._fyers:
            return []
        data = await self._sync(self._fyers.positions)
        positions = []
        for item in data.get("netPositions", []):
            positions.append(self._normalize_position(item))
        return positions

    async def get_holdings(self) -> list[Holding]:
        if not self._fyers:
            return []
        data = await self._sync(self._fyers.holdings)
        holdings = []
        for item in data.get("holdings", []):
            holdings.append(self._normalize_holding(item))
        return holdings

    async def get_funds(self) -> Funds:
        if not self._fyers:
            return Funds(broker=self.broker_name)
        data = await self._sync(self._fyers.funds)
        fund_limit = data.get("fund_limit", [])
        total = 0.0
        used = 0.0
        available = 0.0
        for item in fund_limit:
            title = item.get("title", "").lower()
            eq = float(item.get("equityAmount", 0))
            if "total" in title and "balance" in title:
                total = eq
            elif "utilized" in title:
                used = eq
            elif "clear" in title and "balance" in title:
                available = eq
        return Funds(
            total_margin=total,
            used_margin=used,
            available_margin=available,
            broker=self.broker_name,
        )

    async def get_quotes(self, symbols: list[str]) -> list[Quote]:
        if not self._fyers:
            return []
        data = await self._sync(self._fyers.quotes, {"symbols": ",".join(symbols)})
        quotes = []
        for item in data.get("d", []):
            quotes.append(self._normalize_quote(item))
        return quotes

    async def get_historical(
        self, symbol: str, interval: str, start: str | None = None, end: str | None = None, range: str | None = None
    ) -> list[Candle]:
        if not self._fyers:
            return []
        params = {"symbol": symbol, "resolution": interval, "date_format": "0"}
        if start:
            params["range_from"] = str(int(float(start)))
        if end:
            params["range_to"] = str(int(float(end)))
        if range:
            params["range"] = range
        if "range_from" not in params and "range" not in params:
            import time
            params["range_from"] = str(int(time.time()) - 86400 * 60)
        if "range_to" not in params and "range" not in params:
            import time
            params["range_to"] = str(int(time.time()))
        data = await self._sync(self._fyers.history, params)
        candles = []
        for item in data.get("candles", []):
            candles.append(
                Candle(
                    symbol=symbol,
                    exchange=Exchange.NSE,
                    interval=interval,
                    open=float(item[1]),
                    high=float(item[2]),
                    low=float(item[3]),
                    close=float(item[4]),
                    volume=int(item[5]),
                    timestamp=datetime.fromtimestamp(item[0]),
                )
            )
        return candles

    async def stream(self, symbols: list[str], on_tick: Callable[[Tick], None]) -> None:
        if not self._fyers:
            raise RuntimeError("Not authenticated. Call authenticate() first.")
        self._running = True
        _prev: dict[str, float] = {}

        while self._running:
            try:
                data = await self._sync(self._fyers.quotes, {"symbols": ",".join(symbols)})
                for item in data.get("d", []):
                    v = item.get("v", {})
                    sym = v.get("symbol") or item.get("n", "")
                    lp = float(v.get("lp", 0))
                    prev = _prev.get(sym)
                    change = (lp - prev) if prev is not None else 0.0
                    change_pct = ((lp - prev) / prev * 100) if prev and prev != 0 else 0.0
                    _prev[sym] = lp
                    inst_type = InstrumentType.EQ
                    strike = None
                    expiry = None
                    opt_type = None
                    if ":" in sym:
                        parsed = self._parse_instrument(sym)
                        inst_type = parsed["instrument_type"]
                        strike = parsed["strike_price"]
                        expiry = parsed["expiry_date"]
                        opt_type = parsed["option_type"]
                    tick = Tick(
                        symbol=sym,
                        exchange=Exchange.NSE,
                        last_price=lp,
                        bid=float(v.get("bid", 0)),
                        ask=float(v.get("ask", 0)),
                        bid_qty=int(v.get("bid_size", 0)),
                        ask_qty=int(v.get("ask_size", 0)),
                        volume=int(v.get("volume", 0)),
                        oi=int(v.get("oi", 0)),
                        change=round(change, 2),
                        change_pct=round(change_pct, 2),
                        timestamp=datetime.now(UTC),
                        broker=self.broker_name,
                        instrument_type=inst_type,
                        strike_price=strike,
                        expiry_date=expiry,
                        option_type=opt_type,
                    )
                    if asyncio.iscoroutinefunction(on_tick):
                        await on_tick(tick)
                    else:
                        on_tick(tick)
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Fyers polling error: %s", e)
                await asyncio.sleep(5)

    async def disconnect(self) -> None:
        self._running = False

    async def _sync(self, method, *args, **kwargs):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: method(*args, **kwargs))

    @staticmethod
    def _decode_jwt_payload(token: str) -> dict:
        try:
            parts = token.split(".")
            if len(parts) != 3:
                return {}
            padded = parts[1] + "=" * (4 - len(parts[1]) % 4)
            import base64

            return json.loads(base64.urlsafe_b64decode(padded))
        except Exception:
            return {}

    def _normalize_order(self, item: dict) -> NormalizedOrder:
        inst = self._parse_instrument(item.get("symbol", ""))
        return NormalizedOrder(
            id=item.get("id", ""),
            broker_order_id=item.get("id_fyers", ""),
            symbol=item.get("symbol", ""),
            exchange=Exchange.NSE,
            side=OrderSide.BUY if item.get("side", 1) == 1 else OrderSide.SELL,
            order_type=self._rev_map_order_type(item.get("type", 1)),
            product=self._rev_map_product(item.get("productType", "INTRADAY")),
            quantity=int(item.get("qty", 0)),
            price=float(item.get("limitPrice", 0)),
            trigger_price=float(item.get("stopPrice", 0)) if item.get("stopPrice") else None,
            status=self._map_status(item.get("status", 0)),
            filled_quantity=int(item.get("filledQty", 0)),
            average_price=float(item.get("tradedPrice", 0)),
            broker=self.broker_name,
            instrument_type=inst["instrument_type"],
            strike_price=inst["strike_price"],
            expiry_date=inst["expiry_date"],
            option_type=inst["option_type"],
        )

    def _normalize_position(self, item: dict) -> Position:
        inst = self._parse_instrument(item.get("symbol", ""))
        return Position(
            symbol=item.get("symbol", ""),
            exchange=Exchange.NSE,
            quantity=int(item.get("netQty", 0)),
            buy_quantity=int(item.get("buyQty", 0)),
            sell_quantity=int(item.get("sellQty", 0)),
            average_buy_price=float(item.get("avgBuyPrice", 0)),
            average_sell_price=float(item.get("avgSellPrice", 0)),
            unrealised_pnl=float(item.get("unrealised", 0)),
            realised_pnl=float(item.get("realised", 0)),
            product=ProductType.INTRADAY,
            broker=self.broker_name,
            instrument_type=inst["instrument_type"],
            strike_price=inst["strike_price"],
            expiry_date=inst["expiry_date"],
            option_type=inst["option_type"],
        )

    def _normalize_holding(self, item: dict) -> Holding:
        return Holding(
            symbol=item.get("symbol", ""),
            exchange=Exchange.NSE,
            quantity=int(item.get("quantity", 0)),
            average_price=float(item.get("averagePrice", 0)),
            current_price=float(item.get("ltp", 0)),
            pnl=float(item.get("pnl", 0)),
            broker=self.broker_name,
        )

    def _normalize_quote(self, item: dict) -> Quote:
        v = item.get("v", {})
        sym = v.get("symbol") or item.get("n", "")
        inst = self._parse_instrument(sym)
        return Quote(
            symbol=sym,
            exchange=Exchange.NSE,
            last_price=float(v.get("lp", 0)),
            open=float(v.get("open_price", 0)),
            high=float(v.get("high_price", 0)),
            low=float(v.get("low_price", 0)),
            close=float(v.get("prev_close_price", 0)),
            volume=int(v.get("volume", 0)),
            bid=float(v.get("bid", 0)),
            ask=float(v.get("ask", 0)),
            timestamp=datetime.now(UTC),
            broker=self.broker_name,
            instrument_type=inst["instrument_type"],
            strike_price=inst["strike_price"],
            expiry_date=inst["expiry_date"],
            option_type=inst["option_type"],
        )

    @staticmethod
    def _parse_instrument(symbol: str) -> dict:
        import re

        clean = symbol.split(":")[-1] if ":" in symbol else symbol
        m = re.match(r"^([A-Z]+)(\d{2})([A-Z]{3})(\d+)(CE|PE)$", clean.upper())
        if m:
            yy = int(m.group(2))
            month_code = m.group(3)
            months = {
                "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
                "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
            }
            month_num = months.get(month_code, 1)
            return {
                "instrument_type": InstrumentType.OPT,
                "strike_price": float(m.group(4)),
                "expiry_date": f"{2000 + yy}-{month_num:02d}",
                "option_type": OptionType(m.group(5)),
            }
        m = re.match(r"^([A-Z]+)(\d{2})([A-Z]{3})$", clean.upper())
        if m:
            return {"instrument_type": InstrumentType.FUT, "strike_price": None, "expiry_date": None, "option_type": None}
        return {"instrument_type": InstrumentType.EQ, "strike_price": None, "expiry_date": None, "option_type": None}

    @staticmethod
    def _map_order_type(ot: OrderType) -> int:
        mapping = {OrderType.MARKET: 1, OrderType.LIMIT: 2, OrderType.SL: 3, OrderType.SLM: 4}
        return mapping.get(ot, 1)

    @staticmethod
    def _rev_map_order_type(code: int) -> OrderType:
        mapping = {1: OrderType.MARKET, 2: OrderType.LIMIT, 3: OrderType.SL, 4: OrderType.SLM}
        return mapping.get(code, OrderType.MARKET)

    @staticmethod
    def _map_product(p: ProductType) -> str:
        mapping = {
            ProductType.INTRADAY: "INTRADAY",
            ProductType.DELIVERY: "DELIVERY",
            ProductType.MIS: "INTRADAY",
            ProductType.NRML: "CNC",
        }
        return mapping.get(p, "INTRADAY")

    @staticmethod
    def _rev_map_product(code: str) -> ProductType:
        mapping = {"INTRADAY": ProductType.INTRADAY, "DELIVERY": ProductType.DELIVERY, "MARGIN": ProductType.INTRADAY, "CNC": ProductType.NRML}
        return mapping.get(code, ProductType.INTRADAY)

    @staticmethod
    def _map_status(code: int) -> OrderStatus:
        mapping = {
            1: OrderStatus.OPEN,
            2: OrderStatus.PENDING,
            3: OrderStatus.FILLED,
            4: OrderStatus.CANCELLED,
            5: OrderStatus.REJECTED,
            6: OrderStatus.EXPIRED,
        }
        return mapping.get(code, OrderStatus.PENDING)
