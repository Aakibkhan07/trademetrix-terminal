import asyncio
import hashlib
import logging
import time
from collections import OrderedDict
from datetime import UTC, datetime
from typing import Any

from execution.event_bus import execution_event_bus, ExecutionEvent, fire_and_forget
from execution.manager import ExecutionManager
from execution.models import ExecutionRequest, ExecutionState
from execution.retry import is_transient
from oms.models import (
    BracketOrder,
    OCOOrder,
    OMSOrderState,
    OmniOrder,
    OrderQueueItem,
    OrderRelationType,
)
from oms.observability import oms_metrics
from oms.order_queue import order_queue
from oms.persistence import (
    load_active_bracket_orders,
    load_active_oco_orders,
    load_active_orders,
    load_order,
    remove_order,
    save_bracket_order,
    save_oco_order,
    save_order,
)
from oms.state_machine import state_machine

logger = logging.getLogger(__name__)

PAPER_BROKER = "paper"
MAX_ACTIVE_ORDERS = 1000
RECONCILE_INTERVAL_SECONDS = 5
BRACKET_INTERVAL_SECONDS = 2
SL_PCT_DEFAULT = 0.10
RR_TARGET_DEFAULT = 1.5
QUOTE_CACHE_TTL = 2.0

EXIT_SOURCES = frozenset({"bracket_sl", "bracket_target", "exit_sl", "exit_target"})

TERMINAL_OMS_STATES = {
    OMSOrderState.FILLED,
    OMSOrderState.CANCELLED,
    OMSOrderState.REJECTED,
    OMSOrderState.EXPIRED,
}


def _text(value) -> str:
    """Normalise an enum member or plain value to its stored string form.

    `ExecutionRequest` carries these as pydantic enums while `OmniOrder` stores strings,
    because the row is written to a text column. ``InstrumentType.OPT`` has to become
    ``"OPT"``, and ``None`` has to become ``""`` so the column is never null.
    """
    if value is None:
        return ""
    return str(getattr(value, "value", value))


def build_execution_request(order: "OmniOrder") -> ExecutionRequest:
    """Rebuild the broker request from a persisted OMS order.

    Extracted from `_process_queue` so it can be exercised directly. While it was inline,
    the only way to test it was to run the worker against a live Redis and a broker
    adapter -- and a source-level assertion that the keyword names were present passed while
    `disclosed_quantity=order.disclosed_quantity or None` raised a `ValidationError` on every
    order whose disclosed quantity is 0, because 0 is falsy. The presence of a keyword is
    not the correctness of a keyword; only running it is.

    `disclosed_quantity` is coerced to 0 rather than `None` because
    `ExecutionRequest.disclosed_quantity` is a non-optional int.
    """
    return ExecutionRequest(
        user_id=order.user_id,
        broker=order.broker,
        symbol=order.symbol,
        exchange=order.exchange,
        side=order.side,
        order_type=order.order_type,
        product=order.product,
        quantity=order.quantity,
        price=order.price,
        trigger_price=order.trigger_price,
        # Restored from the persisted order. Without these the broker adapter had no
        # `instrument_type` and therefore emitted no `drvExpiryDate`, `drvStrikePrice` or
        # `drvOptionType` at all -- the two order paths disagreed about which contract was
        # being traded, and only the queue path is what production uses.
        # `instrument_type` and `validity` are non-optional on ExecutionRequest (they
        # default to "EQ" / "DAY"). `... or None` therefore raised a ValidationError on any
        # order whose stored value was empty -- which is exactly the case for an order
        # recovered from the database, where the columns are backfilled to "".
        # This is the same class of defect as the `disclosed_quantity` line above: coercing
        # an absent value to None for a field that is not Optional.
        instrument_type=order.instrument_type or "EQ",
        expiry_date=order.expiry_date or None,
        strike_price=order.strike_price,
        option_type=order.option_type or None,
        validity=order.validity or "DAY",
        disclosed_quantity=int(order.disclosed_quantity or 0),
        strategy_id=order.strategy_id or None,
        source=order.source,
        is_paper=order.is_paper,
        execution_request_id=order.execution_request_id,
    )


def _oms_order_id() -> str:
    raw = f"oms:{time.time_ns()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


