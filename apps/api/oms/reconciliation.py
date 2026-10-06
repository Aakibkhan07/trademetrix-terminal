"""Deciding what an order's real state is when the broker never answered.

The problem this exists for: `POST /v2/orders` can be accepted by the broker and still
leave us with no `orderId`, because the response was lost. At that moment the order is not
rejected and it is not accepted -- nobody knows. The previous code had no way to say that,
so it said "rejected", retried, and produced duplicate orders.

Matching uses only identifiers Dhan actually supports. The strongest is the correlation id:

  * ``GET /v2/orders/external/{correlation_id}`` -- Dhan's own official client exposes this
    as ``Order.get_order_by_correlationID``, and this repo already sends
    ``correlationId: <client order id>`` on every order. Verified live: a correlation id that
    does not exist answers ``404`` with ``errorType: Order_Error``, and the bare collection
    answers ``200 []``.

  * Failing that, the day order list scanned for an exact attribute match inside a time
    window: securityId, exchangeSegment, transactionType, quantity, orderType, productType,
    expiry, strike, option type. This is genuinely weaker -- two identical orders can look
    alike -- so more than one match is reported as AMBIGUOUS and never resolved by picking
    the first. A weaker identifier is not a licence to guess.

Nothing here decides whether to retry. It reports a verdict; `retry_eligible` is true only
for a definitive NOT_FOUND after the configured number of observations.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum

logger = logging.getLogger(__name__)


class ReconcileVerdict(StrEnum):
    """What reconciliation could establish about an order the broker did not answer for."""

    #: The broker holds this order. `match` carries its broker order id.
    ACCEPTED = "ACCEPTED"
    #: The broker explicitly refused it. Terminal.
    REJECTED = "REJECTED"
    #: The broker definitively does not hold it, after the full observation window.
    NOT_FOUND = "NOT_FOUND"
    #: More than one broker order matches, or matching is impossible to narrow. Never
    #: auto-resolved -- a wrong choice here creates or cancels a real position.
    AMBIGUOUS = "AMBIGUOUS"
    #: Not answerable yet. Never retried on this verdict.
    UNKNOWN = "UNKNOWN"


#: Dhan order statuses that mean the broker refused or finished with the order. Taken from
#: the statuses this repo's own `DhanAdapter._map_status` already handles.
TERMINAL_STATUSES = frozenset({"REJECTED", "CANCELLED", "EXPIRED"})

#: A single missing observation is not proof. The broker may simply not have made a
#: just-created order visible yet, so NOT_FOUND requires this many consecutive absences and
#: at least `NOT_FOUND_GRACE` elapsed since the request was sent.
DEFAULT_NOT_FOUND_OBSERVATIONS = 3
DEFAULT_NOT_FOUND_GRACE = timedelta(seconds=45)

#: Attribute identity used for the weaker order-list scan. `securityId` and
#: `exchangeSegment` come from resolved contract metadata, so two contracts can never
#: collide on them.
IDENTITY_ATTRIBUTES = (
    "securityId", "exchangeSegment", "transactionType", "quantity",
    "orderType", "productType", "drvExpiryDate", "drvStrikePrice", "drvOptionType",
)


@dataclass(frozen=True)
class BrokerOrderMatch:
    broker_order_id: str
    correlation_id: str = ""
    status: str = ""
    #: How this candidate was identified: "correlation_id" or "attributes".
    matched_by: str = ""
    attributes: dict = field(default_factory=dict)

    @property
    def is_terminal(self) -> bool:
        return (self.status or "").upper() in TERMINAL_STATUSES


@dataclass(frozen=True)
class ReconcileOutcome:
    verdict: ReconcileVerdict
    reason: str
    match: BrokerOrderMatch | None = None
    candidates: tuple[BrokerOrderMatch, ...] = ()
    #: True only for a definitive NOT_FOUND. Never true for UNKNOWN or AMBIGUOUS.
    retry_eligible: bool = False

    @property
    def resolved(self) -> bool:
        return self.verdict in (ReconcileVerdict.ACCEPTED, ReconcileVerdict.REJECTED,
                                ReconcileVerdict.NOT_FOUND)


def _norm(value: object) -> str:
    """Normalise a broker field for comparison.

    Floats compare badly as strings -- `65.0` vs `65`, `23250` vs `23250.0` -- and an
    attribute match that misses because of formatting is a false NOT_FOUND.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, float):
        return f"{value:g}"
    return str(value).strip()


