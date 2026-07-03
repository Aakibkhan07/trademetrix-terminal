import asyncio
import hashlib
import logging
import time
from collections import OrderedDict
from datetime import UTC, datetime
from typing import Any

from execution.event_bus import execution_event_bus, ExecutionEvent, fire_and_forget
from execution.manager import ExecutionManager
from execution.models import ExecutionRequest, ExecutionResult, ExecutionState
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
    remove_order,
    save_bracket_order,
    save_oco_order,
    save_order,
)
from oms.state_machine import state_machine

logger = logging.getLogger(__name__)

PAPER_BROKER = "paper"
MAX_ACTIVE_ORDERS = 1000

TERMINAL_OMS_STATES = {
    OMSOrderState.FILLED,
    OMSOrderState.CANCELLED,
    OMSOrderState.REJECTED,
    OMSOrderState.EXPIRED,
}


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
        self._running = False

    async def start(self) -> None:
        await self._recover_active_orders()
        self._running = True
        self._processor_task = asyncio.create_task(self._process_queue())
        logger.info("OrderManager started")

    async def stop(self) -> None:
        self._running = False
        if self._processor_task:
            self._processor_task.cancel()
            self._processor_task = None
        logger.info("OrderManager stopped")

    async def place_order(self, req: ExecutionRequest) -> OmniOrder:
        oms_id = _oms_order_id()
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
            strategy_id=req.strategy_id or "",
            source=req.source,
            is_paper=(req.broker == PAPER_BROKER),
            state=OMSOrderState.NEW,
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

    async def cancel_order(self, oms_order_id: str) -> OmniOrder | None:
        order = self._orders.get(oms_order_id)
        if not order:
            return None

        if not state_machine.can_transition(order.state, OMSOrderState.CANCELLED):
            logger.warning("Cannot cancel order %s in state %s", oms_order_id, order.state)
            return order

        if order.state == OMSOrderState.QUEUED:
            removed = await order_queue.remove(oms_order_id)
            if not removed:
                if order.state != OMSOrderState.QUEUED:
                    logger.warning("Order %s was already dequeued by processor — falling through to broker cancel", oms_order_id)
                else:
                    order.state = OMSOrderState.CANCELLED
                    order.cancelled_at = datetime.now(UTC)
                    order.updated_at = datetime.now(UTC)
                    oms_metrics.record_cancelled()
                    await save_order(order)
                    await remove_order(oms_order_id)
                    self._publish_event("OrderCancelled", order)
                    return order
            else:
                order.state = OMSOrderState.CANCELLED
                order.cancelled_at = datetime.now(UTC)
                order.updated_at = datetime.now(UTC)
                oms_metrics.record_cancelled()
                await save_order(order)
                await remove_order(oms_order_id)
                self._publish_event("OrderCancelled", order)
                return order

        req = ExecutionRequest(
            user_id=order.user_id, broker=order.broker,
            symbol=order.symbol, exchange=order.exchange,
            side=order.side, quantity=order.quantity,
            source="oms_cancel",
        )
        exec_result = await self._exec_mgr.cancel_order(req, order.broker_order_id or "")
        if exec_result.success:
            order.state = OMSOrderState.CANCELLED
            order.cancelled_at = datetime.now(UTC)
            order.updated_at = datetime.now(UTC)
            order.message = exec_result.message
            oms_metrics.record_cancelled()
            await save_order(order)
            await remove_order(oms_order_id)
            self._publish_event("OrderCancelled", order)
        else:
            order.message = exec_result.message or "Cancel failed"
            order.updated_at = datetime.now(UTC)
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

                req = ExecutionRequest(
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
                    strategy_id=order.strategy_id or None,
                    source=order.source,
                    execution_request_id=order.execution_request_id,
                )

                exec_start = time.monotonic()
                exec_result = await self._exec_mgr.place_order(req)
                latency_ms = (time.monotonic() - exec_start) * 1000

                order.latency_ms = latency_ms
                oms_metrics.record_broker_latency(order.broker, latency_ms)

                if exec_result.success:
                    order.state = OMSOrderState.FILLED
                    order.broker_order_id = exec_result.broker_order_id or ""
                    order.filled_quantity = order.quantity
                    order.filled_at = datetime.now(UTC)
                    order.message = exec_result.message
                    oms_metrics.record_filled(latency_ms)
                    await save_order(order)
                    await remove_order(item.oms_order_id)
                    self._publish_event("OrderCompleted", order)
                    await self._handle_parent_completion(order)
                else:
                    if order.retry_count < order.max_retries:
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
                        self._publish_event("OrderRejected", order)

                order.updated_at = datetime.now(UTC)
                await order_queue.complete(item.oms_order_id)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Queue processor error: %s", e, exc_info=True)
                oms_metrics.record_error()
                await asyncio.sleep(1)

    async def _handle_parent_completion(self, order: OmniOrder) -> None:
        if order.relation_type != OrderRelationType.BRACKET:
            return
        bracket = self._bracket_orders.get(order.oms_order_id)
        if not bracket:
            return
        bracket.entry_filled = True
        await save_bracket_order(bracket)

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

    def _evict_oldest_terminal_order(self) -> None:
        for oid, o in list(self._orders.items()):
            if o.state in TERMINAL_OMS_STATES:
                del self._orders[oid]
                logger.debug("Evicted terminal order %s from memory", oid)
                return
        oldest = next(iter(self._orders))
        logger.warning("No terminal order to evict — evicting oldest active order %s", oldest)
        del self._orders[oldest]

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
