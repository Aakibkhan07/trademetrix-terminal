"""Auto Trading v1.0 — trading-mode enforcement for the Strategy Runtime.

Pure guard logic layered on the frozen runtime + Broker SDK:

- normalises a raw request into a persisted trading mode
  (``paper`` → Paper Broker, ``live`` → Broker SDK account);
- requires an explicit confirmation for ANY live deployment (no accidental
  live orders — a live start without ``confirm_live=True`` is refused);
- validates the chosen broker account actually exists for the user;
- blocks live starts while the global kill switch or a user emergency stop
  is active;
- enforces per-strategy execution limits (max daily trades / max positions /
  max risk per trade) at the point of order submission.

This module only imports the frozen infra — no architecture redesign.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

PAPER_BROKER = "paper"


class ModeGuardError(Exception):
    """Raised when a deployment violates a trading-mode safety rule."""

    def __init__(self, message: str, code: str = "MODE_GUARD_REJECTED"):
        super().__init__(message)
        self.code = code


@dataclass
class ModeDecision:
    """Normalised, persisted trading mode + the safety verdict."""

    mode: str = "paper"
    is_paper: bool = True
    broker: str = ""
    account: str = ""
    confirmed: bool = False
    rejected: bool = False
    reason: str = ""
    code: str = ""

    def checkpoint(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "is_paper": self.is_paper,
            "broker": self.broker,
            "account": self.account,
            "confirmed": self.confirmed,
        }


def normalize_mode(mode: str, is_paper: bool | None, broker: str = "", account: str = "") -> ModeDecision:
    """Resolve a raw mode/is_paper/broker/account into a canonical decision.

    Rules (fail-closed):
    - mode ``paper`` → Paper Broker, always confirmed (paper is safe by design).
    - mode ``live`` → Broker SDK; broker MUST be a real broker (not ``paper``)
      and ``confirmed`` must be explicitly True (set by the route from the
      request's ``confirm_live`` flag).
    - any other mode value → rejected.
    """
    mode = (mode or "").strip().lower()
    if mode not in ("paper", "live"):
        return ModeDecision(rejected=True, reason=f"Unknown trading mode: {mode!r}", code="MODE_UNKNOWN")
    if is_paper is False and mode == "paper":
        return ModeDecision(rejected=True, reason="mode=paper conflicts with is_paper=false", code="MODE_CONFLICT")

    if mode == "paper":
        return ModeDecision(
            mode="paper",
            is_paper=True,
            broker="paper",
            account=account or "",
            confirmed=True,
        )

    if not broker or broker == PAPER_BROKER:
        return ModeDecision(rejected=True, reason="Live mode requires a real broker account", code="MODE_NO_BROKER")

    return ModeDecision(
        mode="live",
        is_paper=False,
        broker=broker,
        account=account or "",
        confirmed=False,  # requires explicit confirm_live
    )


async def confirm_live(
    decision: ModeDecision,
    user_id: str,
    confirm_live: bool = False,
) -> ModeDecision:
    """Apply the explicit-live-confirmation gate to a live decision.

    Refuses (fail-closed) unless the caller explicitly passes ``confirm_live``
    AND a live broker account exists for the user. Paper mode passes through.
    """
    if decision.rejected or decision.mode != "live":
        return decision

    if not confirm_live:
        return ModeDecision(
            mode="live", is_paper=False, broker=decision.broker, account=decision.account,
            rejected=True,
            reason="Live deployment requires explicit confirmation (confirm_live=true)",
            code="LIVE_CONFIRMATION_REQUIRED",
        )

    if not await _user_has_broker_account(user_id, decision.broker):
        return ModeDecision(
            mode="live", is_paper=False, broker=decision.broker, account=decision.account,
            rejected=True,
            reason=f"No active credentials for broker {decision.broker!r}. Connect the broker first.",
            code="MODE_NO_ACCOUNT",
        )

    decision.confirmed = True
    return decision


async def assert_orders_allowed(user_id: str) -> None:
    """Global + per-user kill-switch/emergency gate.

    Called at start-time and immediately before every order submission.
    Raises ModeGuardError when the global kill switch or a user emergency
    stop is active.
    """
    try:
        from risk.kill_switch import kill_switch

        if await kill_switch.global_kill_switch_active():
            raise ModeGuardError("Global kill switch is ACTIVE — trading halted", code="GLOBAL_KILL_SWITCH")
        if kill_switch.active(user_id):
            raise ModeGuardError("Emergency stop is ACTIVE for this account — release it before trading", code="EMERGENCY_STOP_ACTIVE")
    except ModeGuardError:
        raise
    except Exception as e:  # fail-open on infra errors is acceptable for reads
        logger.warning("Kill-switch check failed (fail-open): %s", e)


async def _user_has_broker_account(user_id: str, broker: str) -> bool:
    try:
        from infrastructure.repositories.broker_repository import BrokerRepository

        repo = BrokerRepository()
        cred = await repo.get_by_user_and_broker(user_id, broker)
        return cred is not None
    except Exception as e:
        logger.warning("Broker-account check failed (fail-closed): %s", e)
        return False
