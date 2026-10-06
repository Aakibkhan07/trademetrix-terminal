"""An order request whose outcome at the broker is unknown.

This exists because "the broker did not answer" and "the broker rejected the order" are
different facts, and the code was collapsing them.

The chain that made the collapse real, all of it verified in this repository:

  * `BrokerExecutionAdapter.place_order` deliberately **raised** on transport errors
    (`asyncio.TimeoutError`, `httpx.TimeoutException`, `httpx.ConnectError`,
    `httpx.RemoteProtocolError`, `httpx.ReadTimeout`) precisely because a lost response
    says nothing about whether the broker accepted the order. It returned a failed
    `OrderResult` only for errors where a response *was* received.

  * `retry_with_backoff` then treated those very exceptions as transient and **re-issued
    the POST**, up to `MAX_RETRIES = 3`. So one logical order could reach the broker four
    times, and `DuplicateOrderRule` cannot help: it runs once, before the first send. A
    MARKET order for one lot could fill more than once. That is a duplicate-order hazard
    created by the retry that was supposed to help.

  * `ExecutionManager._execute_with_retry` caught the resulting exception and returned a
    plain `OrderResult(success=False)`, destroying the only signal that distinguished
    "indeterminate" from "rejected". The OMS then read that as a definitive rejection and
    retried, which hit `DuplicateOrderRule` and produced a permanent
    `RISK_REJECTED` for an order whose real state was still unknown.

So an indeterminate send raises this instead of a bare transport error. It is not in
`TRANSIENT_EXCEPTIONS` and its code is not in `TRANSIENT_ERRORS`, so `retry_with_backoff`
re-raises it on the first attempt without sending anything a second time. Nothing in this
module decides whether the order exists -- that is reconciliation's job, and it answers by
asking the broker, not by guessing.
"""
from __future__ import annotations

#: Recorded on `OrderResult.error_code`. Deliberately absent from
#: `retry.TRANSIENT_ERRORS` so `is_transient()` returns False and the retry wrapper
#: re-raises instead of re-sending.
ORDER_RESULT_UNKNOWN = "ORDER_RESULT_UNKNOWN"


class IndeterminateOrderError(Exception):
    """The broker never told us whether the order was accepted.

    ``reason`` records what was observed (a read timeout, a dropped connection) and is for
    humans. It is never used to decide whether to retry: only reconciliation may.
    """

    code = ORDER_RESULT_UNKNOWN

    def __init__(self, reason: str = "", *, broker: str = "") -> None:
        self.reason = reason or "no response from the broker"
        self.broker = broker
        super().__init__(f"{broker or 'broker'}: order result unknown ({self.reason})" if broker
                         else f"order result unknown ({self.reason})")


def is_indeterminate(exc: BaseException) -> bool:
    return isinstance(exc, IndeterminateOrderError)
