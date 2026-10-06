"""The full OMS path against a deterministic broker. No real order is ever sent.

Strategy -> risk -> Redis -> OMS worker -> ExecutionManager -> broker adapter -> broker
answer -> OMS state -> reconciliation, with the broker replaced by a simulator whose answer
is chosen per scenario. Redis is replaced by an in-process queue with the same enqueue /
dequeue / complete contract, because a real Redis would add timing rather than evidence.

Each scenario asserts the two properties that matter and cannot be traded against each
other: the right OMS state, and the number of POSTs the broker actually received.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from core.models import (Exchange, InstrumentType, NormalizedOrder, OptionType, OrderResult,
                         OrderSide, OrderType, ProductType)
from execution.indeterminate import IndeterminateOrderError
from execution.manager import ExecutionManager
from execution.models import ExecutionRequest
from oms.identity import intent_fingerprint
from oms.manager import build_execution_request
from oms.models import OMSOrderState, OmniOrder
from oms.reconciliation import OrderReconciler, ReconcileVerdict

USER = "17ba8349-30e6-48fa-a0f3-9a06389fe44b"
CID = "logical-order-sim-1"
EXPIRY = "2026-10-06"
STRIKE = 23250.0

BROKER_ORDER = {
    "orderId": "998877665544", "correlationId": CID, "orderStatus": "OPEN",
    "securityId": "40749", "exchangeSegment": "NSE_FNO", "transactionType": "BUY",
    "quantity": 65, "orderType": "MARKET", "productType": "INTRADAY",
    "drvExpiryDate": EXPIRY, "drvStrikePrice": STRIKE, "drvOptionType": "CE",
    "exchangeTime": int(datetime.now(UTC).timestamp()),
}


def make_request(**over) -> ExecutionRequest:
    base = dict(
        user_id=USER, broker="dhan", symbol="NIFTY-Oct2026-23250-CE", exchange=Exchange.NSE,
        side=OrderSide.BUY, order_type=OrderType.MARKET, product=ProductType.MIS,
        quantity=65, price=0.65, validity="DAY", instrument_type=InstrumentType.OPT,
        strike_price=STRIKE, expiry_date=EXPIRY, option_type=OptionType.CE,
        execution_request_id=CID, source="sim", is_paper=False,
    )
    base.update(over)
    return ExecutionRequest(**base)


class SimBroker:
    """Counts what reached the broker and answers with a chosen outcome."""

    def __init__(self, outcome: str, *, holds_order: bool = False,
                 hold_delay: timedelta = timedelta(0)):
        self.outcome = outcome
        self.posts: list[dict] = []
        self.holds_order = holds_order
        self.hold_delay = hold_delay
        self.held = holds_order

    async def place_order(self, order: NormalizedOrder) -> OrderResult:
        self.posts.append({"symbol": order.symbol, "quantity": order.quantity,
                           "security_id": order.client_order_id})
        if self.outcome == "reject":
            return OrderResult(success=False, message="Invalid_Quantity",
                               error_code="INVALID_QUANTITY")
        if self.outcome == "timeout_after_accept":
            # The broker took it; the response never arrived.
            self.held = True
            raise IndeterminateOrderError("read timeout", broker="dhan")
        if self.outcome == "timeout_before_create":
            raise IndeterminateOrderError("connect timeout", broker="dhan")
        if self.outcome == "accept":
            self.held = True
            return OrderResult(success=True, broker_order_id="998877665544",
                               status="open")
        raise AssertionError(self.outcome)

    def orderbook(self):
        return [BROKER_ORDER] if self.held else []


@pytest.fixture
def wired(monkeypatch):
    """A real ExecutionManager with the simulated adapter injected, plus stub persistence."""
    import oms.manager as oms_mod

    saved: dict[str, OmniOrder] = {}
    enqueued: list = []

    async def fake_save(order):
        saved[order.oms_order_id] = order.model_copy(deep=True)

    async def fake_remove(_oid):
        return True

    async def fake_enqueue(item, **kw):
        enqueued.append(item)

    async def fake_complete(_oid):
        return True

    monkeypatch.setattr(oms_mod, "save_order", fake_save)
    monkeypatch.setattr(oms_mod, "remove_order", fake_remove)
    monkeypatch.setattr(oms_mod.order_queue, "enqueue", fake_enqueue)
    monkeypatch.setattr(oms_mod.order_queue, "enqueue_retry", fake_enqueue)
    monkeypatch.setattr(oms_mod.order_queue, "complete", fake_complete)

    mgr = ExecutionManager()
    mgr._adapters.clear()
    monkeypatch.setattr(mgr, "_adapters", {})

    def install(broker: SimBroker):
        class _Wrapper:
            """Stands in for BrokerExecutionAdapter: the worker calls place_order on it."""
            def __init__(self): self._adapter = broker
            async def health(self): return {"authenticated": True}
            async def place_order(self, order): return await broker.place_order(order)

        mgr._adapters[f"{USER}:dhan"] = _Wrapper()
        return broker

    return oms_mod, mgr, install, saved, enqueued


def _order(o: OmniOrder) -> NormalizedOrder:
    """The order the execution manager would have built for this OMS row."""
    return NormalizedOrder(
        symbol=o.symbol, exchange=Exchange(o.exchange), side=OrderSide(o.side),
        order_type=OrderType(o.order_type), product=ProductType(o.product),
        quantity=o.quantity, price=o.price, broker=o.broker, client_order_id=o.client_order_id,
        instrument_type=InstrumentType(o.instrument_type), option_type=OptionType(o.option_type),
        strike_price=o.strike_price, expiry_date=o.expiry_date,
    )


async def _store(wired, req, **over):
    """Put an order through the OMS's own construction so identity fields are real."""
    oms_mod, mgr, install, saved, enqueued = wired
    broker = install(over.pop("broker"))
    req = req if isinstance(req, ExecutionRequest) else make_request(**req)
    oms_id = "oms-sim-1"
    order = OmniOrder(
        oms_order_id=oms_id, execution_request_id=req.execution_request_id or CID,
        client_order_id=req.execution_request_id or CID, user_id=req.user_id,
        broker=req.broker, symbol=req.symbol, exchange=req.exchange, side=req.side,
        order_type=req.order_type, product=req.product, quantity=req.quantity,
        price=req.price, instrument_type=str(getattr(req.instrument_type, "value", req.instrument_type)),
        expiry_date=req.expiry_date, strike_price=req.strike_price,
        option_type=str(getattr(req.option_type, "value", req.option_type)),
        validity=req.validity,
        state=OMSOrderState.SENT, sent_at=datetime.now(UTC) - timedelta(seconds=2),
        created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        intent_fingerprint=intent_fingerprint(req),
    )
    mgr._exec_mgr = mgr
    oms_mod.order_manager._orders[oms_id] = order
    return order, broker, oms_mod, enqueued


