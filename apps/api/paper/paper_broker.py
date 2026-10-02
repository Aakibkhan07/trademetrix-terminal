import asyncio
import logging
import time
from datetime import UTC, datetime

from core.db import get_supabase
from core.models import (
    Exchange, Funds, NormalizedOrder,
    OrderResult, OrderSide, OrderStatus, OrderType, Position, ProductType,
)
from execution.event_bus import execution_event_bus, ExecutionEvent, fire_and_forget
from execution.models import BrokerCapabilities
from paper.fill_engine import FillEngine
from paper.models import (
    PaperAccount,
    PaperConfig,
    PaperFill,
    PaperOrderStatus,
    PaperPosition,
)
from paper.observability import paper_metrics

logger = logging.getLogger(__name__)

PAPER_BROKER = "paper"

_paper_broker_instances: dict[str, "PaperBroker"] = {}


def get_paper_broker(user_id: str) -> "PaperBroker":
    if user_id not in _paper_broker_instances:
        _paper_broker_instances[user_id] = PaperBroker(user_id)
    return _paper_broker_instances[user_id]


class PaperBroker:
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.broker = PAPER_BROKER
        self._config = PaperConfig()
        self._fill_engine = FillEngine(self._config)
        self._orders: dict[str, dict] = {}
        self._positions: dict[str, PaperPosition] = {}
        self._account = PaperAccount(user_id=user_id)
        self._authenticated = False
        self._connected = False
        self._order_counter = 0

    async def _ensure_quote(self, symbol: str) -> None:
        try:
            from market.cache import market_cache
            cached = market_cache.get_quote(symbol)
            if cached and (cached.get("last_price") or cached.get("ltp")):
                return
            from brokers.token_manager import TokenManager
            from brokers.fyers_adapter import FyersAdapter
            from core.models import Quote
            tm = TokenManager(self.user_id, "fyers")
            session = await tm.get_session()
            adapter = FyersAdapter()
            await adapter.authenticate({
                "client_id": session.get("client_id", ""),
                "access_token": session.get("access_token", ""),
            })
            quotes = await adapter.get_quotes([symbol])
            if quotes:
                q = quotes[0]
                if getattr(q, "last_price", 0) > 0:
                    market_cache.put_quote(symbol, q.model_dump(mode="json"))
                    logger.info("Paper quote primed for %s: %.2f", symbol, q.last_price)
                    return
        except Exception as e:
            logger.warning("Paper quote priming failed for %s: %s", symbol, e)

        # Yahoo fallback, the same provider `GET /marketdata/quote` uses to fill whatever the
        # broker did not price.
        #
        # Without it the only sources were the in-process cache and Fyers, so a tenant with no
        # broker token — every paper-only user, and any user whose token has expired — got a fill at
        # **price zero**. `execution_engine/trades.py` then skipped the trade for exactly that reason,
        # so the order was recorded as FILLED with `average_price = 0` while no position was ever
        # created: an audit trail claiming a fill that never happened, at no price.
        #
        # Yahoo prices are real market data, not a substitute or a simulation, so using them here is
        # the same trade the quote route already makes — broker first, Yahoo for the rest. It is not
        # a way to make an unfillable order fill: if neither source has a price the order still goes
        # out unfilled, which is the honest outcome.
        try:
            from providers.yahoo import fetch_quotes
            yq = await fetch_quotes([symbol])
            if yq:
                last = getattr(yq[0], "last_price", 0) or 0
                if last > 0:
                    market_cache.put_quote(symbol, yq[0].model_dump(mode="json"))
                    logger.info("Paper quote for %s from Yahoo: %.2f", symbol, last)
        except Exception as e:
            logger.warning("Yahoo fallback for paper quote %s failed: %s", symbol, e)

    async def connect(self) -> bool:
        self._authenticated = True
        self._connected = True
        self._account.initial_capital = self._config.initial_capital
        self._account.total_margin = self._config.initial_capital
        self._account.available_margin = self._config.initial_capital
        self._account.current_value = self._config.initial_capital
        await self._restore_positions()
        logger.info("PaperBroker connected for user %s (capital: %.2f)", self.user_id, self._config.initial_capital)
        return True

    async def _restore_positions(self) -> None:
        try:
            from core.db import get_supabase
            from core.safe_query import async_safe_execute
            supabase = get_supabase()
            rows = await async_safe_execute(
                supabase.table("orders")
                .select("*")
                .eq("user_id", self.user_id)
                .eq("broker", PAPER_BROKER)
                .eq("status", "FILLED")
                .order("created_at")
            )
            if not rows:
                return

            self._positions = {}
            self._orders = {}

            for row in rows:
                order = NormalizedOrder(
                    symbol=row.get("symbol", ""),
                    exchange=Exchange(row.get("exchange", "NSE")),
                    side=OrderSide(row.get("side", "BUY")),
                    order_type=OrderType(row.get("order_type", "MARKET")),
                    product=ProductType(row.get("product", "INTRADAY")),
                    quantity=row.get("quantity", 0),
                    price=row.get("price", 0.0),
                    trigger_price=row.get("trigger_price"),
                    broker=PAPER_BROKER,
                    broker_order_id=row.get("broker_order_id", ""),
                    filled_quantity=row.get("filled_quantity", 0),
                    average_price=row.get("average_price", 0.0),
                    user_id=self.user_id,
                    is_paper=True,
                    status=OrderStatus.FILLED,
                )
                fill = PaperFill(
                    filled_quantity=order.filled_quantity or order.quantity,
                    filled_price=order.average_price or order.price or 0,
                    order_id=order.broker_order_id or "",
                )
                self._update_position(order, fill)
                self._update_account(order, fill)
                order_id = order.broker_order_id or order.client_order_id or str(int(time.time()))
                self._orders[order_id] = {
                    "order": order,
                    "status": PaperOrderStatus.FILLED,
                    "fills": [fill],
                    "created_at": datetime.now(UTC),
                }
            logger.info(
                "Restored %d filled orders, %d positions for paper user %s",
                len(self._orders), len(self._positions), self.user_id,
            )
        except Exception as e:
            logger.error("Failed to restore paper positions for user %s: %s", self.user_id, e)

    async def disconnect(self):
        self._authenticated = False
        self._connected = False
        logger.info("PaperBroker disconnected for user %s", self.user_id)

    async def health(self) -> dict:
        return {
            "broker": PAPER_BROKER,
            "authenticated": self._authenticated,
            "connected": self._connected,
            "paper": True,
            "capital": self._account.initial_capital,
            "available_margin": self._account.available_margin,
        }

    def capabilities(self) -> BrokerCapabilities:
        return BrokerCapabilities(
            broker=PAPER_BROKER,
            supports_orders=True,
            supports_modify=True,
            supports_cancel=True,
            supports_bracket=False,
            supports_cover=False,
            supports_gtt=False,
            supports_websocket=False,
            supports_option_chain=False,
            supports_positions=True,
            supports_holdings=True,
        )

    async def place_order(self, order: NormalizedOrder) -> OrderResult:
        start = time.monotonic()
        self._order_counter += 1
        order_id = f"paper_{self._order_counter}_{int(time.time())}"
        order.broker_order_id = order_id
        order.broker = PAPER_BROKER

        await asyncio.sleep(self._config.broker_delay_ms / 1000)

        if not await self._check_margin(order):
            paper_metrics.record_rejected()
            return OrderResult(
                success=False, broker_order_id=order_id, order=order,
                message="Insufficient margin", status="rejected",
            )

        await self._ensure_quote(order.symbol)
        fill = await self._fill_engine.simulate_fill(order, self.user_id)

        if fill.filled_quantity <= 0:
            self._orders[order_id] = {
                "order": order, "status": PaperOrderStatus.PENDING, "fills": [],
                "created_at": datetime.now(UTC),
            }
            paper_metrics.record_order()
            self._publish_event("PaperOrderPending", order, order_id, fill)
            return OrderResult(
                success=True, broker_order_id=order_id, order=order,
                message="Order pending (limit/stop not triggered)", status="pending",
            )

        is_partial = fill.filled_quantity < order.quantity
        self._update_position(order, fill)
        self._update_account(order, fill)
        self._orders[order_id] = {
            "order": order, "status": PaperOrderStatus.FILLED, "fills": [fill],
            "created_at": datetime.now(UTC),
        }

        order.status = OrderStatus.PARTIALLY_FILLED if is_partial else OrderStatus.FILLED
        order.filled_quantity = fill.filled_quantity
        order.average_price = fill.filled_price
        order.filled_at = datetime.now(UTC)

        self._persist_order(order, fill)
        paper_metrics.record_fill()

        elapsed_ms = (time.monotonic() - start) * 1000
        event_type = "PaperOrderPartiallyFilled" if is_partial else "PaperOrderFilled"
        self._publish_event(event_type, order, order_id, fill)

        state = "partially_filled" if is_partial else "filled"
        return OrderResult(
            success=True, broker_order_id=order_id, order=order,
            message=f"Paper order {'partially filled' if is_partial else 'filled'} {fill.filled_quantity} @ {fill.filled_price:.2f}",
            status=state, filled_qty=fill.filled_quantity, avg_price=fill.filled_price,
        )

    async def modify_order(self, order_id: str, changes: dict) -> OrderResult:
        existing = self._orders.get(order_id)
        if not existing:
            return OrderResult(success=False, message="Order not found")

        order = existing["order"]
        if "quantity" in changes:
            order.quantity = changes["quantity"]
        if "price" in changes:
            order.price = changes["price"]
        if "trigger_price" in changes:
            order.trigger_price = changes["trigger_price"]

        return OrderResult(success=True, broker_order_id=order_id, order=order, message="Order modified")

    async def cancel_order(self, order_id: str) -> OrderResult:
        existing = self._orders.get(order_id)
        if not existing:
            return OrderResult(success=False, message="Order not found")

        existing["status"] = PaperOrderStatus.CANCELLED
        paper_metrics.record_cancelled()
        self._publish_event("PaperOrderRejected", existing["order"], order_id)
        return OrderResult(success=True, broker_order_id=order_id, message="Order cancelled")

    async def get_order(self, order_id: str) -> NormalizedOrder | None:
        existing = self._orders.get(order_id)
        return existing["order"] if existing else None

    async def get_orders(self) -> list[NormalizedOrder]:
        return [o["order"] for o in self._orders.values()]

    async def get_orderbook(self) -> list[NormalizedOrder]:
        return await self.get_orders()

    async def get_positions(self) -> list:
        import random
        from market.status import market_status_service
        is_open = market_status_service.is_market_open()
        positions = []
        for symbol, pos in self._positions.items():
            base = pos.last_price if pos.last_price and pos.last_price > 0 else pos.average_buy_price if pos.average_buy_price > 0 else pos.average_sell_price if pos.average_sell_price > 0 else 80.0
            sl = pos.average_buy_price * 0.7 if pos.average_buy_price > 0 else 0
            target = pos.average_buy_price + (pos.average_buy_price - sl) * 3.0 if pos.average_buy_price > 0 else 0
            hit = (base <= sl and sl > 0) or (base >= target and target > 0)
            if is_open and not hit and base and base > 0:
                jitter = random.uniform(-0.015, 0.015)
                pos.last_price = round(max(5.0, base * (1 + jitter)), 2)
                pos.unrealised_pnl = pos.quantity * (pos.last_price - pos.average_buy_price) if pos.quantity > 0 else abs(pos.quantity) * (pos.average_sell_price - pos.last_price) if pos.quantity < 0 else 0.0
                pos.m2m = pos.realised_pnl + pos.unrealised_pnl
            positions.append(self._to_position_model(pos))
        return positions

    async def get_holdings(self) -> list:
        return []

    async def get_funds(self) -> Funds:
        return Funds(
            total_margin=self._account.total_margin,
            used_margin=self._account.used_margin,
            available_margin=self._account.available_margin,
            payin=self._account.payin,
            payout=self._account.payout,
            broker=PAPER_BROKER,
        )

    async def validate_order(self, order: NormalizedOrder) -> dict:
        errors = []
        if not order.symbol:
            errors.append({"field": "symbol", "message": "Symbol is required"})
        if order.quantity <= 0:
            errors.append({"field": "quantity", "message": "Quantity must be positive"})
        if order.order_type in (OrderType.LIMIT, OrderType.SL, OrderType.SLM) and order.price <= 0:
            errors.append({"field": "price", "message": "Price required for LIMIT/SL orders"})
        return {"valid": len(errors) == 0, "errors": errors}

    def update_config(self, config: PaperConfig) -> None:
        self._config = config
        self._fill_engine = FillEngine(config)
        self._account.initial_capital = config.initial_capital
        self._account.total_margin = config.initial_capital
        self._account.available_margin = config.initial_capital
        self._account.current_value = config.initial_capital

    def get_config(self) -> PaperConfig:
        return self._config

    def get_metrics(self) -> dict:
        return paper_metrics.stats

    def _update_position(self, order: NormalizedOrder, fill: PaperFill) -> None:
        symbol = order.symbol
        pos = self._positions.get(symbol)
        if not pos:
            pos = PaperPosition(symbol=symbol, product=order.product.value if hasattr(order.product, "value") else "INTRADAY")
            self._positions[symbol] = pos

        side = order.side.value if hasattr(order.side, "value") else str(order.side)
        qty = fill.filled_quantity
        price = fill.filled_price

        if side == "BUY":
            new_buy_qty = pos.buy_quantity + qty
            pos.average_buy_price = ((pos.average_buy_price * pos.buy_quantity) + (price * qty)) / max(new_buy_qty, 1)
            pos.buy_quantity = new_buy_qty
            pos.quantity = pos.buy_quantity - pos.sell_quantity
        else:
            new_sell_qty = pos.sell_quantity + qty
            pos.average_sell_price = ((pos.average_sell_price * pos.sell_quantity) + (price * qty)) / max(new_sell_qty, 1)
            pos.sell_quantity = new_sell_qty
            pos.quantity = pos.buy_quantity - pos.sell_quantity

        if pos.quantity == 0:
            pos.realised_pnl += (pos.average_sell_price - pos.average_buy_price) * min(pos.buy_quantity, pos.sell_quantity)
            pos.buy_quantity = 0
            pos.sell_quantity = 0

        pos.last_price = price
        pos.unrealised_pnl = pos.quantity * (price - pos.average_buy_price) if pos.quantity > 0 else \
                             abs(pos.quantity) * (pos.average_sell_price - price) if pos.quantity < 0 else 0.0
        pos.m2m = pos.realised_pnl + pos.unrealised_pnl

        self._publish_event("PaperPositionUpdated", order, fill.order_id)

    def _update_account(self, order: NormalizedOrder, fill: PaperFill) -> None:
        gross = fill.filled_quantity * fill.filled_price
        if order.side == OrderSide.SELL:
            self._account.available_margin += gross
        else:
            self._account.used_margin += gross
        self._account.available_margin = self._account.total_margin - self._account.used_margin
        self._account.m2m_unrealised = sum(p.unrealised_pnl for p in self._positions.values())
        self._account.current_value = self._account.total_margin + self._account.m2m_unrealised

    async def _check_margin(self, order: NormalizedOrder) -> bool:
        price = order.price if order.price and order.price > 0 else order.trigger_price or 0
        if price <= 0:
            price = 100.0
        required = order.quantity * price
        if required > self._account.available_margin:
            logger.warning("Insufficient paper margin: need %.2f, have %.2f", required, self._account.available_margin)
            return False
        return True

    def _to_position_model(self, pos: PaperPosition) -> Position:
        exch = Exchange.BSE if "SENSEX" in (pos.symbol or "").upper() else Exchange.NSE
        return Position(
            symbol=pos.symbol,
            exchange=exch,
            quantity=pos.quantity,
            buy_quantity=pos.buy_quantity,
            sell_quantity=pos.sell_quantity,
            average_buy_price=pos.average_buy_price,
            average_sell_price=pos.average_sell_price,
            unrealised_pnl=pos.unrealised_pnl,
            realised_pnl=pos.realised_pnl,
            m2m=pos.m2m,
            product=ProductType.INTRADAY,
            multiplier=pos.multiplier,
            broker=PAPER_BROKER,
            last_price=pos.last_price,
        )

    def _persist_order(self, order: NormalizedOrder, fill: PaperFill) -> None:
        """Write the paper broker's view of an order to the shared `orders` table.

        Why delete-then-insert rather than `upsert(..., on_conflict="user_id,client_order_id")`:

        That upsert could never work here. `orders` carries **partial** unique indexes —

            CREATE UNIQUE INDEX idx_orders_client_order_id ON orders (user_id, client_order_id)
                WHERE (client_order_id <> '')

        and Postgres will only infer a conflict target from a partial index if the statement
        reproduces the index predicate. supabase-py has no way to send one, so every call failed:

            Failed to persist paper order: 42P10 — there is no unique or exclusion constraint
            matching the ON CONFLICT specification

        The index has to stay partial: `NormalizedOrder.id` defaults to `""` and is stripped from
        the payload, so most rows carry an empty `client_order_id` and a non-partial unique index
        over it would reject the second such row outright. The primary key is not an option either,
        for the same reason — `id` is absent from the payload.

        So the row is replaced explicitly. This writes to the same row `execution/manager.py`
        inserts into, keyed the same way, and `core/telegram.py` already establishes delete+insert
        as the workaround for this exact PostgREST limitation.
        """
        try:
            supabase = get_supabase()
            data = order.model_dump(mode="json")
            for field in ("id", "run_id", "signal_id", "validity", "disclosed_quantity"):
                if field in data and not data[field]:
                    del data[field]

            client_order_id = data.get("client_order_id") or ""
            if client_order_id:
                (
                    supabase.table("orders")
                    .delete()
                    .eq("user_id", data.get("user_id", ""))
                    .eq("client_order_id", client_order_id)
                    .execute()
                )
            supabase.table("orders").insert(data).execute()
        except Exception as e:
            logger.error("Failed to persist paper order: %s", e)

    def _publish_event(self, event_type: str, order: NormalizedOrder, order_id: str, fill: PaperFill | None = None):
        try:
            payload = {
                "order_id": order_id,
                "symbol": order.symbol,
                "side": order.side.value if hasattr(order.side, "value") else "",
                "quantity": order.quantity,
                "price": order.price,
                "broker": PAPER_BROKER,
                "paper": True,
            }
            if fill:
                payload["fill"] = fill.model_dump()
            event = ExecutionEvent(
                event_type=event_type,
                execution_request_id=order_id,
                user_id=self.user_id,
                broker=PAPER_BROKER,
                symbol=order.symbol,
                side=order.side.value if hasattr(order.side, "value") else "",
                payload=payload,
            )
            fire_and_forget(execution_event_bus.publish(event))
        except Exception as e:
            logger.error("Failed to publish paper event: %s", e)
