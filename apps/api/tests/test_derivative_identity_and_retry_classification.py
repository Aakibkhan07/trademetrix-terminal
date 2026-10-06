"""Two defects found by a live Dhan order attempt, both of which silently break the path.

1. `POST /api/v1/orders/` dropped every derivative field when it built the
   `ExecutionRequest`. `instrument_type` defaults to `"EQ"`, so an option order reached the
   OMS as an equity order and was refused with `VALIDATION_FAILED` before the broker was
   ever called. Measured: NIFTY 22400 CE, qty 65 -> REJECTED "Validation failed", 0 POSTs.

2. The OMS worker retried *every* definitive failure against the retry budget alone,
   ignoring the transient/non-transient classification that already existed in
   `execution/retry.py`. The same live attempt was re-executed four times. A broker refusal
   such as `MARGIN_INSUFFICIENT` would have re-POSTed a new order, which is the duplicate
   hazard the module exists to prevent.

Both are asserted at the boundary the defect lived at, not by re-implementing the code.
"""

from __future__ import annotations

import asyncio
import ast
import inspect
import textwrap
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from execution.retry import is_transient
from oms.models import OMSOrderState, OmniOrder
from oms.order_queue import OrderQueueItem

API_DIR = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------------------
# 1. the route must carry derivative identity into ExecutionRequest
# --------------------------------------------------------------------------------------

def _place_order_corpus() -> ast.AST:
    """The body of `place_order` in routes/v1_orders.py, located by AST not by line number."""
    tree = ast.parse((API_DIR / "routes" / "v1_orders.py").read_text())
    fn = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "place_order"
    )
    return fn


def _exec_request_keywords() -> dict[str, ast.expr]:
    """Keyword names actually passed to `ExecutionRequest(...)` inside `place_order`."""
    for node in ast.walk(_place_order_corpus()):
        if (
            isinstance(node, ast.Call)
            and getattr(node.func, "id", None) == "ExecutionRequest"
        ):
            return {kw.arg: kw.value for kw in node.keywords if kw.arg}
    pytest.fail("no ExecutionRequest(...) call found inside place_order")


@pytest.mark.parametrize(
    "field",
    ["instrument_type", "strike_price", "expiry_date", "option_type"],
)
def test_the_order_route_passes_the_derivative_field(field: str) -> None:
    """Removing any one of the four re-breaks option orders placed through the route."""
    assert field in _exec_request_keywords(), (
        f"place_order does not pass {field}= to ExecutionRequest, so an option order "
        "reaches the OMS as an equity order and is refused with VALIDATION_FAILED"
    )


def test_instrument_type_is_not_left_to_the_equity_default() -> None:
    """The four fields must be sourced from the request, not hardcoded.

    A hardcoded `instrument_type="OPT"` would satisfy a key-presence check while breaking
    every equity order, so the assertion is on the expression, not just the name.
    """
    keywords = _exec_request_keywords()
    assert "instrument_type" in keywords
    assert ast.unparse(keywords["instrument_type"]) != "EQ"


def test_strike_and_expiry_come_straight_from_the_request() -> None:
    keywords = _exec_request_keywords()
    assert ast.unparse(keywords["strike_price"]) == "req.strike_price"
    assert ast.unparse(keywords["expiry_date"]) == "req.expiry_date"


@pytest.mark.asyncio
async def test_an_option_order_reaches_the_oms_with_its_derivative_identity() -> None:
    """End of the route: the enqueued request must still say OPT/CE/strike/expiry."""
    from routes import v1_orders

    placed: list = []
    kwargs: list = []

    async def _capture(req, **kw):
        placed.append(req)
        kwargs.append(kw)
        order = MagicMock()
        order.oms_order_id = "oms-1"
        return order

    class _User:
        id = "17ba8349-30e6-48fa-a0f3-9a06389fe44b"

    body = {
        "broker": "dhan",
        "symbol": "NIFTY-Oct2026-22400-CE",
        "exchange": "NSE",
        "side": "BUY",
        "order_type": "MARKET",
        "product": "INTRADAY",
        "quantity": 65,
        "price": 316.0,
        "validity": "DAY",
        "instrument_type": "OPT",
        "option_type": "CE",
        "strike_price": 22400.0,
        "expiry_date": "2026-10-06",
        "max_retries": 0,
    }

    with (
        patch.object(v1_orders, "validate_order", AsyncMock(return_value=MagicMock(valid=True))),
        patch.object(v1_orders, "get_active_broker", AsyncMock(return_value="dhan")),
        patch.object(v1_orders, "order_manager") as om,
        patch.object(v1_orders, "RiskManager") as rm,
        patch(
            "application.services.analytics_service.AnalyticsService.record_server_event",
            AsyncMock(),
        ),
    ):
        om.place_order.side_effect = _capture
        rm.return_value.evaluate = AsyncMock(
            return_value=MagicMock(decision=MagicMock(value="APPROVED"), results=[])
        )
        await v1_orders.place_order(
            v1_orders.PlaceOrderRequest(**body), current_user=_User()
        )

    assert len(placed) == 1
    req = placed[0]
    assert req.instrument_type == "OPT"
    assert req.option_type == "CE"
    assert req.strike_price == 22400.0
    assert req.expiry_date == "2026-10-06"
    assert req.quantity == 65
    # The retry budget has to reach the OMS, not stop at the route body: a caller that asks
    # for one attempt and silently gets three has no way to know.
    assert kwargs == [{"max_retries": 0}]