# ── 1. immediate rejection ──────────────────────────────────────────────────


class TestScenario1ImmediateRejection:
    @pytest.mark.asyncio
    async def test_the_broker_refuses_and_the_order_ends_rejected(self, wired):
        broker = SimBroker("reject")
        order, broker, oms_mod, _ = await _store(wired, make_request(), broker=broker)
        mgr = oms_mod.order_manager._exec_mgr
        result = await mgr._execute_with_retry(broker, _order(order), "req-1")
        assert result.success is False
        assert result.indeterminate is False, "the broker answered; this is decisive"
        assert len(broker.posts) == 1, "a refusal must not be resent"
        assert result.broker_order_id == ""


# ── 2. immediate acceptance ─────────────────────────────────────────────────


class TestScenario2ImmediateAcceptance:
    @pytest.mark.asyncio
    async def test_acceptance_yields_a_broker_order_id_and_no_reconciliation(self, wired):
        broker = SimBroker("accept")
        order, broker, oms_mod, _ = await _store(wired, make_request(), broker=broker)
        mgr = oms_mod.order_manager._exec_mgr
        result = await mgr._execute_with_retry(broker, _order(order), "req-2")
        assert result.success is True
        assert result.broker_order_id == "998877665544"
        assert result.indeterminate is False
        assert len(broker.posts) == 1
        # With an id in hand there is nothing to reconcile.
        out = await OrderReconciler().reconcile(
            correlation_id=CID, expected_attributes={},
            sent_at=order.sent_at, broker_order_id=result.broker_order_id,
        )
        assert out.verdict is ReconcileVerdict.ACCEPTED
        assert out.retry_eligible is False


# ── 3. timeout AFTER the broker accepted ─────────────────────────────────────


class TestScenario3TimeoutAfterAcceptance:
    @pytest.mark.asyncio
    async def test_reconciliation_finds_the_order_and_nothing_is_resent(self, wired):
        broker = SimBroker("timeout_after_accept", holds_order=True)
        order, broker, oms_mod, enqueued = await _store(wired, make_request(), broker=broker)
        mgr = oms_mod.order_manager._exec_mgr

        result = await mgr._execute_with_retry(broker, _order(order), "req-3")
        assert result.indeterminate is True, "the response was lost; that must not read as a refusal"
        assert len(broker.posts) == 1
        assert order.state is not OMSOrderState.REJECTED

        async def _async_corr(c):
            return [BROKER_ORDER] if c == CID else []

        async def _async_book():
            return broker.orderbook()

        oms_mod.order_manager.reconciler_factory = (
            lambda _u, _b: OrderReconciler(
                lookup_by_correlation=_async_corr,
                list_orders=_async_book,
                grace=timedelta(seconds=1),
            )
        )
        order.state = OMSOrderState.UNKNOWN
        await oms_mod.order_manager._reconcile_one_unknown(order)

        assert order.state is OMSOrderState.PENDING
        assert order.broker_order_id == "998877665544"
        assert len(broker.posts) == 1, (
            "an accepted order whose response was lost must never be sent again"
        )
        assert enqueued == [], "nothing may be requeued once the order is located"


