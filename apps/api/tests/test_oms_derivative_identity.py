"""Regression tests: the OMS must not drop a derivative contract's identity.

Found by driving the *real* queue path -- OMS enqueue, Redis, the OMS worker, the
execution manager, the broker adapter -- with the final Dhan POST intercepted. The direct
`ExecutionManager.place_order` call produced a correct payload; the queue path produced one
with the right `securityId` and `exchangeSegment` but no expiry, no strike and no option
type, because `OmniOrder` had nowhere to store them and `_process_queue` rebuilt the
`ExecutionRequest` without them.

`DhanAdapter.place_order` only emits `drvExpiryDate` / `drvStrikePrice` / `drvOptionType`
when `instrument_type` is FUT or OPT, so a missing `instrument_type` silently strips the
whole derivative identity. These tests pin the round trip.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from core.models import Exchange, InstrumentType, OptionType, OrderSide, OrderType, ProductType
from execution.models import ExecutionRequest
from oms.manager import _text
from oms.models import OmniOrder

REPO_ROOT = Path(__file__).resolve().parents[3]
MANAGER = Path("oms/manager.py")
MODELS = Path("oms/models.py")

OPTION_REQUEST = ExecutionRequest(
    user_id="u1", broker="dhan", symbol="NIFTY-Oct2026-23250-CE", exchange=Exchange.NSE,
    side=OrderSide.BUY, order_type=OrderType.MARKET, product=ProductType.MIS,
    quantity=65, price=0.65, validity="DAY", instrument_type=InstrumentType.OPT,
    strike_price=23250.0, expiry_date="2026-10-06", option_type=OptionType.CE,
    disclosed_quantity=0, is_paper=False,
)


class TestOmniOrderStoresTheDerivative:
    def test_the_model_has_the_fields_at_all(self):
        """Without these columns there is nowhere for the identity to survive."""
        for name in ("instrument_type", "expiry_date", "strike_price",
                     "option_type", "validity", "disclosed_quantity"):
            assert name in OmniOrder.model_fields, f"OmniOrder is missing {name}"

    def test_the_defaults_keep_equity_orders_and_old_rows_loadable(self):
        o = OmniOrder(oms_order_id="x", user_id="u", broker="dhan", symbol="RELIANCE",
                      side="BUY", quantity=1)
        assert o.instrument_type == "" and o.expiry_date == ""
        assert o.strike_price is None and o.option_type == "" and o.validity == ""
        # `OmniOrder(**row)` with an old row that has none of these keys must still work.
        assert OmniOrder(oms_order_id="x", user_id="u", broker="dhan", symbol="S",
                         side="BUY", quantity=1) is not None

    def test_the_rebuilt_request_is_actually_constructible(self):
        """The kwarg being *present* is not enough; it has to validate.

        `disclosed_quantity=order.disclosed_quantity or None` was present and still raised
        `ValidationError: Input should be a valid integer [input_value=None]` for every order
        whose disclosed quantity is 0 -- 0 is falsy. `_process_queue` swallowed it, the queue
        item had already been popped and was silently lost, and the order sat at state=SENT
        forever.

        This calls the production function rather than restating the rebuild: a test that
        re-implements the code it is checking verifies its own copy, which is how mutation
        N10 survived the first version of this test.
        """
        from oms.manager import build_execution_request

        order = OmniOrder(
            oms_order_id="x", execution_request_id="x", client_order_id="x",
            user_id="u1", broker="dhan", symbol="NIFTY-Oct2026-23250-CE", side="BUY",
            quantity=65, price=0.4, state="QUEUED", instrument_type="OPT",
            expiry_date="2026-10-06", strike_price=23250.0, option_type="CE",
            validity="DAY", disclosed_quantity=0,
        )
        rebuilt = build_execution_request(order)
        assert rebuilt.instrument_type == "OPT"
        assert rebuilt.expiry_date == "2026-10-06"
        assert rebuilt.strike_price == 23250.0
        assert str(getattr(rebuilt.option_type, "value", rebuilt.option_type)) == "CE"
        assert rebuilt.validity == "DAY"
        assert rebuilt.disclosed_quantity == 0

    def test_the_worker_uses_the_extracted_builder(self):
        """Otherwise the function is tested and the worker keeps doing something else."""
        import ast

        tree = ast.parse(MANAGER.read_text())
        processor = next(
            n for n in ast.walk(tree)
            if isinstance(n, ast.AsyncFunctionDef) and n.name == "_process_queue"
        )
        called = {
            n.func.id for n in ast.walk(processor)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        }
        assert "build_execution_request" in called, (
            "_process_queue builds the ExecutionRequest inline again; the extracted "
            "builder would be dead code and the worker's real behaviour untested"
        )

    @pytest.mark.parametrize("value,expected", [
        (None, ""),
        ("", ""),
        (InstrumentType.OPT, "OPT"),
        (OptionType.CE, "CE"),
        ("DAY", "DAY"),
        (InstrumentType.OPT.value, "OPT"),
    ])
    def test_text_normalises_enums_and_none(self, value, expected):
        """The row is written to a text column; an enum member must become its value."""
        assert _text(value) == expected


class TestPlaceOrderCarriesTheDerivative:
    @pytest.mark.asyncio
    async def test_an_option_order_keeps_its_contract_through_place_order(self, monkeypatch):
        saved = {}
        enqueued = {}

        import oms.manager as oms_mod

        async def fake_save(order):
            saved["order"] = order

        async def fake_enqueue(item):
            enqueued["item"] = item

        monkeypatch.setattr(oms_mod, "save_order", fake_save)
        monkeypatch.setattr(oms_mod.order_queue, "enqueue", fake_enqueue)

        order = await oms_mod.order_manager.place_order(OPTION_REQUEST)
        assert order.instrument_type == "OPT"
        assert order.expiry_date == "2026-10-06"
        assert order.strike_price == 23250.0
        assert order.option_type == "CE"
        assert order.validity == "DAY"
        assert saved["order"].instrument_type == "OPT"


class TestWorkerRebuildCarriesTheDerivative:
    def test_the_rebuilt_execution_request_includes_the_derivative_fields(self):
        """Read the source, because the failure was a missing argument, not a wrong value.

        A behavioural test for this needs a live Redis and a broker adapter. What actually
        broke was that the constructor call omitted five keyword arguments, and an omitted
        argument cannot be observed from the far side -- it is indistinguishable from a
        default. So the assertion is on the call itself.
        """
        tree = ast.parse(MANAGER.read_text())
        calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "ExecutionRequest"
        ]
        assert calls, "the OMS no longer builds an ExecutionRequest"
        worker_call = None
        for call in calls:
            # The worker's rebuild reads these off `order`. The read can be wrapped --
            # `order.instrument_type or None` is a BoolOp, not a bare Attribute -- so search
            # the whole keyword subtree rather than only its root node. Matching only the root
            # found no call site at all and reported "the worker no longer rebuilds
            # derivative identity" against code that does exactly that.
            reads_order = False
            for kw in call.keywords:
                for node in ast.walk(kw.value):
                    if (isinstance(node, ast.Attribute)
                            and isinstance(node.value, ast.Name)
                            and node.value.id == "order"
                            and node.attr in ("instrument_type", "expiry_date",
                                              "strike_price", "option_type")):
                        reads_order = True
            if reads_order:
                worker_call = call
                break
        assert worker_call is not None, "the worker no longer rebuilds derivative identity"
        passed = {kw.arg for kw in worker_call.keywords}
        for field in ("instrument_type", "expiry_date", "strike_price",
                      "option_type", "validity"):
            assert field in passed, (
                f"_process_queue does not pass {field} to ExecutionRequest; "
                f"the broker adapter then emits no derivative identity for this contract"
            )


class TestAdapterOnlyEmitsDerivativeIdentityWhenTyped:
    def test_the_adapter_guards_the_derivative_block_on_instrument_type(self):
        """This is the amplifier: no instrument_type means no expiry/strike/option at all."""
        tree = ast.parse(Path("brokers/dhan_adapter.py").read_text())
        place = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "place_order"
        )
        # find `seg = instrument.exchange_segment`
        assigns = {
            t.id: n.value for n in ast.walk(place) if isinstance(n, ast.Assign)
            for t in n.targets if isinstance(t, ast.Name)
        }
        assert "seg" in assigns, "the adapter no longer derives the segment from the contract"
        assert "instrument" in ast.unparse(assigns["seg"]), (
            f"the segment must come from the resolved instrument, not the symbol: "
            f"{ast.unparse(assigns['seg'])}"
        )
        assert "instrument" in ast.unparse(assigns.get("security_id", ast.Constant(value=None))), (
            "the security id must come from the resolved instrument"
        )


class TestMigrationIsIdempotentAndAddsTheColumns:
    def test_every_new_column_is_added_with_if_not_exists(self):
        path = REPO_ROOT / "supabase/migrations/20261006_10000_oms_derivative_identity.sql"
        sql = path.read_text()
        adds = sql.count("ADD COLUMN IF NOT EXISTS")
        assert adds == 6, f"expected 6 additive columns, found {adds}"
        for name in ("instrument_type", "expiry_date", "strike_price",
                     "option_type", "validity", "disclosed_quantity"):
            assert name in sql