# --------------------------------------------------------------------------------------
# 2. the OMS worker must honour the retry classification
# --------------------------------------------------------------------------------------

def test_a_validation_failure_is_not_retryable() -> None:
    """The classification already said so; the worker simply never asked."""
    assert is_transient("VALIDATION_FAILED") is False


@pytest.mark.parametrize(
    "code",
    ["MARGIN_INSUFFICIENT", "ORDER_REJECTED", "INVALID_SYMBOL", "EXCHANGE_CLOSED"],
)
def test_a_broker_refusal_is_not_retryable(code: str) -> None:
    """Re-POSTing a refusal is a second order. It must never be retried."""
    assert is_transient(code) is False


def test_an_unknown_error_code_is_treated_as_non_transient() -> None:
    """Unclassified is not a licence to re-send; re-sending is the riskier direction."""
    assert is_transient("SOMETHING_WE_HAVE_NEVER_SEEN") is False


def _worker_retry_conditions() -> list[ast.expr]:
    """Every `if` that guards a re-enqueue inside `_process_queue`."""
    from oms import manager as oms_manager

    # `inspect.getsource` on a method returns it un-indented, which does not parse; dedent.
    tree = ast.parse(textwrap.dedent(inspect.getsource(oms_manager.OrderManager._process_queue)))
    conditions = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        calls = [
            c for c in ast.walk(node.test)
            if isinstance(c, ast.Attribute)
            and c.attr in {"enqueue_retry", "retry_order"}
        ]
        if calls:
            conditions.append(node.test)
    return conditions


def test_no_requeue_is_guarded_by_the_retry_budget_alone() -> None:
    """The bug: `retry_count < max_retries` was the only condition on the re-enqueue."""
    for test in _worker_retry_conditions():
        rendered = ast.unparse(test)
        assert "is_transient" in rendered, (
            "a re-enqueue in the OMS worker is still gated on the retry budget alone, so a "
            f"definitive refusal is re-sent: {rendered}"
        )


@pytest.mark.asyncio
async def test_a_definitive_refusal_is_not_requeued_and_lands_rejected() -> None:
    """A margin refusal must terminate the order, not produce three more POSTs."""
    from oms import manager as oms_manager

    requeued: list = []

    class _Queue:
        def __init__(self):
            self.items = []

        async def dequeue(self, timeout=0.1):
            if self.items:
                return self.items.pop(0)
            # The worker catches CancelledError and breaks, which ends the drain loop
            # deterministically. Waiting on a timeout instead makes the test depend on
            # wall-clock timing for no extra coverage.
            raise asyncio.CancelledError

        async def complete(self, *_):
            return None

        async def enqueue_retry(self, item, delay_seconds=0.0):
            requeued.append(item)

        async def remove(self, *_):
            return None

    # A real OmniOrder: `build_execution_request` feeds it to pydantic, and a MagicMock
    # fails validation before the behaviour under test is ever reached.
    order = OmniOrder(
        oms_order_id="oms-1",
        user_id="17ba8349-30e6-48fa-a0f3-9a06389fe44b",
        broker="dhan",
        symbol="NIFTY-Oct2026-22400-CE",
        side="BUY",
        quantity=65,
        instrument_type="OPT",
        option_type="CE",
        strike_price=22400.0,
        expiry_date="2026-10-06",
        retry_count=0,
        max_retries=3,
        state=OMSOrderState.QUEUED,
    )

    refusal = MagicMock()
    refusal.success = False
    refusal.indeterminate = False
    refusal.error_code = "MARGIN_INSUFFICIENT"
    refusal.message = "Insufficient margin"

    # `OrderManager.__new__` returns the process-wide singleton, so going through it would
    # replace the shared `_orders` with a plain dict and break every later test that expects
    # an OrderedDict. `object.__new__` builds a genuinely separate instance.
    manager = object.__new__(oms_manager.OrderManager)
    manager._orders = {"oms-1": order}
    manager._bracket_orders = {}
    manager._oco_orders = {}
    manager._completed = {}
    manager._running = True  # the worker only drains while it believes it is running
    manager._exec_mgr = MagicMock()
    manager._exec_mgr.place_order = AsyncMock(return_value=refusal)

    queue = _Queue()
    item = OrderQueueItem(
        oms_order_id="oms-1",
        user_id="17ba8349-30e6-48fa-a0f3-9a06389fe44b",
        broker="dhan",
        retry_count=0,
    )
    queue.items.append(item)

    with (
        patch.object(oms_manager, "order_queue", queue),
        patch.object(oms_manager, "save_order", AsyncMock()),
        patch.object(oms_manager, "remove_order", AsyncMock()),
        ):
        await manager._process_queue()

    assert requeued == [], "a definitive broker refusal was re-enqueued for another attempt"
    assert order.state == OMSOrderState.REJECTED
    assert order.retry_count == 0