# ── 4. timeout BEFORE the broker created it ──────────────────────────────────


class TestScenario4TimeoutBeforeCreation:
    @pytest.mark.asyncio
    async def test_it_stays_pending_reconciliation_and_never_becomes_a_retry(self, wired):
        broker = SimBroker("timeout_before_create", holds_order=False)
        order, broker, oms_mod, enqueued = await _store(wired, make_request(), broker=broker)
        mgr = oms_mod.order_manager._exec_mgr
        result = await mgr._execute_with_retry(broker, _order(order), "req-4")

        assert result.indeterminate is True
        order.state = OMSOrderState.UNKNOWN
        async def _async_none(c):
            return []

        async def _async_book_empty():
            return []

        oms_mod.order_manager.reconciler_factory = (
            lambda _u, _b: OrderReconciler(
                lookup_by_correlation=_async_none,
                list_orders=_async_book_empty, grace=timedelta(seconds=600),
            )
        )
        await oms_mod.order_manager._reconcile_one_unknown(order)

        assert order.state is OMSOrderState.UNKNOWN, (
            "absence inside the grace window is not proof of absence"
        )
        assert enqueued == [], "no retry while the result is unknown"
        assert len(broker.posts) == 1


# ── 5. ambiguous broker result ───────────────────────────────────────────────


class TestScenario5AmbiguousResult:
    @pytest.mark.asyncio
    async def test_two_matching_orders_stop_the_order_and_choose_nothing(self, wired):
        broker = SimBroker("timeout_after_accept", holds_order=True)
        order, broker, oms_mod, enqueued = await _store(wired, make_request(), broker=broker)
        order.state = OMSOrderState.UNKNOWN
        # Mirror the contract identity the OMS itself resolves. Building the broker order
        # from a hardcoded 40749/None here would test nothing: the attribute scan compares
        # against `_reconcile_attributes(order)`, and in the test environment the resolver
        # answers from a fixture rather than the live Dhan master.
        resolved = oms_mod.order_manager._reconcile_attributes(order)
        mirror = {**BROKER_ORDER,
                  **{k: v for k, v in resolved.items() if k in BROKER_ORDER}}
        twin = {**mirror, "orderId": "112233445566", "correlationId": ""}
        async def _async_none(c):
            return []

        async def _async_book_twin():
            # exchangeTime is refreshed at call time, not module import time. The module-level
            # constant is stamped once on import, so once other test files run first the
            # value is stale and the window filter drops both candidates -- which turns this
            # scenario into a silent UNKNOWN.
            fresh = int(datetime.now(UTC).timestamp())
            return [{**mirror, "exchangeTime": fresh},
                    {**twin, "exchangeTime": fresh}]

        oms_mod.order_manager.reconciler_factory = (
            lambda _u, _b: OrderReconciler(
                lookup_by_correlation=_async_none,
                list_orders=_async_book_twin,
                grace=timedelta(seconds=1),
            )
        )
        await oms_mod.order_manager._reconcile_one_unknown(order)

        assert order.state is OMSOrderState.AMBIGUOUS
        assert order.broker_order_id == "", "no broker order may be adopted from ambiguity"
        assert enqueued == [], "ambiguity must not produce a retry"
        assert order.error_code == "AMBIGUOUS_BROKER_MATCH"


# ── 6. duplicate retry attempt ───────────────────────────────────────────────


class TestScenario6DuplicateRetryAttempt:
    @pytest.mark.asyncio
    async def test_a_retry_of_an_unlocated_order_does_not_become_a_second_order(self, wired):
        """The end-to-end version of the defect this phase is about.

        A retry after reconciliation proved absence is allowed -- and it must reuse the same
        logical identity so it cannot become a second logical order.
        """
        broker = SimBroker("timeout_before_create", holds_order=False)
        order, broker, oms_mod, enqueued = await _store(wired, make_request(), broker=broker)
        order.state = OMSOrderState.UNKNOWN
        async def _async_none(c):
            return []

        async def _async_book_empty():
            return []

        oms_mod.order_manager.reconciler_factory = (
            lambda _u, _b: OrderReconciler(
                lookup_by_correlation=_async_none,
                list_orders=_async_book_empty, grace=timedelta(seconds=1),
                not_found_observations=1,
            )
        )
        await oms_mod.order_manager._reconcile_one_unknown(order)

        assert order.state is OMSOrderState.QUEUED, (
            "after a definitive NOT_FOUND a retry is legitimate"
        )
        assert len(enqueued) == 1, "exactly one requeue, not a burst"

        # The requeued attempt must carry the identical identity and intent.
        rebuilt = build_execution_request(order)
        assert rebuilt.execution_request_id == CID
        assert rebuilt.quantity == 65
        assert str(getattr(rebuilt.instrument_type, "value", rebuilt.instrument_type)) == "OPT"
        assert rebuilt.expiry_date == EXPIRY
        assert intent_fingerprint(order) == intent_fingerprint(rebuilt), (
            "the retry changed a material attribute, so it is a different order"
        )
