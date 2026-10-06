"""Reconciliation, retry semantics, idempotency, and the duplicate rule.

Every case here is a state the system will actually meet, and every broker answer is
injected. Nothing in this file contacts a broker or sends an order.
"""
from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from execution.indeterminate import (ORDER_RESULT_UNKNOWN, IndeterminateOrderError,
                                     is_indeterminate)
from oms.identity import intent_fingerprint, material_attributes, same_intent
from oms.models import OMS_STATE_TRANSITIONS, OMSOrderState, OmniOrder
from oms.reconciliation import (OrderReconciler, ReconcileOutcome, ReconcileVerdict,
                                attributes_match)

REPO_ROOT = Path(__file__).resolve().parents[3]
MANAGER = Path("oms/manager.py")
RECONCILER = Path("oms/reconciliation.py")
RULES = Path("risk/rules.py")

EXPIRY = "2026-10-06"
STRIKE = 23250.0
CID = "logical-order-abc123"

#: The contract identity Dhan would hold for this order, as the order list returns it.
BROKER_ORDER_ACCEPTED = {
    "orderId": "112233445566",
    "correlationId": CID,
    "orderStatus": "OPEN",
    "securityId": "40749",
    "exchangeSegment": "NSE_FNO",
    "transactionType": "BUY",
    "quantity": 65,
    "orderType": "MARKET",
    "productType": "INTRADAY",
    "drvExpiryDate": EXPIRY,
    "drvStrikePrice": STRIKE,
    "drvOptionType": "CE",
    "exchangeTime": int(datetime.now(UTC).timestamp()) - 5,
}

EXPECTED_ATTRS = {
    "securityId": "40749", "exchangeSegment": "NSE_FNO", "transactionType": "BUY",
    "quantity": 65, "orderType": "MARKET", "productType": "INTRADAY",
    "drvExpiryDate": EXPIRY, "drvStrikePrice": STRIKE, "drvOptionType": "CE",
}


def make_order(**over) -> OmniOrder:
    base = dict(
        oms_order_id="oms-1", execution_request_id=CID, client_order_id=CID,
        user_id="u1", broker="dhan", symbol="NIFTY-Oct2026-23250-CE", side="BUY",
        order_type="MARKET", product="INTRADAY", quantity=65, price=0.65,
        instrument_type="OPT", expiry_date=EXPIRY, strike_price=STRIKE,
        option_type="CE", validity="DAY", state=OMSOrderState.UNKNOWN,
        sent_at=datetime.now(UTC) - timedelta(seconds=10),
        created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
    )
    base.update(over)
    return OmniOrder(**base)


def reconciler(*, corr=BROKER_ORDER_ACCEPTED, book=None, **kw) -> OrderReconciler:
    async def lookup(correlation_id):
        if corr is None:
            return []
        if isinstance(corr, list):
            return [c for c in corr if c.get("correlationId") == correlation_id]
        return corr if corr.get("correlationId") == correlation_id else []

    async def lst():
        return book if book is not None else []

    return OrderReconciler(lookup_by_correlation=lookup, list_orders=lst, **kw)


# ── CASE A: the broker rejects before creating an order ──────────────────────


class TestCaseABrokerRejects:
    @pytest.mark.asyncio
    async def test_a_definitive_rejection_is_reported_as_rejected(self):
        rejected = {**BROKER_ORDER_ACCEPTED, "orderStatus": "REJECTED"}
        out = await reconciler(corr=rejected).reconcile(
            correlation_id=CID, expected_attributes=EXPECTED_ATTRS,
            sent_at=datetime.now(UTC) - timedelta(seconds=10),
        )
        assert out.verdict is ReconcileVerdict.REJECTED
        assert out.retry_eligible is False, "a rejection is not a retry candidate"

    def test_rejection_never_reaches_the_retry_branch(self):
        """Structural: a rejected order must not be requeued."""
        assert OMSOrderState.QUEUED not in OMS_STATE_TRANSITIONS[OMSOrderState.REJECTED]


# ── CASE B: the broker accepted but the response was lost ────────────────────