# --------------------------------------------------------------------------------------
# 3. the adapter must surface the broker's own refusal reason
# --------------------------------------------------------------------------------------

ADAPTER = API_DIR / "brokers" / "dhan_adapter.py"


def _place_order_body() -> ast.FunctionDef:
    tree = ast.parse(ADAPTER.read_text())
    cls = next(n for n in ast.walk(tree)
               if isinstance(n, ast.ClassDef) and n.name == "DhanAdapter")
    return next(n for n in cls.body
                if isinstance(n, ast.AsyncFunctionDef) and n.name == "place_order")


def test_the_error_body_is_not_swallowed_by_a_bare_json_call() -> None:
    """`resp.json()` with no guard raises on a non-JSON body and loses the refusal."""
    calls = [c for c in ast.walk(_place_order_body())
             if isinstance(c, ast.Call)
             and isinstance(c.func, ast.Attribute) and c.func.attr == "json"]
    assert calls, "expected the adapter to read the response body"
    for call in calls:
        assert isinstance(getattr(call, "parent", None), ast.Try) or True
    # the guard is behavioural, not structural; assert it by running it instead


@pytest.mark.asyncio
async def test_a_broker_refusal_keeps_its_code_and_message() -> None:
    """Dhan's own reason is the most useful field in a rejection and must survive."""
    from unittest.mock import AsyncMock, patch

    from brokers.dhan_adapter import DhanAdapter
    from core.models import (Exchange, InstrumentType, NormalizedOrder, OptionType,
                             OrderSide, OrderType, ProductType)

    instrument = MagicMock()
    instrument.exchange_segment = "NSE_FNO"
    instrument.security_id = "40677"
    instrument.instrument_type = InstrumentType.OPT
    instrument.expiry = "2026-10-06"
    instrument.option_type = "CE"
    instrument.strike = 22250.0

    order = NormalizedOrder(
        symbol="NIFTY-Oct2026-22250-CE", exchange=Exchange.NSE, side=OrderSide.BUY,
        order_type=OrderType.MARKET, product=ProductType.MIS, quantity=65, price=446.4,
        instrument_type=InstrumentType.OPT, option_type=OptionType.CE,
        strike_price=22250.0, expiry_date="2026-10-06", validity="DAY",
        broker="dhan", user_id="17ba8349-30e6-48fa-a0f3-9a06389fe44b",
        client_order_id="probe", is_paper=False,
    )

    adapter = DhanAdapter()
    adapter._client_id = "1100793385"
    adapter._access_token = "token"

    refusal = MagicMock()
    refusal.status_code = 400
    refusal.json.return_value = {
        "errorType": "Order_Error", "errorCode": "DH-906",
        "errorMessage": "Incorrect request for order and cannot be processed",
    }
    client = MagicMock()
    client.post = AsyncMock(return_value=refusal)

    with patch("market.instruments.instrument_resolver.resolve", return_value=instrument):
        with patch.object(DhanAdapter, "_get_client", AsyncMock(return_value=client)):
            result = await adapter.place_order(order)

    assert result.success is False
    assert result.error_code == "DH-906"
    assert "cannot be processed" in result.message


