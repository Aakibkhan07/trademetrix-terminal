import asyncio
import inspect
import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime

import httpx

from brokers.base import BaseBroker
from brokers.sdk.interface import BrokerAdapterBase
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


class DhanAdapter(BaseBroker, BrokerAdapterBase):
    broker_name = "dhan"

    def __init__(self):
        self._client: httpx.AsyncClient | None = None
        self._access_token: str = ""
        self._client_id: str = ""
        self._base_url = "https://api.dhan.co/v2"
        #: There is deliberately no `_ws_url` here. This adapter once carried its own
        #: websocket URL -- `wss://api.dhan.co/v2/ws`, which is the wrong host and the wrong
        #: path -- and its own connection code to go with it. The feed endpoint now lives in
        #: exactly one place, `market.dhan_feed.DHAN_FEED_WSS_URL` (`wss://api-feed.dhan.co`),
        #: and `stream()` delegates to `DhanMarketFeed`. Keeping a second URL around would
        #: only invite the second implementation back.
        self._running = False

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = await get_http_client()
        return self._client

    async def authenticate(self, credentials: dict) -> Session:
        auth_code = credentials.get("auth_code", "")
        access_token = credentials.get("access_token", "")
        client_id = credentials.get("client_id") or credentials.get("api_key") or credentials.get("dhanClientId") or ""
        secret_key = credentials.get("secret_key", "")

        if auth_code and client_id and secret_key:
            return await self._exchange_auth_code(client_id, secret_key, auth_code)

        self._access_token = access_token or credentials.get("secret_key") or ""
        self._client_id = client_id
        if not self._access_token:
            raise ValueError("access_token required for Dhan authentication")

        client = await self._get_client()
        resp = await client.get(
            f"{self._base_url}/orders",
            headers=self._headers(),
            timeout=httpx.Timeout(10, connect=5),
        )
        if resp.status_code == 401:
            raise ValueError("Dhan authentication failed — invalid access_token")

        return Session(
            access_token=self._access_token,
            user_id=self._client_id,
            broker=self.broker_name,
            authenticated=True,
        )

    async def _exchange_auth_code(self, client_id: str, client_secret: str, auth_code: str) -> Session:
        from core.config import settings
        redirect_uri = settings.dhan_redirect_uri or "https://api.ai.trademetrix.tech/api/v1/brokers/dhan/callback"
        client = await self._get_client()
        resp = await client.post(
            f"{self._base_url}/oauth/token",
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": auth_code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
        )
        data = resp.json()
        if resp.status_code != 200 or not data.get("access_token"):
            raise ValueError(f"Dhan token exchange failed: {data.get('message', resp.status_code)}")
        self._access_token = data["access_token"]
        self._client_id = client_id
        return Session(
            access_token=self._access_token,
            user_id=client_id,
            broker=self.broker_name,
            authenticated=True,
        )

    def _headers(self) -> dict:
        return {
            "access-token": self._access_token,
            "Content-Type": "application/json",
        }

    async def place_order(self, order: NormalizedOrder) -> OrderResult:
        client = await self._get_client()

        # Contract metadata must come from the canonical resolver, never from the
        # display symbol. Dhan's `securityId` is a broker-assigned internal
        # identifier, and this previously sent `order.symbol` -- the app's canonical
        # display string -- straight into that field. `exchangeSegment` also
        # defaulted to "NSE_EQ" for any (exchange, instrument_type) pair outside the
        # seven-entry map above, so a futures order could be addressed to the
        # cash-equity segment.
        #
        # Unresolvable metadata blocks the order. It is returned as a failed result
        # rather than raised: OMS treats an exception from place_order as a retryable
        # queue error (oms/manager.py:533 re-queues without completing the item), so
        # raising here would retry a permanently-blocked order forever. A failed
        # result is what marks the order REJECTED and completes the queue item.
        #
        # The local exchange/instrument-type map this used to consult is gone. It
        # defaulted to "NSE_EQ" for any pair it did not list, so an unrecognised
        # futures order was addressed to the cash-equity segment; the segment now
        # comes from the resolver alongside the security id it belongs with.
        from market.instruments import instrument_resolver

        raw_type = getattr(order.instrument_type, "value", order.instrument_type) or ""
        instrument = instrument_resolver.resolve(
            order.symbol, broker="dhan", instrument_type=str(raw_type)
        )
        if instrument is None:
            blocked = (
                "ORDER BLOCKED - Unable to resolve authoritative instrument metadata. "
                f"Symbol: {order.symbol}. Broker: dhan. Instrument type: {raw_type}. "
                "Required metadata: Security ID, Exchange Segment, Instrument Type, Lot Size."
            )
            logger.error(blocked)
            return OrderResult(success=False, message=blocked, status="rejected")

        seg = instrument.exchange_segment
        security_id = instrument.security_id

        payload: dict = {
            "dhanClientId": self._client_id,
            "transactionType": self._map_side(order.side),
            "exchangeSegment": seg,
            "productType": self._map_product(order.product),
            "orderType": self._map_order_type(order.order_type),
            "validity": "DAY",
            "securityId": security_id,
            "quantity": order.quantity,
            "afterMarketOrder": False,
        }
        if order.price and order.price > 0:
            payload["price"] = order.price
        if order.trigger_price and order.trigger_price > 0:
            payload["triggerPrice"] = order.trigger_price
        if order.disclosed_quantity and order.disclosed_quantity > 0:
            payload["disclosedQuantity"] = order.disclosed_quantity
        if order.instrument_type in (InstrumentType.FUT, InstrumentType.OPT) and order.expiry_date:
            payload["drvExpiryDate"] = order.expiry_date
        if order.instrument_type == InstrumentType.OPT:
            if order.option_type:
                payload["drvOptionType"] = order.option_type.value
            if order.strike_price:
                payload["drvStrikePrice"] = order.strike_price
        # Derivative identity now prefers the resolved instrument. The order's own
        # fields are used only when present, because they are set opportunistically by
        # whichever caller built the order and are frequently absent -- which is how a
        # contract could reach the broker without an expiry or a strike. Same source
        # as the security id and segment, so the payload cannot describe two different
        # contracts.
        if order.instrument_type in (InstrumentType.FUT, InstrumentType.OPT):
            payload["drvExpiryDate"] = order.expiry_date or instrument.expiry or None
            if payload["drvExpiryDate"] is None:
                payload.pop("drvExpiryDate")
        if order.instrument_type == InstrumentType.OPT:
            opt_type = order.option_type.value if order.option_type else instrument.option_type
            if opt_type:
                payload["drvOptionType"] = opt_type
            strike = order.strike_price if order.strike_price else instrument.strike
            if strike:
                payload["drvStrikePrice"] = strike
        hdrs = self._headers()
        if order.client_order_id:
            hdrs["correlationId"] = order.client_order_id
        resp = await client.post(f"{self._base_url}/orders", json=payload, headers=hdrs, timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout))
        data = resp.json()
        success = data.get("status") == "success"
        return OrderResult(
            success=success,
            broker_order_id=data.get("orderId", ""),
            message=data.get("message", ""),
        )

    async def modify_order(self, order_id: str, changes: dict) -> OrderResult:
        client = await self._get_client()
        order_type_str = changes.get("order_type", "LIMIT")
        product_str = changes.get("product", "INTRADAY")
        payload = {
            "dhanClientId": self._client_id,
            "orderId": order_id,
            "orderType": self._map_order_type_str(order_type_str),
            "productType": self._map_product_str(product_str),
            "validity": "DAY",
            "quantity": changes.get("quantity", 0),
            "price": changes.get("price", 0),
            "triggerPrice": changes.get("trigger_price", 0),
        }
        resp = await client.put(f"{self._base_url}/orders/{order_id}", json=payload, headers=self._headers(), timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout))
        data = resp.json()
        return OrderResult(
            success=data.get("status") == "success",
            broker_order_id=order_id,
            message=data.get("message", ""),
        )

    async def cancel_order(self, order_id: str) -> OrderResult:
        client = await self._get_client()
        resp = await client.delete(f"{self._base_url}/orders/{order_id}", headers=self._headers(), timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout))
        data = resp.json()
        success = data.get("status") == "success"
        return OrderResult(
            success=success,
            broker_order_id=order_id,
            message=data.get("message", ""),
        )

    async def get_orderbook(self) -> list[NormalizedOrder]:
        client = await self._get_client()
        resp = await client.get(f"{self._base_url}/orders", headers=self._headers(), timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout))
        data = resp.json()
        items = data if isinstance(data, list) else data.get("data", [])
        return [self._normalize_order(item) for item in items]

    async def get_positions(self) -> list[Position]:
        client = await self._get_client()
        resp = await client.get(f"{self._base_url}/positions", headers=self._headers(), timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout))
        data = resp.json()
        items = data if isinstance(data, list) else data.get("data", [])
        return [self._normalize_position(item) for item in items]

    async def get_holdings(self) -> list[Holding]:
        client = await self._get_client()
        resp = await client.get(f"{self._base_url}/holdings", headers=self._headers(), timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout))
        data = resp.json()
        items = data if isinstance(data, list) else data.get("data", [])
        if not items and isinstance(data, dict) and "errorMessage" in data:
            return []
        return [self._normalize_holding(item) for item in items]

    async def get_funds(self) -> Funds:
        client = await self._get_client()
        resp = await client.get(f"{self._base_url}/fundlimit", headers=self._headers(), timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout))
        data = resp.json()
        total = float(data.get("sodLimit", data.get("totalBalance", 0)))
        used = float(data.get("utilizedAmount", data.get("usedBalance", 0)))
        avail = float(data.get("availableBalance", data.get("availabelBalance", 0)))
        return Funds(
            total_margin=total,
            used_margin=used,
            available_margin=avail,
            broker=self.broker_name,
        )

    async def get_quotes(self, symbols: list[str]) -> list[Quote]:
        client = await self._get_client()
        resp = await client.get(
            f"{self._base_url}/quotes", params={"symbols": ",".join(symbols)}, headers=self._headers(),
            timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
        )
        data = resp.json()
        quotes = []
        items = data.get("data", [])
        for i, item in enumerate(items):
            orig = symbols[i] if i < len(symbols) else item.get("securityId", "")
            quotes.append(self._normalize_quote(item, orig))
        return quotes

    async def get_historical(
        self, symbol: str, interval: str, start: str | None = None, end: str | None = None, range: str | None = None
    ) -> list[Candle]:
        client = await self._get_client()
        params = {"securityId": symbol, "exchangeSegment": "NSE", "interval": interval}
        if start:
            params["from"] = start
        if end:
            params["to"] = end
        resp = await client.get(f"{self._base_url}/charts/historical", params=params, headers=self._headers(), timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout))
        data = resp.json()
        candles = []
        for item in data.get("data", []):
            candles.append(
                Candle(
                    symbol=symbol,
                    exchange=Exchange.NSE,
                    interval=interval,
                    open=float(item.get("open", 0)),
                    high=float(item.get("high", 0)),
                    low=float(item.get("low", 0)),
                    close=float(item.get("close", 0)),
                    volume=int(item.get("volume", 0)),
                    timestamp=datetime.fromisoformat(item.get("timestamp", "")),
                )
            )
        return candles

    async def stream(self, symbols: list[str], on_tick: Callable[[Tick], None]) -> None:
        """Stream live ticks by delegating to the one verified Dhan feed.

        This method used to hold a second, independent Dhan websocket implementation. It
        was wrong in seven ways at once, and every one of them failed silently:

          * ``httpx.AsyncClient.stream()`` cannot upgrade to a websocket -- the upgrade
            handshake does not exist in httpx, so the request could never become one.
          * ``wss://api.dhan.co/v2/ws`` is the wrong host *and* the wrong path. Dhan's feed
            is ``wss://api-feed.dhan.co``; ``api.dhan.co`` serves no websocket at all.
          * ``RequestCode: 1`` is not a v2 subscription code (v2 uses 15/17/21).
          * ``SecurityToken`` is not a v2 field name; v2 uses ``SecurityId``.
          * ``ExchangeSegment`` was hardcoded to ``NSE_EQ``, so a derivative could never be
            subscribed even when handed a correct id.
          * The display symbol was sent where the broker-assigned security id belongs.
          * Dhan's v2 feed emits *binary* packets, but this read the body as JSON lines, so
            ``json.loads`` threw on every packet and ``continue`` swallowed all of them.

        It then retried forever on a capped backoff, so a Dhan feed looked connected and
        delivered nothing. `market/dhan_feed.py` is the verified implementation -- proven
        against Dhan's live server, with the real protocol, the real binary decoding, and
        the CA bundle named explicitly. There is now exactly one Dhan feed in the codebase
        and this method only forwards to it.

        This was not dead code: `market/data_socket.py` calls `adapter.stream(...)` on
        broker-feed startup, so the stale copy was the path every Dhan market-data feed
        actually took.
        """
        if not self._access_token:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        from market.dhan_feed import DhanMarketFeed, FeedMode, subscription_for_instrument
        from market.instruments import instrument_resolver

        # A symbol becomes a subscription only via resolved contract metadata. No default
        # segment, no display-symbol fallback: an unresolvable symbol is refused and
        # named, because defaulting it to NSE_EQ is precisely how this method was wrong.
        subscriptions, symbol_of, refused = [], {}, []
        for symbol in symbols:
            instrument = None
            for candidate_type in ("OPT", "FUT", "EQ"):
                try:
                    instrument = instrument_resolver.resolve(
                        symbol, broker=self.broker_name, instrument_type=candidate_type,
                    )
                except Exception:  # noqa: BLE001 - a provider failure is a refusal, not a crash
                    instrument = None
                if instrument is not None:
                    break
            if instrument is None or not instrument.security_id:
                refused.append(symbol)
                continue
            sub = subscription_for_instrument(instrument, mode=FeedMode.QUOTE)
            subscriptions.append(sub)
            symbol_of[sub.identity] = symbol

        if refused:
            logger.error(
                "Dhan feed refused %d symbol(s) with no authoritative metadata (not "
                "subscribed, never defaulted to NSE_EQ): %s",
                len(refused), ", ".join(refused[:10]),
            )
        if not subscriptions:
            raise RuntimeError(
                "No Dhan symbol resolved to contract metadata, so no feed was opened. "
                f"Refused: {refused[:10]}"
            )

        async def _emit(event) -> None:
            # A packet carrying no price is not a tick. Forwarding it would publish a
            # zero last_price, which every downstream consumer reads as a real quote.
            if event.ltp is None:
                return
            tick = Tick(
                symbol=symbol_of.get(event.identity, event.security_id),
                exchange=Exchange.NSE,
                last_price=float(event.ltp),
                bid=float(event.bid) if event.bid is not None else 0.0,
                ask=float(event.ask) if event.ask is not None else 0.0,
                bid_qty=int(event.bid_quantity) if event.bid_quantity is not None else 0,
                ask_qty=int(event.ask_quantity) if event.ask_quantity is not None else 0,
                volume=int(event.volume) if event.volume is not None else 0,
                oi=int(event.open_interest) if event.open_interest is not None else 0,
                timestamp=event.timestamp or datetime.now(UTC),
                broker=self.broker_name,
            )
            if inspect.iscoroutinefunction(on_tick):
                await on_tick(tick)
            else:
                on_tick(tick)

        feed = DhanMarketFeed(self._access_token, self._client_id, on_event=_emit)
        feed.subscribe(subscriptions)
        self._feed = feed
        self._running = True
        try:
            await feed.run()
        finally:
            self._running = False
            self._feed = None

    async def disconnect(self) -> None:
        self._running = False
        feed = getattr(self, "_feed", None)
        if feed is not None:
            try:
                await feed.stop()
            except Exception:  # noqa: BLE001 - shutdown must not mask the original error
                logger.debug("Dhan feed stop raised during disconnect", exc_info=True)
        await self.close_http_client()

    def _parse_tick(self, data: dict) -> Tick | None:
        try:
            return Tick(
                symbol=data.get("securityId", ""),
                exchange=Exchange.NSE,
                last_price=float(data.get("lastPrice", 0)),
                bid=float(data.get("bidPrice", 0)),
                ask=float(data.get("askPrice", 0)),
                bid_qty=int(data.get("bidQty", 0)),
                ask_qty=int(data.get("askQty", 0)),
                volume=int(data.get("volume", 0)),
                oi=int(data.get("openInterest", 0)),
                timestamp=datetime.now(UTC),
                broker=self.broker_name,
            )
        except (ValueError, KeyError, TypeError) as e:
            logger.warning("Failed to parse Dhan tick: %s", e)
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
        return mapping.get(ot.upper(), "MARKET")

    @staticmethod
    def _unmap_order_type(val: str) -> OrderType:
        mapping = {"MARKET": OrderType.MARKET, "LIMIT": OrderType.LIMIT, "STOP_LOSS": OrderType.SL, "STOP_LOSS_MARKET": OrderType.SLM}
        return mapping.get(val.upper(), OrderType.MARKET)

    @staticmethod
    def _map_product(p: ProductType) -> str:
        mapping = {ProductType.INTRADAY: "INTRADAY", ProductType.DELIVERY: "DELIVERY", ProductType.MIS: "INTRADAY", ProductType.NRML: "DELIVERY"}
        return mapping.get(p, "INTRADAY")

    @staticmethod
    def _map_product_str(p: str) -> str:
        mapping = {"INTRADAY": "INTRADAY", "DELIVERY": "DELIVERY", "MIS": "INTRADAY", "NRML": "DELIVERY"}
        return mapping.get(p.upper(), "INTRADAY")

    @staticmethod
    def _unmap_product(val: str) -> ProductType:
        """Dhan product type -> the local vocabulary.

        `CNC` and `MARGIN` were missing, so both silently became INTRADAY through the
        fallback. That made a delivery position and a margin position indistinguishable
        from an intraday one -- three different product types collapsed into one, which is
        exactly what position reconciliation must not lose. An unknown value still falls back
        to INTRADAY, because refusing to record a position at all is worse than recording it
        under the wrong product: the quantity and identity remain correct and a human can see
        the product is unrecognised.
        """
        mapping = {
            "INTRADAY": ProductType.INTRADAY,
            "MIS": ProductType.INTRADAY,
            "DELIVERY": ProductType.DELIVERY,
            "CNC": ProductType.DELIVERY,
            "NRML": ProductType.NRML,
            "MARGIN": ProductType.NRML,
        }
        return mapping.get(val.upper(), ProductType.INTRADAY)

    def _normalize_order(self, item: dict) -> NormalizedOrder:
        inst = self._parse_instrument(item.get("securityId", ""))
        return NormalizedOrder(
            id=item.get("orderId", ""),
            broker_order_id=item.get("orderId", ""),
            symbol=item.get("securityId", ""),
            exchange=Exchange(item.get("exchange", "NSE")),
            side=OrderSide.BUY if item.get("transactionType") == "BUY" else OrderSide.SELL,
            order_type=self._unmap_order_type(str(item.get("orderType", "MARKET"))),
            product=self._unmap_product(str(item.get("productType", "INTRADAY"))),
            quantity=int(item.get("quantity", 0)),
            price=float(item.get("price", 0)),
            trigger_price=float(item.get("triggerPrice", 0)) if item.get("triggerPrice") else None,
            status=self._map_status(item.get("orderStatus", "")),
            filled_quantity=int(item.get("filledQuantity", 0)),
            average_price=float(item.get("averageTradedPrice", 0)),
            broker=self.broker_name,
            instrument_type=inst["instrument_type"],
            strike_price=inst["strike_price"],
            expiry_date=inst["expiry_date"],
            option_type=inst["option_type"],
        )

    def _normalize_position(self, item: dict) -> Position:
        """Normalise one Dhan position.

        This used to store the broker's `securityId` in `symbol` and then feed that same
        string to `_parse_instrument`, which matches a Fyers-style compact symbol like
        `NIFTY26OCT23250CE`. A five-digit security id matches nothing, so **every** Dhan
        option position was recorded as `EQ` with no strike, no expiry and no option type,
        labelled with a number. Reconciliation therefore had nothing to match on: two
        different option contracts, or the same contract in two segments, were
        indistinguishable in local state.

        The contract identity now comes from the Dhan instrument master by
        `(exchange_segment, security_id)`, which is the key the master itself is indexed
        on, and the broker's own `productType` is honoured rather than assumed to be
        INTRADAY.
        """
        security_id = str(item.get("securityId", "") or "")
        segment = str(item.get("exchangeSegment", "") or "")
        symbol = security_id
        inst = {"instrument_type": InstrumentType.EQ, "strike_price": None,
                "expiry_date": None, "option_type": None}
        lot = 1.0
        if security_id:
            try:
                from market.dhan_instruments import dhan_instrument_provider

                # Resolved by (exchange_segment, security_id) -- the key the Dhan master is
                # indexed on. Resolving by symbol alone cannot work here, because the broker
                # gave us an id, not a symbol.
                resolved = dhan_instrument_provider.resolve_by_security_id(
                    security_id, exchange_segment=segment,
                )
                if resolved is not None:
                    symbol = resolved.broker_symbol or resolved.security_id
                    inst = {
                        "instrument_type": (InstrumentType(resolved.instrument_type)
                                            if resolved.instrument_type else
                                            InstrumentType.EQ),
                        "strike_price": resolved.strike,
                        "expiry_date": resolved.expiry,
                        "option_type": (OptionType(resolved.option_type)
                                        if resolved.option_type else None),
                    }
                    lot = float(resolved.lot_size or 1.0)
            except Exception as e:  # noqa: BLE001 - keep the raw identity rather than guess
                logger.warning("Could not resolve Dhan position %s/%s: %s",
                               segment, security_id, e)

        product = ProductType.INTRADAY
        raw_product = str(item.get("productType", "") or "").upper()
        if raw_product:
            mapped = self._unmap_product(raw_product)
            if mapped is not None:
                product = mapped

        return Position(
            symbol=symbol,
            security_id=security_id,
            exchange_segment=segment,
            exchange=Exchange(item.get("exchange", "NSE")),
            quantity=int(item.get("netQty", 0)),
            buy_quantity=int(item.get("buyQty", 0)),
            sell_quantity=int(item.get("sellQty", 0)),
            average_buy_price=float(item.get("avgBuyPrice", 0)),
            average_sell_price=float(item.get("avgSellPrice", 0)),
            unrealised_pnl=float(item.get("unrealizedPnl", 0)),
            realised_pnl=float(item.get("realizedPnl", 0)),
            product=product,
            multiplier=lot,
            broker=self.broker_name,
            instrument_type=inst["instrument_type"],
            strike_price=inst["strike_price"],
            expiry_date=inst["expiry_date"],
            option_type=inst["option_type"],
        )

    def _normalize_holding(self, item: dict) -> Holding:
        return Holding(
            symbol=item.get("securityId", ""),
            exchange=Exchange.NSE,
            quantity=int(item.get("quantity", 0)),
            average_price=float(item.get("averagePrice", 0)),
            current_price=float(item.get("currentPrice", 0)),
            pnl=float(item.get("pnl", 0)),
            broker=self.broker_name,
        )

    def _normalize_quote(self, item: dict, symbol: str = "") -> Quote:
        sym = symbol or item.get("securityId", "")
        inst = self._parse_instrument(sym)
        return Quote(
            symbol=sym,
            exchange=Exchange(item.get("exchange", "NSE")),
            last_price=float(item.get("lastPrice", 0)),
            open=float(item.get("open", 0)),
            high=float(item.get("high", 0)),
            low=float(item.get("low", 0)),
            close=float(item.get("close", 0)),
            volume=int(item.get("volume", 0)),
            bid=float(item.get("bid", 0)),
            ask=float(item.get("ask", 0)),
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
            "TRIGGER_PENDING": OrderStatus.PENDING,
            "FILLED": OrderStatus.FILLED,
            "CANCELLED": OrderStatus.CANCELLED,
            "REJECTED": OrderStatus.REJECTED,
        }
        return mapping.get(status.upper(), OrderStatus.PENDING)