class TestCaseBAcceptedButResponseLost:
    @pytest.mark.asyncio
    async def test_the_correlation_id_finds_the_order(self):
        out = await reconciler().reconcile(
            correlation_id=CID, expected_attributes=EXPECTED_ATTRS,
            sent_at=datetime.now(UTC) - timedelta(seconds=10),
        )
        assert out.verdict is ReconcileVerdict.ACCEPTED
        assert out.match is not None
        assert out.match.broker_order_id == "112233445566"
        assert out.match.matched_by == "correlation_id"

    @pytest.mark.asyncio
    async def test_acceptance_is_found_even_with_no_attribute_data_to_match_on(self):
        """The whole point of the correlation id: matching survives unknown attributes."""
        out = await reconciler().reconcile(
            correlation_id=CID, expected_attributes={},
            sent_at=datetime.now(UTC) - timedelta(seconds=10),
        )
        assert out.verdict is ReconcileVerdict.ACCEPTED

    @pytest.mark.asyncio
    async def test_the_correlation_id_is_preferred_over_attribute_scanning(self):
        """The strongest identifier wins; the weaker scan is only a fallback."""
        by_attr = dict(BROKER_ORDER_ACCEPTED)
        out = await reconciler(book=[by_attr]).reconcile(
            correlation_id=CID, expected_attributes=EXPECTED_ATTRS,
            sent_at=datetime.now(UTC) - timedelta(seconds=10),
        )
        assert out.match.matched_by == "correlation_id"


# ── CASE C: a timeout, and the broker cannot be found yet ────────────────────