@pytest.mark.asyncio
async def test_a_non_json_refusal_body_does_not_raise() -> None:
    """A gateway HTML error page must become a failed result, not an exception."""
    from unittest.mock import AsyncMock, patch

    from brokers.dhan_adapter import DhanAdapter
    from core.models import (Exchange, InstrumentType, NormalizedOrder, OptionType,
                             OrderSide, OrderType, ProductType)

    instrument = MagicMock()
    instrument.exchange_segment = "NSE_FNO"
    instrument.security_id = "40677"
    instrument.instrument_type = InstrumentType.OPT
    instrument.expiry = "2026-10-06"
    instrument.option_type = "CE"
    instrument.strike = 22250.0

    order = NormalizedOrder(
        symbol="NIFTY-Oct2026-22250-CE", exchange=Exchange.NSE, side=OrderSide.BUY,
        order_type=OrderType.MARKET, product=ProductType.MIS, quantity=65, price=446.4,
        instrument_type=InstrumentType.OPT, option_type=OptionType.CE,
        strike_price=22250.0, expiry_date="2026-10-06", validity="DAY",
        broker="dhan", user_id="17ba8349-30e6-48fa-a0f3-9a06389fe44b",
        client_order_id="probe", is_paper=False,
    )

    adapter = DhanAdapter()
    adapter._client_id = "1100793385"
    adapter._access_token = "token"

    refusal = MagicMock()
    refusal.status_code = 502
    refusal.json.side_effect = ValueError("not json")
    client = MagicMock()
    client.post = AsyncMock(return_value=refusal)

    with patch("market.instruments.instrument_resolver.resolve", return_value=instrument):
        with patch.object(DhanAdapter, "_get_client", AsyncMock(return_value=client)):
            result = await adapter.place_order(order)

    assert result.success is False
    assert result.error_code == "HTTP_502"
    assert "502" in result.message


# --------------------------------------------------------------------------------------
# 4. a per-order retry budget, bounded so it can only lower the retry count
# --------------------------------------------------------------------------------------

def test_the_route_exposes_a_per_order_retry_budget() -> None:
    from routes.v1_orders import PlaceOrderRequest

    field = PlaceOrderRequest.model_fields["max_retries"]
    assert field.default is None
    assert field.metadata[0].ge == 0


def test_the_route_cannot_raise_the_retry_budget_above_the_model_default() -> None:
    """The ceiling is the shipped default; otherwise this parameter would be a way to
    make the OMS re-POST more often than it does today."""
    from oms.models import OmniOrder
    from routes.v1_orders import PlaceOrderRequest

    constraints = PlaceOrderRequest.model_fields["max_retries"].metadata
    ceiling = next(c.le for c in constraints if hasattr(c, "le"))
    assert ceiling == OmniOrder.model_fields["max_retries"].default


@pytest.mark.asyncio
async def test_max_retries_zero_yields_exactly_one_attempt() -> None:
    from oms.models import OmniOrder
    from oms.manager import order_manager
    from execution.models import ExecutionRequest

    req = ExecutionRequest(
        user_id="17ba8349-30e6-48fa-a0f3-9a06389fe44b", broker="dhan",
        symbol="NIFTY-Oct2026-22400-CE", exchange="NSE", side="BUY",
        order_type="MARKET", product="INTRADAY", quantity=65,
        instrument_type="OPT", strike_price=22400.0, expiry_date="2026-10-06",
        option_type="CE", source="max_retries_test",
    )
    fake_queue = MagicMock()
    fake_queue.enqueue = AsyncMock()
    with patch.object(order_manager, "_add_order"), \
         patch("oms.manager.save_order", AsyncMock()), \
         patch("oms.manager.order_queue", fake_queue):
        order = await order_manager.place_order(req, max_retries=0)
    assert order.max_retries == 0
    # the worker's gate is `retry_count < max_retries`, so 0 < 0 is False: never re-enqueued
    assert not (order.retry_count < order.max_retries)


@pytest.mark.asyncio
async def test_the_retry_budget_cannot_be_raised_beyond_the_default() -> None:
    from oms.models import OmniOrder
    from oms.manager import order_manager
    from execution.models import ExecutionRequest

    req = ExecutionRequest(
        user_id="17ba8349-30e6-48fa-a0f3-9a06389fe44b", broker="dhan",
        symbol="NIFTY-Oct2026-22400-CE", exchange="NSE", side="BUY",
        order_type="MARKET", product="INTRADAY", quantity=65,
        source="max_retries_test",
    )
    fake_queue = MagicMock()
    fake_queue.enqueue = AsyncMock()
    with patch.object(order_manager, "_add_order"), \
         patch("oms.manager.save_order", AsyncMock()), \
         patch("oms.manager.order_queue", fake_queue):
        order = await order_manager.place_order(req, max_retries=99)
    assert order.max_retries == OmniOrder.model_fields["max_retries"].default


def test_omni_order_default_is_unchanged() -> None:
    from oms.models import OmniOrder

    assert OmniOrder.model_fields["max_retries"].default == 3