class OrderManager:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, max_orders: int = MAX_ACTIVE_ORDERS):
        if self._initialized:
            return
        self._initialized = True
        self._orders: OrderedDict[str, OmniOrder] = OrderedDict()
        self._max_orders = max_orders
        self._bracket_orders: dict[str, BracketOrder] = {}
        self._oco_orders: dict[str, OCOOrder] = {}
        self._exec_mgr = ExecutionManager()
        self._processor_task: asyncio.Task | None = None
        self._reconciler_task: asyncio.Task | None = None
        self._bracket_task: asyncio.Task | None = None
        self._running = False
        self._completed: OrderedDict[str, OmniOrder] = OrderedDict()
        self._quote_cache: dict[tuple[str, str, str], tuple[float, float]] = {}
        self._quote_inflight: dict[tuple[str, str], asyncio.Task] = {}
        self._warn_since: dict[str, float] = {}

    def _log_throttled(self, fmt: str, symbol: str, *args) -> None:
        """Rate-limit repeated warning logs per symbol (a dead token would
        otherwise spam the same line every bracket cycle — 5542 lines/48h seen
        in prod)."""
        now = time.monotonic()
        if now - self._warn_since.get(symbol, 0.0) >= 60.0:
            self._warn_since[symbol] = now
            logger.warning(fmt, symbol, *args)

    async def start(self) -> None:
        await self._recover_active_orders()
        self._running = True
        self._processor_task = asyncio.create_task(self._process_queue())
        self._reconciler_task = asyncio.create_task(self._reconcile_loop())
        self._bracket_task = asyncio.create_task(self._bracket_loop())
        logger.info("OrderManager started")

    async def stop(self) -> None:
        self._running = False
        for task in (self._processor_task, self._reconciler_task, self._bracket_task):
            if task:
                task.cancel()
        self._processor_task = None
        self._reconciler_task = None
        self._bracket_task = None
        logger.info("OrderManager stopped")

    async def place_order(self, req: ExecutionRequest) -> OmniOrder:
        from oms.identity import intent_fingerprint

        oms_id = _oms_order_id()
        # Minted ONCE, here, and carried unchanged through every retry. It becomes
        # `client_order_id`, which the Dhan adapter sends as the `correlationId` header --
        # so it is the one identifier that survives a lost response and lets reconciliation
        # find the order. A retry must never mint a new one.
        exec_request_id = req.execution_request_id or oms_id

        order = OmniOrder(
            oms_order_id=oms_id,
            execution_request_id=exec_request_id,
            client_order_id=exec_request_id,
            user_id=req.user_id,
            broker=req.broker,
            symbol=req.symbol,
            exchange=req.exchange,
            side=req.side,
            order_type=req.order_type,
            product=req.product,
            quantity=req.quantity,
            price=req.price,
            trigger_price=req.trigger_price,
            # Derivative identity. Dropping these here is what made the queue path send an
            # option order to Dhan with no expiry, no strike and no option type, while a
            # direct ExecutionManager call carried all three. See `OmniOrder`.
            instrument_type=_text(req.instrument_type),
            expiry_date=_text(req.expiry_date),
            strike_price=float(req.strike_price) if req.strike_price else None,
            option_type=_text(req.option_type),
            validity=_text(req.validity),
            disclosed_quantity=int(req.disclosed_quantity or 0),
            strategy_id=req.strategy_id or "",
            source=req.source,
            is_paper=req.is_paper or (req.broker == PAPER_BROKER),
            state=OMSOrderState.NEW,
            # Recorded once. If a later attempt presents a different fingerprint, it is a new
            # order and goes through complete risk evaluation.
            intent_fingerprint=intent_fingerprint(req),
        )

        self._add_order(order)
        await save_order(order)
        oms_metrics.record_submitted()

        queue_item = OrderQueueItem(
            oms_order_id=oms_id,
            user_id=req.user_id,
            broker=req.broker,
            priority=0,
        )
        order.state = OMSOrderState.QUEUED
        order.updated_at = datetime.now(UTC)
        await save_order(order)
        await order_queue.enqueue(queue_item)

        self._publish_event("OrderQueued", order)
        return order

    async def place_and_wait(self, req: ExecutionRequest, timeout: float = 20.0) -> OmniOrder:
        """Enqueue an order and block until it leaves QUEUED/SENT (terminal or PENDING).

        Used by the engine path so strategy orders get the same OMS lifecycle
        (persistence, reconcile, recovery) while returning synchronously.
        """
        order = await self.place_order(req)
        oid = order.oms_order_id
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            current = self._orders.get(oid)
            if current and current.state not in (OMSOrderState.QUEUED, OMSOrderState.SENT):
                return current
            current = self._completed.get(oid) or await self._load_result(oid)
            if current and current.state not in (OMSOrderState.QUEUED, OMSOrderState.SENT):
                return current
            await asyncio.sleep(0.1)
        current = self._orders.get(oid) or self._completed.get(oid) or await self._load_result(oid) or order
        if current.state in (OMSOrderState.QUEUED, OMSOrderState.SENT):
            current.message = f"Order still {current.state.value} after {int(timeout)}s wait"
        return current

    async def _load_result(self, oms_order_id: str) -> OmniOrder | None:
        try:
            from core.cache import cache
            r = await cache.get_redis()
            if not r:
                return None
            raw = await r.get(f"oms:result:{oms_order_id}")
            if not raw:
                return None
            import json
            return OmniOrder(**json.loads(raw))
        except Exception:
            return None

    async def cancel_order(self, oms_order_id: str) -> OmniOrder | None:
        order = self._orders.get(oms_order_id)
        if not order:
            return None

        if not state_machine.can_transition(order.state, OMSOrderState.CANCELLED):
            logger.warning("Cannot cancel order %s in state %s", oms_order_id, order.state)
            order.message = f"Cannot cancel order in state {order.state.value}"
            return order

        if order.state == OMSOrderState.QUEUED:
            removed = await order_queue.remove(oms_order_id)
            if removed:
                order.state = OMSOrderState.CANCELLED
                order.cancelled_at = datetime.now(UTC)
                order.updated_at = datetime.now(UTC)
                oms_metrics.record_cancelled()
                await save_order(order)
                await remove_order(oms_order_id)
                await self._mirror_audit_status(order, OMSOrderState.CANCELLED)
                await self._deactivate_bracket(order.oms_order_id)
                self._publish_event("OrderCancelled", order)
                await self._cancel_oco_sibling(order)
                return order

        if not order.broker_order_id:
            order.state = OMSOrderState.CANCELLED
            order.cancelled_at = datetime.now(UTC)
            order.updated_at = datetime.now(UTC)
            oms_metrics.record_cancelled()
            await save_order(order)
            await remove_order(oms_order_id)
            await self._mirror_audit_status(order, OMSOrderState.CANCELLED)
            await self._deactivate_bracket(order.oms_order_id)
            self._publish_event("OrderCancelled", order)
            await self._cancel_oco_sibling(order)
            return order

        req = ExecutionRequest(
            user_id=order.user_id, broker=order.broker,
            symbol=order.symbol, exchange=order.exchange,
            side=order.side, quantity=order.quantity,
            source="oms_cancel",
        )
        exec_result = await self._exec_mgr.cancel_order(req, order.broker_order_id)
        if exec_result.success:
            order.state = OMSOrderState.CANCELLED
            order.cancelled_at = datetime.now(UTC)
            order.updated_at = datetime.now(UTC)
            order.message = exec_result.message
            oms_metrics.record_cancelled()
            await save_order(order)
            await remove_order(oms_order_id)
            await self._mirror_audit_status(order, OMSOrderState.CANCELLED)
            await self._deactivate_bracket(order.oms_order_id)
            self._publish_event("OrderCancelled", order)
        else:
            order.message = exec_result.message or "Cancel failed"
            order.updated_at = datetime.now(UTC)
            await save_order(order)
        await self._cancel_oco_sibling(order)
        return order

    async def _cancel_oco_sibling(self, order: OmniOrder) -> None:
        if order.relation_type != OrderRelationType.OCO:
            return
        for oco in list(self._oco_orders.values()):
            if not oco.active:
                continue
            is_a = oco.order_a_id == order.oms_order_id
            is_b = oco.order_b_id == order.oms_order_id
            if not is_a and not is_b:
                continue
            oco.active = False
            await save_oco_order(oco)
            sibling_id = oco.order_b_id if is_a else oco.order_a_id
            sibling = self._orders.get(sibling_id)
            if sibling and state_machine.can_transition(sibling.state, OMSOrderState.CANCELLED):
                sibling.state = OMSOrderState.CANCELLED
                sibling.cancelled_at = datetime.now(UTC)
                sibling.updated_at = datetime.now(UTC)
                oms_metrics.record_cancelled()
                await save_order(sibling)
                await remove_order(sibling_id)
                self._publish_event("OrderCancelled", sibling)
            break

    async def modify_order(self, oms_order_id: str, changes: dict) -> OmniOrder | None:
        order = self._orders.get(oms_order_id)
        if not order:
            return None
        if not state_machine.is_active(order.state):
            order.message = f"Cannot modify order in state {order.state.value}"
            return order
        if order.broker_order_id:
            req = ExecutionRequest(
                user_id=order.user_id, broker=order.broker,
                symbol=order.symbol, exchange=order.exchange,
                side=order.side, quantity=order.quantity,
                source="oms_modify",
            )
            exec_result = await self._exec_mgr.modify_order(req, order.broker_order_id, changes)
            if not exec_result.success:
                order.message = exec_result.message or "Modify failed"
                order.updated_at = datetime.now(UTC)
                await save_order(order)
                return order
        if "quantity" in changes:
            order.quantity = int(changes["quantity"])
        if "price" in changes:
            order.price = float(changes["price"])
        if "trigger_price" in changes:
            order.trigger_price = float(changes["trigger_price"])
        order.updated_at = datetime.now(UTC)
        order.message = "Order modified"
        await save_order(order)
        return order

    async def get_order(self, oms_order_id: str) -> OmniOrder | None:
        return self._orders.get(oms_order_id)

    async def get_orders_by_user(self, user_id: str) -> list[OmniOrder]:
        return [o for o in self._orders.values() if o.user_id == user_id]

    async def get_orders_by_state(self, state: OMSOrderState) -> list[OmniOrder]:
        return [o for o in self._orders.values() if o.state == state]

    async def get_active_orders(self, user_id: str) -> list[OmniOrder]:
        return [o for o in self._orders.values() if o.user_id == user_id and state_machine.is_active(o.state)]

    async def create_bracket(self, req: ExecutionRequest, sl_price: float, target_price: float, trailing_sl_pct: float = 0.0) -> list[OmniOrder]:
        parent = await self.place_order(req)
        parent.relation_type = OrderRelationType.BRACKET

        bracket = BracketOrder(
            oms_order_id=_oms_order_id(),
            parent_order_id=parent.oms_order_id,
            user_id=req.user_id,
            symbol=req.symbol,
            quantity=req.quantity,
            entry_price=req.price,
            stop_loss_price=sl_price,
            target_price=target_price,
            trailing_sl_pct=trailing_sl_pct,
            active=True,
        )
        self._bracket_orders[parent.oms_order_id] = bracket
        await save_bracket_order(bracket)
        oms_metrics.record_bracket()
        return [parent]

    async def create_oco(self, req_a: ExecutionRequest, req_b: ExecutionRequest) -> list[OmniOrder]:
        order_a = await self.place_order(req_a)
        order_b = await self.place_order(req_b)

        order_a.relation_type = OrderRelationType.OCO
        order_a.sibling_order_id = order_b.oms_order_id
        order_b.relation_type = OrderRelationType.OCO
        order_b.sibling_order_id = order_a.oms_order_id

        oco = OCOOrder(
            oms_order_id=_oms_order_id(),
            user_id=req_a.user_id,
            symbol=req_a.symbol,
            quantity=req_a.quantity,
            order_a_id=order_a.oms_order_id,
            order_b_id=order_b.oms_order_id,
            active=True,
        )
        self._oco_orders[oco.oms_order_id] = oco
        await save_oco_order(oco)
        oms_metrics.record_oco()
        return [order_a, order_b]

    async def retry_order(self, oms_order_id: str) -> OmniOrder | None:
        order = self._orders.get(oms_order_id)
        if not order:
            return None
        if order.retry_count >= order.max_retries:
            order.state = OMSOrderState.REJECTED
            order.message = "Max retries exceeded"
            order.updated_at = datetime.now(UTC)
            oms_metrics.record_rejected()
            await save_order(order)
            await remove_order(oms_order_id)
            return order

        queue_item = OrderQueueItem(
            oms_order_id=oms_order_id,
            user_id=order.user_id,
            broker=order.broker,
            priority=order.priority,
            retry_count=order.retry_count,
        )
        await order_queue.enqueue_retry(queue_item, delay_seconds=2.0 ** order.retry_count)
        order.retry_count += 1
        order.state = OMSOrderState.QUEUED
        order.updated_at = datetime.now(UTC)
        await save_order(order)
        oms_metrics.record_retry()
        return order

    async def stats(self) -> dict:
        queue_stats = await order_queue.stats()
        return {
            "total_orders": len(self._orders),
            "active_brackets": len(self._bracket_orders),
            "active_ocos": len(self._oco_orders),
            "queue": queue_stats.model_dump(),
            "metrics": oms_metrics.stats,
        }

    async def health(self) -> dict:
        running = self._running
        processor_alive = self._processor_task is not None and not self._processor_task.done()
        return {
            "status": "healthy" if running and processor_alive else "degraded",
            "running": running,
            "processor_alive": processor_alive,
            "total_orders": len(self._orders),
            "active_brackets": len(self._bracket_orders),
            "active_ocos": len(self._oco_orders),
        }

    async def _process_queue(self) -> None:
        while self._running:
            try:
                item = await order_queue.dequeue()
                if item is None:
                    await asyncio.sleep(0.1)
                    continue

                order = self._orders.get(item.oms_order_id)
                if not order:
                    row = await load_order(item.oms_order_id)
                    if row:
                        order = OmniOrder(**row)
                        self._add_order(order)
                        logger.info("Loaded order %s from DB (cross-process enqueue)", item.oms_order_id)
                    else:
                        await order_queue.complete(item.oms_order_id)
                        continue

                if not state_machine.can_transition(order.state, OMSOrderState.SENT):
                    await order_queue.complete(item.oms_order_id)
                    continue

                order.state = OMSOrderState.SENT
                order.sent_at = datetime.now(UTC)
                order.updated_at = datetime.now(UTC)
                await save_order(order)
                self._publish_event("OrderSent", order)

                req = build_execution_request(order)

                exec_start = time.monotonic()
                exec_result = await self._exec_mgr.place_order(req)
                latency_ms = (time.monotonic() - exec_start) * 1000

                order.latency_ms = latency_ms
                oms_metrics.record_broker_latency(order.broker, latency_ms)

                if exec_result.indeterminate:
                    # The broker never answered. This is not a rejection -- the request may
                    # be sitting at the broker right now -- so the order stops here and
                    # reconciliation decides. Retrying from this point is what produced
                    # duplicate orders: the previous code requeued immediately, and
                    # `retry_with_backoff` had already re-sent the POST up to three more
                    # times before this branch existed.
                    order.state = OMSOrderState.UNKNOWN
                    order.updated_at = datetime.now(UTC)
                    order.message = exec_result.message or "broker did not respond"
                    await save_order(order)
                    await order_queue.complete(item.oms_order_id)
                    self._publish_event("OrderUnknown", order)
                elif exec_result.success:
                    is_partial = exec_result.state == ExecutionState.PARTIALLY_FILLED
                    is_filled = exec_result.state == ExecutionState.FILLED
                    order.broker_order_id = exec_result.broker_order_id or ""
                    new_filled = exec_result.filled_qty or 0
                    order.filled_quantity = (order.filled_quantity or 0) + new_filled
                    if new_filled and exec_result.avg_price:
                        prev_filled = order.filled_quantity - new_filled
                        if prev_filled > 0:
                            order.average_price = (order.average_price * prev_filled + exec_result.avg_price * new_filled) / order.filled_quantity
                        else:
                            order.average_price = exec_result.avg_price
                    order.filled_at = datetime.now(UTC) if is_filled or is_partial else None
                    order.message = exec_result.message
                    if is_filled:
                        oms_metrics.record_filled(latency_ms)
                        order.state = OMSOrderState.FILLED
                        await save_order(order)
                        await remove_order(item.oms_order_id)
                        await self._attach_auto_bracket(order)
                        self._record_terminal(order)
                        self._publish_event("OrderCompleted", order)
                        await self._handle_parent_completion(order)
                    elif is_partial:
                        oms_metrics.record_partial()
                        remaining = order.quantity - new_filled
                        if remaining > 0:
                            order.quantity = remaining
                            order.state = OMSOrderState.QUEUED
                            await save_order(order)
                            await order_queue.enqueue_retry(item, delay_seconds=5)
                        else:
                            order.state = OMSOrderState.FILLED
                            await save_order(order)
                            await remove_order(item.oms_order_id)
                            await self._attach_auto_bracket(order)
                            self._record_terminal(order)
                            self._publish_event("OrderCompleted", order)
                    else:
                        order.state = OMSOrderState.PENDING
                        await save_order(order)
                        self._publish_event("OrderPending", order)
                else:
                    # A definitive failure -- the broker answered and refused. The case where
                    # the broker did *not* answer is the `indeterminate` branch above, and
                    # that one must never reach this retry: it reconciles instead.
                    #
                    # A definitive answer is only retryable if it is also *transient*. The
                    # retry budget used to be the only condition, so a `VALIDATION_FAILED`
                    # was re-executed 4x against unchanged inputs -- measured on a live Dhan
                    # option order: attempts 1, 2 and 3, all rejected identically. Worse, a
                    # broker-level refusal such as MARGIN_INSUFFICIENT or ORDER_REJECTED
                    # would re-POST a new order to the broker, which is precisely the
                    # duplicate-order hazard this module exists to prevent. An unknown code
                    # is treated as non-transient: re-sending is the riskier direction.
                    retryable = (
                        order.retry_count < order.max_retries
                        and is_transient(exec_result.error_code or "")
                    )
                    if retryable:
                        order.state = OMSOrderState.QUEUED
                        await order_queue.enqueue_retry(item, delay_seconds=2.0 ** order.retry_count)
                        order.retry_count += 1
                        order.message = f"Retrying: {exec_result.message}"
                        oms_metrics.record_retry()
                        await save_order(order)
                    else:
                        order.state = OMSOrderState.REJECTED
                        order.error_code = exec_result.error_code or "EXECUTION_FAILED"
                        order.message = exec_result.message or "Execution failed"
                        oms_metrics.record_rejected()
                        await save_order(order)
                        await remove_order(item.oms_order_id)
                        self._record_terminal(order)
                        self._publish_event("OrderRejected", order)

                order.updated_at = datetime.now(UTC)
                await order_queue.complete(item.oms_order_id)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Queue processor error: %s", e, exc_info=True)
                oms_metrics.record_error()
                await asyncio.sleep(1)

    async def _reconcile_loop(self) -> None:
        while self._running:
            try:
                await self._reconcile_once()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Order reconciliation error: %s", e, exc_info=True)
            await asyncio.sleep(RECONCILE_INTERVAL_SECONDS)

    async def _reconcile_once(self) -> None:
        # Orders whose broker result is unknown have no `broker_order_id`, so the loop below
        # -- which selects on exactly that field -- could never see them. That is why an
        # order with a lost response used to sit unresolved forever instead of being
        # reconciled at all.
        await self._reconcile_unknown_once()

        active = [
            o for o in self._orders.values()
            if o.broker_order_id and o.state in (OMSOrderState.PENDING, OMSOrderState.PARTIAL)
        ]
        if not active:
            return
        by_key: dict[tuple[str, str], list[OmniOrder]] = {}
        for o in active:
            by_key.setdefault((o.user_id, o.broker), []).append(o)
        for (user_id, broker), orders in by_key.items():
            try:
                book = await self._exec_mgr.get_orders(user_id, broker)
            except Exception as e:
                logger.warning("Reconcile fetch failed for %s/%s: %s", user_id, broker, e)
                continue
            by_broker_id = {o.broker_order_id: o for o in book if o.broker_order_id}
            for order in orders:
                remote = by_broker_id.get(order.broker_order_id)
                if remote is None:
                    continue
                await self._apply_remote_status(order, remote)

    #: Injected in tests so the decision table can be driven deterministically. Left None in
    #: production, where the reconciler is built against the real broker adapter.
    reconciler_factory: Any = None

    def _build_reconciler(self, user_id: str, broker: str):
        """A reconciler bound to this user's live broker.

        The two callables are Dhan's own lookups -- `GET /v2/orders/external/{correlationId}`
        and the day order list -- as exposed by the official Dhan client. No identifier is
        invented here; if the adapter cannot answer, reconciliation reports UNKNOWN rather
        than guessing.
        """
        if self.reconciler_factory is not None:
            return self.reconciler_factory(user_id, broker)

        from oms.reconciliation import OrderReconciler

        async def lookup_by_correlation(correlation_id: str):
            adapter = await self._exec_mgr._get_adapter(user_id, broker)
            client = getattr(adapter, "_adapter", None)
            inner = getattr(client, "_inner", client)
            fetch = getattr(inner, "_get_client", None)
            if fetch is None:
                raise RuntimeError("adapter cannot issue HTTP requests")
            http = await fetch()
            base = getattr(inner, "_base_url", "https://api.dhan.co/v2")
            headers = inner._headers()
            resp = await http.get(f"{base}/orders/external/{correlation_id}",
                                  headers=headers, timeout=15.0)
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            return resp.json()

        async def list_orders():
            adapter = await self._exec_mgr._get_adapter(user_id, broker)
            client = getattr(adapter, "_adapter", None)
            inner = getattr(client, "_inner", client)
            fetch = getattr(inner, "_get_client", None)
            if fetch is None:
                raise RuntimeError("adapter cannot issue HTTP requests")
            http = await fetch()
            base = getattr(inner, "_base_url", "https://api.dhan.co/v2")
            resp = await http.get(f"{base}/orders", headers=inner._headers(), timeout=20.0)
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, list) else []

        return OrderReconciler(lookup_by_correlation=lookup_by_correlation,
                               list_orders=list_orders)

    async def _reconcile_unknown_once(self) -> None:
        """Resolve orders the broker never answered for.

        Every verdict is acted on. `UNKNOWN` and `AMBIGUOUS` produce **no** retry and no
        duplicate: UNKNOWN goes back to waiting, AMBIGUOUS becomes terminal and waits for a
        human. Only a definitive NOT_FOUND can make a retry eligible, and even then the
        decision is recorded rather than acted on here -- `retry_eligible` is a fact for the
        caller, not an action taken in the middle of a reconciliation pass.
        """
        pending = [
            o for o in self._orders.values()
            if o.state in (OMSOrderState.UNKNOWN, OMSOrderState.RECONCILING)
        ]
        for order in pending:
            try:
                await self._reconcile_one_unknown(order)
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 - one bad order must not stop the loop
                logger.error("Unknown-order reconciliation failed for %s: %s",
                             order.oms_order_id, e, exc_info=True)

    async def _reconcile_one_unknown(self, order: OmniOrder) -> None:
        from oms.reconciliation import ReconcileVerdict

        order.state = OMSOrderState.RECONCILING
        order.reconcile_attempts += 1
        await save_order(order)

        reconciler = self._build_reconciler(order.user_id, order.broker)
        outcome = await reconciler.reconcile(
            correlation_id=order.client_order_id or order.execution_request_id or "",
            expected_attributes=self._reconcile_attributes(order),
            sent_at=order.sent_at,
            broker_order_id=order.broker_order_id or "",
            not_found_observations=order.not_found_observations,
        )
        order.message = outcome.reason

        if outcome.verdict is ReconcileVerdict.ACCEPTED and outcome.match:
            order.broker_order_id = outcome.match.broker_order_id
            order.not_found_observations = 0
            order.state = OMSOrderState.PENDING
            await save_order(order)
            self._publish_event("OrderPending", order)
            return

        if outcome.verdict is ReconcileVerdict.REJECTED:
            order.not_found_observations = 0
            order.state = OMSOrderState.REJECTED
            order.error_code = order.error_code or "BROKER_REJECTED"
            await save_order(order)
            await remove_order(order.oms_order_id)
            self._record_terminal(order)
            self._publish_event("OrderRejected", order)
            return

        if outcome.verdict is ReconcileVerdict.AMBIGUOUS:
            # Never resolved automatically. Choosing one of several real broker orders could
            # cancel a live position or leave a duplicate behind.
            order.state = OMSOrderState.AMBIGUOUS
            order.error_code = "AMBIGUOUS_BROKER_MATCH"
            await save_order(order)
            await remove_order(order.oms_order_id)
            logger.error(
                "Order %s is AMBIGUOUS at the broker (%d candidates); manual review required",
                order.oms_order_id, len(outcome.candidates),
            )
            self._record_terminal(order)
            self._publish_event("OrderAmbiguous", order)
            return

        if outcome.verdict is ReconcileVerdict.NOT_FOUND:
            order.not_found_observations = outcome and order.not_found_observations + 1
            order.state = OMSOrderState.QUEUED
            order.retry_count += 1
            order.message = (
                f"{outcome.reason}; broker confirmed no matching order, retry is eligible"
            )
            await save_order(order)
            await order_queue.enqueue_retry(
                OrderQueueItem(oms_order_id=order.oms_order_id),
                delay_seconds=2.0,
            )
            oms_metrics.record_retry()
            logger.warning("Order %s: %s", order.oms_order_id, outcome.reason)
            return

        if outcome.verdict is ReconcileVerdict.UNKNOWN:
            # Still cannot tell. Stay put -- no retry, no duplicate. Explicit rather than a
            # fall-through, so that a verdict added later cannot silently land here and be
            # treated as "keep waiting".
            order.not_found_observations = order.not_found_observations + 1
            order.state = OMSOrderState.UNKNOWN
            await save_order(order)
            logger.info("Order %s still unknown: %s", order.oms_order_id, outcome.reason)
            return

        # An unrecognised verdict is not a licence to retry either.
        logger.error(
            "Order %s: reconciliation returned an unhandled verdict %r; leaving it %s",
            order.oms_order_id, outcome.verdict, order.state.value,
        )

    def _reconcile_attributes(self, order: OmniOrder) -> dict:
        """The contract identity to match a broker order against.

        `securityId` and `exchangeSegment` come from the resolver, not from the display
        symbol, so two contracts can never be confused here.
        """
        expected = {
            "transactionType": order.side,
            "quantity": order.quantity,
            "orderType": order.order_type,
            "productType": order.product,
            "drvExpiryDate": order.expiry_date,
            "drvStrikePrice": order.strike_price,
            "drvOptionType": order.option_type,
        }
        try:
            from market.instruments import instrument_resolver

            instrument = instrument_resolver.resolve(
                order.symbol, broker=order.broker,
                instrument_type=order.instrument_type or "EQ",
            )
            if instrument is not None:
                expected["securityId"] = instrument.security_id
                expected["exchangeSegment"] = instrument.exchange_segment
                expected["drvExpiryDate"] = expected["drvExpiryDate"] or instrument.expiry
                expected["drvStrikePrice"] = expected["drvStrikePrice"] or instrument.strike
                expected["drvOptionType"] = expected["drvOptionType"] or instrument.option_type
        except Exception as e:  # noqa: BLE001 - weaker matching, never a guess
            logger.warning("Could not resolve contract identity for %s: %s",
                           order.oms_order_id, e)
        return expected

    async def _apply_remote_status(self, order: OmniOrder, remote: Any) -> None:
        remote_status = remote.status.value if hasattr(remote.status, "value") else str(remote.status or "")
        target = None
        event_type = ""
        if remote_status in ("FILLED", "TRADED", "COMPLETED"):
            target = OMSOrderState.FILLED
            event_type = "OrderCompleted"
        elif remote_status == "PARTIALLY_FILLED":
            target = OMSOrderState.PARTIAL
        elif remote_status == "CANCELLED":
            target = OMSOrderState.CANCELLED
            event_type = "OrderCancelled"
        elif remote_status == "REJECTED":
            target = OMSOrderState.REJECTED
            event_type = "OrderRejected"
        elif remote_status == "EXPIRED":
            target = OMSOrderState.EXPIRED
            event_type = "OrderExpired"
        if target is None:
            return
        if not state_machine.can_transition(order.state, target):
            return

        order.broker_order_id = remote.broker_order_id or order.broker_order_id
        if target == OMSOrderState.PARTIAL:
            order.filled_quantity = remote.filled_quantity or order.filled_quantity
            order.average_price = remote.average_price or order.average_price
            order.state = target
            order.updated_at = datetime.now(UTC)
            order.message = "Partially filled (reconciled)"
            await save_order(order)
            return

        if target == OMSOrderState.FILLED:
            order.filled_quantity = remote.filled_quantity or order.quantity
            order.average_price = remote.average_price or 0.0
            order.filled_at = datetime.now(UTC)
            order.message = "Filled (reconciled)"
            oms_metrics.record_filled(order.latency_ms or 0.0)
        elif target == OMSOrderState.CANCELLED:
            order.cancelled_at = datetime.now(UTC)
            order.message = "Cancelled at broker"
            oms_metrics.record_cancelled()
        elif target == OMSOrderState.REJECTED:
            order.message = "Rejected at broker"
            oms_metrics.record_rejected()
        else:
            order.message = "Expired at broker"

        order.state = target
        order.updated_at = datetime.now(UTC)
        await save_order(order)
        await remove_order(order.oms_order_id)
        self._orders.pop(order.oms_order_id, None)
        if target == OMSOrderState.FILLED:
            await self._attach_auto_bracket(order)
        else:
            await self._deactivate_bracket(order.oms_order_id)
        self._record_terminal(order)
        await self._mirror_audit_status(order, target)
        if event_type:
            self._publish_event(event_type, order)
        if target == OMSOrderState.FILLED:
            await self._handle_parent_completion(order)

    async def _mirror_audit_status(self, order: OmniOrder, target: OMSOrderState) -> None:
        try:
            from core.db import async_supabase, get_supabase
            supabase = get_supabase()
            data: dict[str, Any] = {
                "status": target.value,
                "message": order.message,
            }
            if target in (OMSOrderState.FILLED, OMSOrderState.PARTIAL):
                data["filled_at"] = datetime.now(UTC).isoformat()
                data["filled_quantity"] = order.filled_quantity
            await async_supabase(lambda: supabase.table("orders").update(data)
                                 .eq("user_id", order.user_id)
                                 .eq("broker_order_id", order.broker_order_id)
                                 .execute())
        except Exception as e:
            logger.warning("Failed to mirror audit status for %s: %s", order.broker_order_id, e)

    async def _handle_parent_completion(self, order: OmniOrder) -> None:
        if order.relation_type == OrderRelationType.BRACKET:
            await self._handle_bracket_completion(order)
        elif order.relation_type == OrderRelationType.OCO:
            await self._handle_oco_completion(order)

    async def _handle_oco_completion(self, order: OmniOrder) -> None:
        for oco in list(self._oco_orders.values()):
            if not oco.active:
                continue
            if oco.order_a_id == order.oms_order_id:
                oco.order_a_filled = True
                sibling_id = oco.order_b_id
            elif oco.order_b_id == order.oms_order_id:
                oco.order_b_filled = True
                sibling_id = oco.order_a_id
            else:
                continue
            oco.active = False
            await save_oco_order(oco)

            sibling = self._orders.get(sibling_id)
            if sibling and state_machine.can_transition(sibling.state, OMSOrderState.CANCELLED):
                sibling.state = OMSOrderState.CANCELLED
                sibling.cancelled_at = datetime.now(UTC)
                sibling.updated_at = datetime.now(UTC)
                oms_metrics.record_cancelled()
                await save_order(sibling)
                await remove_order(sibling_id)
                self._publish_event("OrderCancelled", sibling)
            break

    async def _handle_bracket_completion(self, order: OmniOrder) -> None:
        bracket = self._bracket_orders.get(order.oms_order_id)
        if not bracket:
            return
        bracket.entry_filled = True
        await save_bracket_order(bracket)

        try:
            sl_req = ExecutionRequest(
                user_id=order.user_id, broker=order.broker,
                symbol=order.symbol, exchange=order.exchange,
                side="SELL" if order.side == "BUY" else "BUY",
                order_type="SL", product=order.product,
                quantity=order.filled_quantity or order.quantity,
                price=bracket.stop_loss_price,
                trigger_price=bracket.stop_loss_price,
                source="bracket_sl",
            )
            sl_order = await self.place_order(sl_req)
            if sl_order.state in (OMSOrderState.REJECTED, OMSOrderState.CANCELLED):
                logger.error("Bracket SL leg rejected for parent %s: %s", order.oms_order_id, sl_order.message)
                return
            bracket.sl_order_id = sl_order.oms_order_id

            target_req = ExecutionRequest(
                user_id=order.user_id, broker=order.broker,
                symbol=order.symbol, exchange=order.exchange,
                side="SELL" if order.side == "BUY" else "BUY",
                order_type="LIMIT", product=order.product,
                quantity=order.filled_quantity or order.quantity,
                price=bracket.target_price,
                source="bracket_target",
            )
            target_order = await self.place_order(target_req)
            if target_order.state in (OMSOrderState.REJECTED, OMSOrderState.CANCELLED):
                logger.error("Bracket target leg rejected for parent %s: %s", order.oms_order_id, target_order.message)
                return
            bracket.target_order_id = target_order.oms_order_id

            await save_bracket_order(bracket)
        except Exception as e:
            logger.error("Failed to place bracket legs for parent %s: %s", order.oms_order_id, e)

    async def _attach_auto_bracket(self, order: OmniOrder) -> None:
        """Attach default SL/target protection to any filled order.

        SL = entry -10% (BUY) / +10% (SELL); target = RR 1.5 against SL.
        Exit legs are placed by the bracket monitor loop on tick breach.
        """
        try:
            if order.source in EXIT_SOURCES or order.relation_type != OrderRelationType.NONE:
                return
            entry = order.average_price or order.price
            if entry <= 0 or order.quantity <= 0:
                return
            side = order.side.upper()
            if side == "BUY":
                sl = round(entry * (1 - SL_PCT_DEFAULT), 2)
                target = round(entry * (1 + SL_PCT_DEFAULT * RR_TARGET_DEFAULT), 2)
            elif side == "SELL":
                sl = round(entry * (1 + SL_PCT_DEFAULT), 2)
                target = round(entry * (1 - SL_PCT_DEFAULT * RR_TARGET_DEFAULT), 2)
            else:
                return
            bracket = BracketOrder(
                oms_order_id=_oms_order_id(),
                parent_order_id=order.oms_order_id,
                user_id=order.user_id,
                symbol=order.symbol,
                quantity=order.filled_quantity or order.quantity,
                entry_price=entry,
                stop_loss_price=sl,
                target_price=target,
                entry_filled=True,
                active=True,
                side=side,
                broker=order.broker,
            )
            self._bracket_orders[order.oms_order_id] = bracket
            await save_bracket_order(bracket)
            oms_metrics.record_bracket()
            logger.info(
                "Auto-bracket attached: user=%s parent=%s symbol=%s side=%s entry=%.2f sl=%.2f target=%.2f",
                order.user_id, order.oms_order_id, order.symbol, side, entry, sl, target,
            )
        except Exception as e:
            logger.error("Failed to attach auto-bracket for %s: %s", order.oms_order_id, e)

    async def _deactivate_bracket(self, parent_order_id: str) -> None:
        bracket = self._bracket_orders.get(parent_order_id)
        if not bracket or not bracket.active:
            return
        bracket.active = False
        await save_bracket_order(bracket)
        logger.info("Bracket deactivated for parent %s", parent_order_id)

    async def _bracket_loop(self) -> None:
        while self._running:
            try:
                await self._evaluate_brackets()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Bracket monitor error: %s", e, exc_info=True)
            await asyncio.sleep(BRACKET_INTERVAL_SECONDS)

    async def _evaluate_brackets(self) -> None:
        active = [b for b in list(self._bracket_orders.values()) if b.active and not (b.sl_order_id or b.target_order_id)]
        for b in list(self._bracket_orders.values()):
            if b.active and (b.sl_order_id or b.target_order_id):
                b.active = False
                await save_bracket_order(b)
        if not active:
            return
        quotes = await asyncio.gather(*[self._bracket_quote(b) for b in active], return_exceptions=True)
        for bracket, last in zip(active, quotes):
            if isinstance(last, Exception):
                logger.warning("Bracket quote failed for %s: %s", bracket.oms_order_id, last)
                continue
            if not isinstance(last, (int, float)) or last <= 0:
                continue
            if bracket.side == "BUY":
                if last <= bracket.stop_loss_price:
                    await self._place_exit(bracket, "SL", last)
                elif last >= bracket.target_price:
                    await self._place_exit(bracket, "TARGET", last)
            else:
                if last >= bracket.stop_loss_price:
                    await self._place_exit(bracket, "SL", last)
                elif last <= bracket.target_price:
                    await self._place_exit(bracket, "TARGET", last)

    async def _bracket_quote(self, bracket: BracketOrder) -> float:
        key = (bracket.user_id, bracket.broker, bracket.symbol)
        now = time.monotonic()
        cached = self._quote_cache.get(key)
        if cached and now - cached[0] < QUOTE_CACHE_TTL:
            return cached[1]
        # Prefer WebSocket-fed ticks (shared_socket / market_cache) before any
        # REST quote call — live market updates never hit the Fyers REST API.
        from market.cache import market_cache
        from datetime import UTC, datetime
        ws_tick = market_cache.get_tick(bracket.symbol)
        if ws_tick and ws_tick.last_price > 0:
            tick_age = (datetime.now(UTC) - ws_tick.timestamp).total_seconds()
            if tick_age < 5.0:
                price = ws_tick.last_price
                self._quote_cache[key] = (now, price)
                return price
        # Single-flight: multiple brackets on the same (user, symbol) share ONE
        # REST round-trip; the bracket monitor itself is a single global worker.
        flight_key = (bracket.user_id, bracket.symbol)
        existing = self._quote_inflight.get(flight_key)
        if existing is not None:
            return await existing
        task = asyncio.create_task(self._bracket_quote_fetch(bracket))
        self._quote_inflight[flight_key] = task
        try:
            price = await task
        finally:
            self._quote_inflight.pop(flight_key, None)
        self._quote_cache[key] = (now, price)
        return price

    async def _bracket_quote_fetch(self, bracket: BracketOrder) -> float:
        from market.cache import market_cache
        price = 0.0
        if bracket.broker == PAPER_BROKER:
            q = market_cache.get_quote(bracket.symbol)
            if not q or not (q.get("last_price") or q.get("ltp")):
                # Paper quotes must not depend on a live broker token: use the
                # broker-agnostic Yahoo feed first, then the live-broker REST
                # refresh only as a last resort (token may be expired/dead).
                try:
                    from providers.yahoo import fetch_quotes
                    quotes = await fetch_quotes([bracket.symbol])
                    if quotes and getattr(quotes[0], "last_price", 0) > 0:
                        market_cache.put_quote(bracket.symbol, quotes[0].model_dump(mode="json"))
                        q = market_cache.get_quote(bracket.symbol)
                except Exception:
                    pass
            if not q or not (q.get("last_price") or q.get("ltp")):
                try:
                    from brokers.token_manager import TokenManager
                    from brokers.fyers_adapter import FyersAdapter
                    session = await TokenManager(bracket.user_id, "fyers").get_session()
                    if session:
                        adapter = FyersAdapter()
                        await adapter.authenticate({
                            "client_id": session.get("client_id", ""),
                            "access_token": session.get("access_token", ""),
                        })
                        quotes = await adapter.get_quotes([bracket.symbol])
                        if quotes and getattr(quotes[0], "last_price", 0) > 0:
                            market_cache.put_quote(bracket.symbol, quotes[0].model_dump(mode="json"))
                            q = market_cache.get_quote(bracket.symbol)
                except Exception as e:
                    self._log_throttled("Paper bracket quote refresh failed for %s: %s", bracket.symbol, e)
            if q:
                price = float(q.get("last_price") or q.get("ltp") or 0)
        else:
            adapter = await self._exec_mgr._get_adapter(bracket.user_id, bracket.broker)
            if adapter:
                quotes = await adapter.get_quotes([bracket.symbol])
                if quotes and getattr(quotes[0], "last_price", 0):
                    price = quotes[0].last_price
        return price

    async def _place_exit(self, bracket: BracketOrder, leg: str, last: float) -> None:
        side = "SELL" if bracket.side == "BUY" else "BUY"
        level = bracket.stop_loss_price if leg == "SL" else bracket.target_price
        source = "exit_sl" if leg == "SL" else "exit_target"
        try:
            if leg == "TARGET":
                order_type = "MARKET" if last > level * 1.02 else "LIMIT"
                req = ExecutionRequest(
                    user_id=bracket.user_id, broker=bracket.broker,
                    symbol=bracket.symbol, exchange="NSE",
                    side=side, order_type=order_type, product="INTRADAY",
                    quantity=bracket.quantity, price=0.0 if order_type == "MARKET" else level,
                    source=source,
                )
            else:
                req = ExecutionRequest(
                    user_id=bracket.user_id, broker=bracket.broker,
                    symbol=bracket.symbol, exchange="NSE",
                    side=side, order_type="SL", product="INTRADAY",
                    quantity=bracket.quantity, price=level, trigger_price=level,
                    source=source,
                )
            exit_order = await self.place_order(req)
            if exit_order.state in (OMSOrderState.REJECTED, OMSOrderState.CANCELLED) and leg == "SL":
                logger.warning("SL leg %s rejected (%s) — falling back to MARKET", exit_order.oms_order_id, exit_order.message)
                req.order_type = "MARKET"
                req.price = 0.0
                req.trigger_price = None
                exit_order = await self.place_order(req)
            if exit_order.state in (OMSOrderState.REJECTED, OMSOrderState.CANCELLED):
                logger.error("Exit leg %s failed for bracket %s: %s", leg, bracket.oms_order_id, exit_order.message)
                return
            if leg == "SL":
                bracket.sl_order_id = exit_order.oms_order_id
            else:
                bracket.target_order_id = exit_order.oms_order_id
            bracket.active = False
            await save_bracket_order(bracket)
            logger.info(
                "Bracket exit %s placed: user=%s parent=%s symbol=%s side=%s qty=%d level=%.2f oms=%s broker=%s",
                leg, bracket.user_id, bracket.parent_order_id, bracket.symbol, side,
                bracket.quantity, level, exit_order.oms_order_id, exit_order.broker_order_id or exit_order.broker,
            )
        except Exception as e:
            logger.error("Exit placement failed for bracket %s: %s", bracket.oms_order_id, e)

    async def _recover_active_orders(self) -> None:
        rows = await load_active_orders()
        for row in rows:
            try:
                order = OmniOrder(**row)
                self._add_order(order)
                if order.state in (OMSOrderState.QUEUED, OMSOrderState.SENT):
                    item = OrderQueueItem(
                        oms_order_id=order.oms_order_id,
                        user_id=order.user_id,
                        broker=order.broker,
                        priority=order.priority,
                        retry_count=order.retry_count,
                    )
                    await order_queue.enqueue(item)
            except Exception as e:
                logger.warning("Failed to recover order %s: %s", row.get("oms_order_id", ""), e)

        bracket_rows = await load_active_bracket_orders()
        for row in bracket_rows:
            try:
                bracket = BracketOrder(**row)
                self._bracket_orders[bracket.parent_order_id] = bracket
            except Exception as e:
                logger.warning("Failed to recover bracket order: %s", e)

        oco_rows = await load_active_oco_orders()
        for row in oco_rows:
            try:
                oco = OCOOrder(**row)
                self._oco_orders[oco.oms_order_id] = oco
            except Exception as e:
                logger.warning("Failed to recover OCO order: %s", e)

        logger.info(
            "Recovered %d active orders, %d bracket orders, %d OCO orders",
            len(rows), len(bracket_rows), len(oco_rows),
        )

    def _add_order(self, order: OmniOrder) -> None:
        self._orders[order.oms_order_id] = order
        self._orders.move_to_end(order.oms_order_id)
        if len(self._orders) > self._max_orders:
            self._evict_oldest_terminal_order()

    def _record_terminal(self, order: OmniOrder) -> None:
        """Keep a short-lived record of terminal orders for synchronous callers."""
        self._completed[order.oms_order_id] = order
        if len(self._completed) > 200:
            self._completed.pop(next(iter(self._completed)), None)
        try:
            import asyncio
            import json
            from core.cache import cache

            async def _store() -> None:
                try:
                    r = await cache.get_redis()
                    if not r:
                        return
                    await r.setex(f"oms:result:{order.oms_order_id}", 60, json.dumps(order.model_dump(mode="json")))
                except Exception:
                    pass

            asyncio.get_running_loop().create_task(_store())
        except Exception:
            pass

    def find_order(self, user_id: str, broker_order_id: str) -> OmniOrder | None:
        """Locate an OMS order by broker order id (active or recently completed)."""
        for oid in (self._orders, self._completed):
            for o in oid.values():
                if o.broker_order_id == broker_order_id and o.user_id == user_id:
                    return o
        return None

    def _evict_oldest_terminal_order(self) -> None:
        for oid, o in list(self._orders.items()):
            if o.state in TERMINAL_OMS_STATES:
                del self._orders[oid]
                logger.debug("Evicted terminal order %s from memory", oid)
                return
        logger.warning("No terminal orders to evict (total=%d) — skipping eviction", len(self._orders))

    @classmethod
    def _reset_instance(cls):
        cls._instance = None

    def _publish_event(self, event_type: str, order: OmniOrder) -> None:
        try:
            event = ExecutionEvent(
                event_type=event_type,
                execution_request_id=order.execution_request_id,
                user_id=order.user_id,
                broker=order.broker,
                symbol=order.symbol,
                side=order.side,
                payload=order.model_dump(mode="json"),
            )
            fire_and_forget(execution_event_bus.publish(event))
        except Exception as e:
            logger.error("Failed to publish %s event: %s", event_type, e)


order_manager = OrderManager()