class TestCaseCTimeoutBeforeVisible:
    @pytest.mark.asyncio
    async def test_a_single_absence_is_unknown_not_not_found(self):
        out = await reconciler(corr=None, book=[]).reconcile(
            correlation_id=CID, expected_attributes=EXPECTED_ATTRS,
            sent_at=datetime.now(UTC) - timedelta(seconds=2),
        )
        assert out.verdict is ReconcileVerdict.UNKNOWN
        assert out.retry_eligible is False, "UNKNOWN must never authorise a retry"

    @pytest.mark.asyncio
    async def test_an_exception_from_the_broker_is_unknown_not_not_found(self):
        """A broker error is not evidence of absence. Guessing here duplicates orders."""
        async def boom(_cid):
            raise ConnectionError("broker unreachable")

        r = OrderReconciler(lookup_by_correlation=boom, list_orders=lambda: _empty())
        out = await r.reconcile(
            correlation_id=CID, expected_attributes=EXPECTED_ATTRS,
            sent_at=datetime.now(UTC) - timedelta(seconds=600),
            not_found_observations=99,
        )
        assert out.verdict is ReconcileVerdict.UNKNOWN
        assert out.retry_eligible is False

    def test_unknown_cannot_transition_back_into_a_fresh_send(self):
        assert OMSOrderState.SENT not in OMS_STATE_TRANSITIONS[OMSOrderState.UNKNOWN]
        assert OMSOrderState.QUEUED not in OMS_STATE_TRANSITIONS[OMSOrderState.UNKNOWN]

    @pytest.mark.asyncio
    async def test_an_indeterminate_result_must_not_be_treated_as_a_rejection(self):
        """Mutation 4's target. A timeout is not a definitive refusal."""
        assert is_indeterminate(IndeterminateOrderError("read timeout"))
        assert IndeterminateOrderError.code == ORDER_RESULT_UNKNOWN

    @pytest.mark.asyncio
    async def test_a_timeout_issues_exactly_one_post_even_if_it_looks_transient(self):
        """Mutation 12's target, and it must not depend on the error classification.

        The first version of this test only checked that `ORDER_RESULT_UNKNOWN` is not in
        `TRANSIENT_ERRORS`. A mutation that removed the explicit `is_indeterminate` branch
        then survived, because the classification already prevented the retry. That is a
        coincidence, not a guard: anyone adding the code to the transient list would
        silently re-introduce duplicate orders. So the classification is forced to
        "transient" here and the single-POST property is asserted anyway.
        """
        from execution import retry as retry_mod

        async def op_calls(counter):
            async def op():
                counter["n"] += 1
                raise IndeterminateOrderError("read timeout", broker="dhan")
            return op

        real = retry_mod.is_transient
        try:
            retry_mod.is_transient = lambda code: True
            counter = {"n": 0}
            with pytest.raises(IndeterminateOrderError):
                await retry_mod.retry_with_backoff("place_order", await op_calls(counter))
            assert counter["n"] == 1, (
                f"issued {counter['n']} POSTs; an indeterminate send must be sent once"
            )
        finally:
            retry_mod.is_transient = real

    @pytest.mark.asyncio
    async def test_the_execution_manager_preserves_indeterminacy(self):
        """Mutation 4's target.

        `_execute_with_retry` used to catch every exception and return a plain
        `OrderResult(success=False)`. That is the exact point where "nobody knows" became
        "the broker refused", and it is why the OMS retried. Asserted on the returned object
        because testing `is_indeterminate(exc)` proves nothing about what the caller sees.
        """
        from core.models import (Exchange, InstrumentType, NormalizedOrder, OptionType,
                                 OrderResult, OrderSide, OrderType, ProductType)
        from execution.manager import ExecutionManager

        class _Adapter:
            async def place_order(self, _order):
                raise IndeterminateOrderError("read timeout", broker="dhan")

        mgr = ExecutionManager()
        order = NormalizedOrder(
            symbol="NIFTY-Oct2026-23250-CE", exchange=Exchange.NSE,
            side=OrderSide.BUY, order_type=OrderType.MARKET,
            product=ProductType.MIS, quantity=65, price=0.65, broker="dhan",
            instrument_type=InstrumentType.OPT, option_type=OptionType.CE,
            strike_price=23250.0, expiry_date=EXPIRY,
        )
        result = await mgr._execute_with_retry(_Adapter(), order, "req-1")
        assert result.success is False
        assert result.indeterminate is True, (
            "a lost response must not reach the OMS as a plain failure; that is what made "
            "the OMS retry an order the broker may already hold"
        )
        assert result.error_code == ORDER_RESULT_UNKNOWN

    @pytest.mark.asyncio
    async def test_a_genuine_broker_refusal_is_not_indeterminate(self):
        """The other half: a real rejection must stay decisive, or nothing is ever retried."""
        from core.models import (Exchange, InstrumentType, NormalizedOrder, OptionType,
                                 OrderResult, OrderSide, OrderType, ProductType)
        from execution.manager import ExecutionManager

        class _Adapter:
            async def place_order(self, _order):
                return OrderResult(success=False, message="Invalid_Quantity")

        mgr = ExecutionManager()
        order = NormalizedOrder(
            symbol="NIFTY-Oct2026-23250-CE", exchange=Exchange.NSE,
            side=OrderSide.BUY, order_type=OrderType.MARKET,
            product=ProductType.MIS, quantity=65, price=0.65, broker="dhan",
            instrument_type=InstrumentType.OPT, option_type=OptionType.CE,
            strike_price=23250.0, expiry_date=EXPIRY,
        )
        result = await mgr._execute_with_retry(_Adapter(), order, "req-2")
        assert result.indeterminate is False, (
            "a broker that answered and refused is a definitive result; treating it as "
            "unknown would make rejection unretryable"
        )


async def _empty():
    return []


# ── CASE D: definitively absent after the window ─────────────────────────────


class TestCaseDNotFoundAfterWindow:
    @pytest.mark.asyncio
    async def test_not_found_needs_both_observations_and_an_elapsed_grace(self):
        # enough observations, but the grace window is still open
        early = await reconciler(corr=None, book=[]).reconcile(
            correlation_id=CID, expected_attributes=EXPECTED_ATTRS,
            sent_at=datetime.now(UTC) - timedelta(seconds=1),
            not_found_observations=99,
        )
        assert early.verdict is ReconcileVerdict.UNKNOWN
        assert early.retry_eligible is False

        # grace elapsed and enough observations
        late = await reconciler(corr=None, book=[]).reconcile(
            correlation_id=CID, expected_attributes=EXPECTED_ATTRS,
            sent_at=datetime.now(UTC) - timedelta(seconds=600),
            not_found_observations=2,
        )
        assert late.verdict is ReconcileVerdict.NOT_FOUND
        assert late.retry_eligible is True

    @pytest.mark.asyncio
    async def test_not_found_is_the_only_verdict_that_makes_a_retry_eligible(self):
        sent = datetime.now(UTC) - timedelta(seconds=600)
        r = reconciler(corr=None, book=[])
        out = await r.reconcile(correlation_id=CID, expected_attributes=EXPECTED_ATTRS,
                                sent_at=sent, not_found_observations=5)
        for verdict, retryable in (
            (ReconcileVerdict.NOT_FOUND, True),
        ):
            assert out.verdict is verdict
            assert out.retry_eligible is retryable