def attributes_match(broker_order: dict, expected: dict) -> bool:
    """True when every identity attribute the local order knows about agrees.

    Attributes the local side does not know are skipped rather than treated as a mismatch,
    so an order stored before the derivative identity was persisted can still be matched on
    the fields it does have.
    """
    for key in IDENTITY_ATTRIBUTES:
        if key not in expected or expected[key] in (None, ""):
            continue
        if _norm(broker_order.get(key)) != _norm(expected[key]):
            return False
    return True


class OrderReconciler:
    """Asks the broker what it actually holds. Never infers.

    ``lookup_by_correlation`` and ``list_orders`` are injected so the whole decision table
    is testable without a broker, and so a broker that cannot answer produces UNKNOWN
    rather than a guess.
    """

    def __init__(
        self,
        *,
        lookup_by_correlation=None,
        list_orders=None,
        not_found_observations: int = DEFAULT_NOT_FOUND_OBSERVATIONS,
        grace: timedelta = DEFAULT_NOT_FOUND_GRACE,
    ) -> None:
        self._lookup_by_correlation = lookup_by_correlation
        self._list_orders = list_orders
        self.not_found_observations = max(1, not_found_observations)
        self.grace = grace

    # ── strategy 1: the correlation id ───────────────────────────────────────────
    async def _by_correlation(self, correlation_id: str) -> tuple[list[BrokerOrderMatch], str]:
        if not correlation_id or self._lookup_by_correlation is None:
            return [], "correlation lookup unavailable"
        try:
            raw = await self._lookup_by_correlation(correlation_id)
        except Exception as exc:  # noqa: BLE001 - a broker error is UNKNOWN, never NOT_FOUND
            return [], f"correlation lookup failed: {type(exc).__name__}: {exc}"
        if raw in (None, "", [], {}):
            return [], "correlation id not found"
        items = raw if isinstance(raw, list) else [raw]
        return [
            BrokerOrderMatch(
                broker_order_id=str(item.get("orderId", "")),
                correlation_id=str(item.get("correlationId", "") or correlation_id),
                status=str(item.get("orderStatus", "")),
                matched_by="correlation_id",
                attributes=dict(item),
            )
            for item in items
            if isinstance(item, dict) and item.get("orderId")
        ], ""

    # ── strategy 2: attribute identity inside a time window ──────────────────────
    async def _by_attributes(self, expected: dict, since: datetime | None) -> tuple[
            list[BrokerOrderMatch], str]:
        if self._list_orders is None:
            return [], "order list unavailable"
        try:
            orders = await self._list_orders()
        except Exception as exc:  # noqa: BLE001
            return [], f"order list failed: {type(exc).__name__}: {exc}"
        if not isinstance(orders, list):
            return [], "order list returned an unexpected shape"
        found = []
        for item in orders:
            if not isinstance(item, dict) or not item.get("orderId"):
                continue
            if since is not None and not self._within_window(item, since):
                continue
            if attributes_match(item, expected):
                found.append(BrokerOrderMatch(
                    broker_order_id=str(item.get("orderId")),
                    correlation_id=str(item.get("correlationId", "") or ""),
                    status=str(item.get("orderStatus", "")),
                    matched_by="attributes",
                    attributes=dict(item),
                ))
        return found, ""

    def _within_window(self, item: dict, since: datetime) -> bool:
        """Only consider orders created at or after ours, so a same-shape earlier order
        cannot be mistaken for this one."""
        raw = item.get("exchangeTime") or item.get("createTime") or item.get("orderTime")
        if not raw:
            # Undatable candidates are KEPT, not dropped.
            #
            # Dropping them is the dangerous direction: a real match that gets filtered out
            # becomes "the broker has nothing", which becomes NOT_FOUND, which authorises a
            # retry of an order that may already be live. Keeping an undatable candidate can
            # only produce AMBIGUOUS, which stops and asks a human. Fail toward ambiguity,
            # never toward a resend.
            return True
        stamp: datetime | None = None
        if isinstance(raw, (int, float)):
            # Dhan sends epoch seconds.
            try:
                stamp = datetime.fromtimestamp(float(raw), tz=UTC)
            except (OverflowError, OSError, ValueError):
                stamp = None
        elif isinstance(raw, str):
            try:
                stamp = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                stamp = None
        if stamp is None:
            return True
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=UTC)
        return stamp >= since - timedelta(seconds=5)

    @staticmethod
    def _is_failure(why: str) -> bool:
        """Whether a strategy failed, as opposed to reporting that it found nothing.

        "unavailable" and "failed" mean the broker never gave an answer, so nothing may be
        concluded from them. "not found" means the broker answered and held no such order --
        which, and only which, can accumulate towards NOT_FOUND.
        """
        lowered = (why or "").lower()
        return ("unavailable" in lowered or "failed" in lowered
                or "unexpected shape" in lowered)

    # ── the decision ─────────────────────────────────────────────────────────────
    async def reconcile(
        self,
        *,
        correlation_id: str,
        expected_attributes: dict,
        sent_at: datetime | None,
        broker_order_id: str = "",
        not_found_observations: int = 0,
    ) -> ReconcileOutcome:
        # A broker order id means the broker already told us. Nothing to infer.
        if broker_order_id:
            return ReconcileOutcome(
                verdict=ReconcileVerdict.ACCEPTED,
                reason="the broker already returned an order id",
                match=BrokerOrderMatch(broker_order_id=broker_order_id,
                                       correlation_id=correlation_id),
            )

        matches, why = await self._by_correlation(correlation_id)
        # A broker that could not answer is not evidence of absence. Concluding NOT_FOUND
        # from a failed lookup would authorise a retry of an order that may already be live
        # at the broker -- which is the duplicate-order defect itself. The distinction the
        # first version of this lost: `_by_correlation` returned `([], "lookup failed")` and
        # `([], "not found")` indistinguishably, so both became NOT_FOUND.
        if self._is_failure(why):
            return ReconcileOutcome(
                verdict=ReconcileVerdict.UNKNOWN, reason=why,
            )
        if len(matches) == 1:
            match = matches[0]
            verdict = (ReconcileVerdict.REJECTED if match.is_terminal
                       else ReconcileVerdict.ACCEPTED)
            return ReconcileOutcome(
                verdict=verdict, match=match,
                candidates=tuple(matches),
                reason=(f"correlation id matched a broker order with status "
                        f"{match.status!r}"),
            )
        if len(matches) > 1:
            return ReconcileOutcome(
                verdict=ReconcileVerdict.AMBIGUOUS, candidates=tuple(matches),
                reason=f"correlation id matched {len(matches)} broker orders",
            )

        candidates, attr_why = await self._by_attributes(expected_attributes, sent_at)
        if self._is_failure(attr_why):
            return ReconcileOutcome(
                verdict=ReconcileVerdict.UNKNOWN, reason=attr_why,
            )
        if len(candidates) == 1:
            match = candidates[0]
            verdict = (ReconcileVerdict.REJECTED if match.is_terminal
                       else ReconcileVerdict.ACCEPTED)
            return ReconcileOutcome(
                verdict=verdict, match=match, candidates=tuple(candidates),
                reason=("matched exactly one broker order on contract identity "
                        f"(status {match.status!r})"),
            )
        if len(candidates) > 1:
            return ReconcileOutcome(
                verdict=ReconcileVerdict.AMBIGUOUS, candidates=tuple(candidates),
                reason=(f"{len(candidates)} broker orders match this contract identity; "
                        f"refusing to choose one"),
            )

        # Nothing found. That is not yet proof of absence.
        observed = not_found_observations + 1
        grace_left = True
        if sent_at is not None:
            grace_left = datetime.now(UTC) - sent_at < self.grace
        if observed >= self.not_found_observations and not grace_left:
            return ReconcileOutcome(
                verdict=ReconcileVerdict.NOT_FOUND,
                reason=(f"the broker reported no matching order after {observed} "
                        f"observation(s) and the {int(self.grace.total_seconds())}s "
                        f"grace window"),
                retry_eligible=True,
            )
        return ReconcileOutcome(
            verdict=ReconcileVerdict.UNKNOWN,
            reason=(f"no broker order found yet (observation {observed}, "
                    f"grace {'active' if grace_left else 'elapsed'}): {why or attr_why}"),
        )