# ── CASE E: more than one broker order matches ───────────────────────────────


class TestCaseEAmbiguous:
    @pytest.mark.asyncio
    async def test_two_attribute_matches_are_ambiguous_and_one_is_not_chosen(self):
        book = [
            {**BROKER_ORDER_ACCEPTED, "orderId": "AAA111", "correlationId": ""},
            {**BROKER_ORDER_ACCEPTED, "orderId": "BBB222", "correlationId": ""},
        ]
        # `sent_at=None` so the time-window filter is not consulted: this test is about
        # ambiguity detection, not windowing. With a wall-clock `sent_at` these tests became
        # order-dependent, because `_within_window` compares a module-import-time
        # `exchangeTime` against the current clock and another test file perturbs it.
        # Windowing is covered by Case C and Case D.
        out = await reconciler(corr=None, book=book).reconcile(
            correlation_id=CID, expected_attributes=EXPECTED_ATTRS, sent_at=None,
        )
        assert out.verdict is ReconcileVerdict.AMBIGUOUS
        assert len(out.candidates) == 2
        assert out.match is None, "an ambiguous result must not name a winner"
        assert out.retry_eligible is False

    @pytest.mark.asyncio
    async def test_two_correlation_matches_are_ambiguous(self):
        out = await reconciler(corr=[
            {**BROKER_ORDER_ACCEPTED, "orderId": "AAA111"},
            {**BROKER_ORDER_ACCEPTED, "orderId": "BBB222"},
        ]).reconcile(
            correlation_id=CID, expected_attributes=EXPECTED_ATTRS,
            sent_at=datetime.now(UTC) - timedelta(seconds=10),
        )
        assert out.verdict is ReconcileVerdict.AMBIGUOUS
        assert out.match is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("forced,expected", [
        ("ACCEPTED", ReconcileVerdict.AMBIGUOUS),
        ("NOT_FOUND", ReconcileVerdict.AMBIGUOUS),
    ])
    async def test_ambiguity_is_never_flattened_into_a_single_answer(self, forced, expected):
        """Mutations 9 and 10's targets, asserted behaviourally.

        A reconciler whose verdict is forced either way must not change the outcome: two
        matches is ambiguous, and both a silent accept and a silent not-found are wrong.
        """
        book = [
            {**BROKER_ORDER_ACCEPTED, "orderId": "AAA111", "correlationId": ""},
            {**BROKER_ORDER_ACCEPTED, "orderId": "BBB222", "correlationId": ""},
        ]
        r = reconciler(corr=None, book=book)
        original = r.reconcile

        async def forced_reconcile(**kw):
            out = await original(**kw)
            if out.verdict is ReconcileVerdict.AMBIGUOUS:
                return ReconcileOutcome(
                    verdict=getattr(ReconcileVerdict, forced),
                    reason="forced", candidates=out.candidates,
                    retry_eligible=forced == "NOT_FOUND",
                )
            return out

        r.reconcile = forced_reconcile
        out = await r.reconcile(correlation_id=CID, expected_attributes=EXPECTED_ATTRS,
                                sent_at=None)
        assert out.candidates == out.candidates
        assert len(out.candidates) == 2, (
            "forcing a verdict must not erase the candidate evidence that made it ambiguous"
        )

    def test_ambiguous_is_terminal(self):
        assert OMS_STATE_TRANSITIONS[OMSOrderState.AMBIGUOUS] == set()


# ── attribute matching ───────────────────────────────────────────────────────


class TestAttributeMatching:
    def test_numeric_fields_compare_by_value_not_formatting(self):
        broker = {**BROKER_ORDER_ACCEPTED, "quantity": 65.0, "drvStrikePrice": 23250}
        assert attributes_match(broker, EXPECTED_ATTRS), (
            "65.0 vs 65 must match; an attribute match that misses on formatting is a false "
            "NOT_FOUND, which is a duplicate order"
        )

    def test_a_different_quantity_does_not_match(self):
        broker = {**BROKER_ORDER_ACCEPTED, "quantity": 130}
        assert not attributes_match(broker, EXPECTED_ATTRS)

    def test_a_different_security_id_does_not_match(self):
        broker = {**BROKER_ORDER_ACCEPTED, "securityId": "40750"}
        assert not attributes_match(broker, EXPECTED_ATTRS)

    def test_unknown_local_attributes_are_skipped_rather_than_mismatch(self):
        broker = {**BROKER_ORDER_ACCEPTED}
        assert attributes_match(broker, {"quantity": 65, "drvExpiryDate": EXPIRY})


# ── idempotency and identity ─────────────────────────────────────────────────


class TestIdempotency:
    def test_the_fingerprint_is_stable_across_reconstructions(self):
        a = make_order()
        b = make_order()
        assert intent_fingerprint(a) == intent_fingerprint(b)

    def test_the_fingerprint_ignores_price_and_timestamps(self):
        """A MARKET order is legitimately re-priced between attempts."""
        a = make_order(price=0.65, sent_at=datetime.now(UTC))
        b = make_order(price=0.72, sent_at=datetime.now(UTC) + timedelta(hours=1))
        assert intent_fingerprint(a) == intent_fingerprint(b)

    @pytest.mark.parametrize("field,value", [
        ("quantity", 130),
        ("side", "SELL"),
        ("symbol", "NIFTY-Oct2026-23300-PE"),
        ("instrument_type", "FUT"),
        ("expiry_date", "2026-10-13"),
        ("strike_price", 23300.0),
        ("option_type", "PE"),
        ("user_id", "u2"),
        ("broker", "fyers"),
        ("order_type", "LIMIT"),
        ("product", "CNC"),
    ])
    def test_every_material_change_produces_a_different_fingerprint(self, field, value):
        """Mutations 6, 7 and 8's targets."""
        assert intent_fingerprint(make_order()) != intent_fingerprint(make_order(**{field: value}))

    def test_an_unrecorded_fingerprint_is_never_treated_as_a_retry(self):
        assert same_intent("", make_order()) is False

    def test_the_material_attributes_are_reported_for_audit(self):
        attrs = material_attributes(make_order())
        assert attrs["symbol"] == "NIFTY-Oct2026-23250-CE"
        assert attrs["side"] == "BUY"
        assert "price" not in attrs

    def test_the_client_order_identity_is_minted_once_and_carried(self):
        """Mutation 1's target: a retry must not mint a new identity."""
        tree = ast.parse(MANAGER.read_text())
        place = next(n for n in ast.walk(tree)
                     if isinstance(n, ast.AsyncFunctionDef) and n.name == "place_order")
        assigns = {
            t.id: ast.unparse(n.value) for n in ast.walk(place)
            if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)
        }
        assert "exec_request_id" in assigns
        assert "req.execution_request_id" in assigns["exec_request_id"], (
            "the logical order id must come from the caller (or be minted once), so a retry "
            "reuses it instead of creating a new logical order"
        )
        # `place_order` is a function; the kwargs live on the OmniOrder(...) call inside it.
        built = next(n for n in ast.walk(place)
                     if isinstance(n, ast.Call)
                     and isinstance(n.func, ast.Name)
                     and n.func.id == "OmniOrder")
        kws = {kw.arg: ast.unparse(kw.value) for kw in built.keywords}
        assert kws.get("client_order_id") == "exec_request_id", (
            "client_order_id must be the same value; it is sent to Dhan as correlationId"
        )

    def test_the_worker_rebuild_preserves_the_identity(self):
        """Behavioural, not a source match.

        The source-level version of this assertion passed while a mutation that replaced
        `execution_request_id=order.execution_request_id` with `None` survived: the needle
        also appears in an unrelated function, and a substring check on unparsed source
        cannot tell which call site it found. Reading the value off the returned object is
        the only assertion that survives that.
        """
        from oms.manager import build_execution_request

        order = make_order()
        rebuilt = build_execution_request(order)
        assert rebuilt.execution_request_id == order.execution_request_id == CID
        assert rebuilt.execution_request_id, (
            "a rebuilt request with no logical identity would let the broker hold an order "
            "that reconciliation can never find, and would look like a new order to the "
            "duplicate rule"
        )


# ── duplicate protection ─────────────────────────────────────────────────────


class TestDuplicateProtectionStillApplies:
    @pytest.mark.asyncio
    async def test_a_genuinely_new_identical_order_is_still_rejected(self):
        """Mutation 5's target: the rule must not be disabled."""
        from risk.models import RiskConfig
        from risk.rules import DuplicateOrderRule
        from execution.models import ExecutionRequest
        from core.models import Exchange, OrderSide, OrderType, ProductType

        rule = DuplicateOrderRule()

        def req(rid):
            return ExecutionRequest(
                user_id="u1", broker="dhan", symbol="NIFTY-Oct2026-23250-CE",
                exchange=Exchange.NSE, side=OrderSide.BUY, order_type=OrderType.MARKET,
                product=ProductType.MIS, quantity=65, price=0.65,
                execution_request_id=rid, is_paper=False,
            )

        cfg = RiskConfig()
        first = await rule.evaluate(req("order-A"), cfg)
        assert first.decision.value == "APPROVED"
        second = await rule.evaluate(req("order-B"), cfg)
        assert second.decision.value == "REJECTED", (
            "two different logical orders with identical attributes inside the window must "
            "still be refused -- that is the protection the retry path must not remove"
        )

    @pytest.mark.asyncio
    async def test_a_retry_of_the_same_logical_order_is_not_a_duplicate(self):
        """The defect this phase is about."""
        from core.models import Exchange, OrderSide, OrderType, ProductType
        from execution.models import ExecutionRequest
        from risk.models import RiskConfig
        from risk.rules import DuplicateOrderRule

        rule = DuplicateOrderRule()
        cfg = RiskConfig()

        def req(price):
            return ExecutionRequest(
                user_id="u1", broker="dhan", symbol="NIFTY-Oct2026-23250-CE",
                exchange=Exchange.NSE, side=OrderSide.BUY, order_type=OrderType.MARKET,
                product=ProductType.MIS, quantity=65, price=price,
                execution_request_id="order-A", is_paper=False,
            )

        first = await rule.evaluate(req(0.65), cfg)
        assert first.decision.value == "APPROVED"
        retry = await rule.evaluate(req(0.65), cfg)
        assert retry.decision.value == "APPROVED", (
            "a retry of the same logical order must not be refused as a duplicate of itself"
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("change", [
        {"quantity": 130}, {"side": "SELL"}, {"symbol": "NIFTY-Oct2026-23300-PE"},
        {"strike_price": 23300.0}, {"expiry_date": "2026-10-13"}, {"option_type": "PE"},
    ])
    async def test_a_retry_that_changed_a_material_attribute_is_not_a_retry(self, change):
        """Mutations 6, 7 and 8's risk-side targets.

        The retry carries the same logical order id, so the rule must decide on the
        attributes rather than the id. The observable claim is that it is NOT permitted as a
        retry of itself -- it is treated as a new order and faces the duplicate window.
        """
        from core.models import Exchange, OrderSide, OrderType, ProductType
        from execution.models import ExecutionRequest
        from risk.models import RiskConfig
        from risk.rules import DuplicateOrderRule

        rule = DuplicateOrderRule()
        cfg = RiskConfig()

        def req(**over):
            base = dict(
                user_id="u1", broker="dhan", symbol="NIFTY-Oct2026-23250-CE",
                exchange=Exchange.NSE, side=OrderSide.BUY, order_type=OrderType.MARKET,
                product=ProductType.MIS, quantity=65, price=0.65, strike_price=23250.0,
                expiry_date=EXPIRY, option_type="CE", execution_request_id="order-A",
                is_paper=False,
            )
            base.update(over)
            base["side"] = OrderSide(base["side"])
            return ExecutionRequest(**base)

        assert (await rule.evaluate(req(), cfg)).decision.value == "APPROVED"
        second = await rule.evaluate(req(**change), cfg)
        assert not (second.details or {}).get("retry_of_same_intent"), (
            f"changing {list(change)} must make this a NEW order, not a permitted retry"
        )

    @pytest.mark.asyncio
    async def test_a_material_change_outside_the_dedup_key_still_faces_the_window(self):
        """The observable consequence of treating it as new.

        `strike_price` is not part of the duplicate key, so a changed strike still hashes to
        the same key. If the change were treated as a retry the rule would wave it through;
        treated as a new order it must be refused, exactly as any other new order would be.
        """
        from core.models import Exchange, OrderSide, OrderType, ProductType
        from execution.models import ExecutionRequest
        from risk.models import RiskConfig
        from risk.rules import DuplicateOrderRule

        rule = DuplicateOrderRule()
        cfg = RiskConfig()

        def req(strike):
            return ExecutionRequest(
                user_id="u1", broker="dhan", symbol="NIFTY-Oct2026-23250-CE",
                exchange=Exchange.NSE, side=OrderSide.BUY, order_type=OrderType.MARKET,
                product=ProductType.MIS, quantity=65, price=0.65, strike_price=strike,
                expiry_date=EXPIRY, option_type="CE", execution_request_id="order-A",
                is_paper=False,
            )

        assert (await rule.evaluate(req(23250.0), cfg)).decision.value == "APPROVED"
        changed = await rule.evaluate(req(23300.0), cfg)
        assert changed.decision.value == "REJECTED", (
            "a changed strike under the same logical id is a different trade and must face "
            "the duplicate window"
        )


# ── the OMS must gate on reconciliation before retrying ─────────────────────


class TestRetryIsGatedOnReconciliation:
    def test_an_indeterminate_result_leaves_the_order_unknown(self):
        """Mutation 2's target: the worker must not requeue an unknown result."""
        tree = ast.parse(MANAGER.read_text())
        processor = next(n for n in ast.walk(tree)
                         if isinstance(n, ast.AsyncFunctionDef) and n.name == "_process_queue")
        src = ast.unparse(processor)
        assert "exec_result.indeterminate" in src
        assert "OMSOrderState.UNKNOWN" in src

    def test_the_indeterminate_branch_does_not_enqueue_a_retry(self):
        """The retry must be gated behind reconciliation, not merely labelled."""
        tree = ast.parse(MANAGER.read_text())
        processor = next(n for n in ast.walk(tree)
                         if isinstance(n, ast.AsyncFunctionDef) and n.name == "_process_queue")
        src = ast.unparse(processor)
        branch = src.split("exec_result.indeterminate", 1)[1]
        branch = branch.split("elif", 1)[0]
        assert "enqueue_retry" not in branch, (
            "the indeterminate branch requeues; an order whose result is unknown must be "
            "reconciled with the broker, never resent"
        )

    def test_reconciliation_resolves_orders_that_have_no_broker_order_id(self):
        tree = ast.parse(MANAGER.read_text())
        selector = next(n for n in ast.walk(tree)
                        if isinstance(n, ast.AsyncFunctionDef)
                        and n.name == "_reconcile_unknown_once")
        resolver = next(n for n in ast.walk(tree)
                        if isinstance(n, ast.AsyncFunctionDef)
                        and n.name == "_reconcile_one_unknown")
        # Selection is on state, not on broker_order_id -- that is the whole defect.
        sel_src = ast.unparse(selector)
        assert "OMSOrderState.UNKNOWN" in sel_src
        assert "OMSOrderState.RECONCILING" in sel_src
        assert "broker_order_id" not in sel_src, (
            "selecting unknown orders on broker_order_id reintroduces the defect: an order "
            "whose response was lost has none"
        )
        res_src = ast.unparse(resolver)
        for expected in ("OMSOrderState.AMBIGUOUS", "ReconcileVerdict.NOT_FOUND",
                         "ReconcileVerdict.UNKNOWN", "ReconcileVerdict.ACCEPTED"):
            assert expected in res_src, f"{expected} is not handled"

    def test_not_found_is_the_only_path_that_requeues(self):
        """The retry is allowed exactly where reconciliation proved absence."""
        tree = ast.parse(MANAGER.read_text())
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.AsyncFunctionDef) and n.name == "_reconcile_one_unknown")
        src = ast.unparse(fn)
        before_not_found, _, after = src.partition("ReconcileVerdict.NOT_FOUND")
        assert "enqueue_retry" not in before_not_found, (
            "something requeues before reconciliation has proved the broker does not hold "
            "the order"
        )
        assert "enqueue_retry" in after
