"""
Execution engine — the heart.

dispatch_signal(signal):
    admin-assigned strategy emits a signal
      -> global kill-switch gate
      -> find live subscribers
      -> for EACH user, isolated: token check, kill/idempotency, sizing,
         risk, place order (paper/live), audit
      -> aggregate into an ExecutionBatch

Design guarantees:
  * PER-USER ISOLATION — one user's failure never touches another's. Every
    per-user path is wrapped; execute_for_user never raises.
  * SEBI TRACEABILITY — every attempt is audited with algo_id + account.
  * SAFE BY DEFAULT — no settings row => PAPER + zero size; unbuilt live broker
    => paper fallback.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from ..db import connections as vault
from . import killswitch as ks
from . import audit
from .symbols import to_broker_symbol
from .models import (
    Signal, Subscriber, OrderIntent, ExecutionResult, ExecutionBatch,
    ResultStatus, Mode,
)
from .ports import (
    SubscriberStore, ProfileStore, PositionSizer, RiskGuard, Notifier,
)
from .adapters import get_trading_adapter
from .sizing import CapitalFractionSizer
from .subscribers import SupabaseSubscriberStore, SupabaseProfileStore
from .notifier_adapter import PlatformNotifier
from .riskguard import RiskSettingsGuard
from .order_store import SupabaseOrderStore


class ExecutionEngine:
    def __init__(
        self,
        subscribers: SubscriberStore,
        profiles: ProfileStore,
        sizer: PositionSizer,
        risk: RiskGuard,
        notifier: Notifier,
        order_store,
        max_parallel: int = 25,
    ):
        self._subs = subscribers
        self._profiles = profiles
        self._sizer = sizer
        self._risk = risk
        self._notify = notifier
        self._orders = order_store
        self._sem = asyncio.Semaphore(max_parallel)

    # -- public --------------------------------------------------------------
    async def dispatch_signal(self, signal: Signal) -> ExecutionBatch:
        batch = ExecutionBatch(signal_id=signal.signal_id, strategy_id=signal.strategy_id)

        # GLOBAL kill switch — abort before any order
        if await ks.is_global_tripped():
            batch.skipped += 1
            return batch

        subscribers = await self._subs.live_subscribers(signal.strategy_id)
        batch.dispatched = len(subscribers)
        if not subscribers:
            return batch

        results = await asyncio.gather(
            *(self._guarded(sub, signal) for sub in subscribers),
            return_exceptions=True,
        )
        for sub, res in zip(subscribers, results):
            if isinstance(res, Exception):
                # last-resort safety net; execute_for_user shouldn't raise
                res = ExecutionResult(sub.user_id, sub.broker, ResultStatus.ERROR,
                                      reason=f"unhandled: {res}")
                audit.write(signal, sub.broker, sub.broker_user_id, res)
            batch.add(res)
        return batch

    # -- per-user (isolated) -------------------------------------------------
    async def _guarded(self, sub: Subscriber, signal: Signal) -> ExecutionResult:
        async with self._sem:
            try:
                return await self._execute_for_user(sub, signal)
            except Exception as e:
                res = ExecutionResult(sub.user_id, sub.broker, ResultStatus.ERROR, reason=str(e))
                audit.write(signal, sub.broker, sub.broker_user_id, res)
                return res

    async def _execute_for_user(self, sub: Subscriber, signal: Signal) -> ExecutionResult:
        uid, broker = sub.user_id, sub.broker

        # per-user kill switch
        if await ks.is_user_tripped(uid):
            return self._audit_ret(signal, sub, ResultStatus.SKIPPED_KILLED, "user_killswitch")

        # idempotency — never place the same signal twice for a user
        if not await ks.claim_once(signal.signal_id, uid):
            return self._audit_ret(signal, sub, ResultStatus.SKIPPED_DUPLICATE, "already_processed")

        # token from the encrypted vault
        tok = vault.get_decrypted_token(uid, broker)
        if not tok or tok.get("status") != "connected":
            await self._notify.notify(uid, "reconnect", f"Reconnect {broker} to trade.")
            return self._audit_ret(signal, sub, ResultStatus.SKIPPED_NO_CONN, "no_connection")

        if _expired(tok["token_expires_at"]):
            vault.mark_status(uid, broker, "needs_attention")
            await self._notify.notify(uid, "reconnect", f"{broker} login expired — reconnect for today.")
            return self._audit_ret(signal, sub, ResultStatus.SKIPPED_EXPIRED, "token_expired")

        # profile / mode / sizing
        profile = await self._profiles.profile(uid)
        qty = self._sizer.size(profile, signal)
        if qty <= 0:
            return self._audit_ret(signal, sub, ResultStatus.SIZED_ZERO, "qty_zero")

        intent = OrderIntent(
            user_id=uid,
            broker=broker,
            broker_symbol=to_broker_symbol(broker, signal),
            side=signal.side,
            qty=qty,
            order_type=signal.order_type,
            product=signal.product,
            est_price=signal.limit_price or signal.ref_price,
            limit_price=signal.limit_price,
            trigger_price=signal.trigger_price,
            target=signal.target,
            stoploss=signal.stoploss,
        )

        # risk
        allowed, reason = await self._risk.check(profile, intent)
        if not allowed:
            return self._audit_ret(signal, sub, ResultStatus.RISK_BLOCKED, reason, intent)

        # place (paper/live decided by profile.mode)
        adapter = get_trading_adapter(broker, profile.mode)
        result = await adapter.place_order(intent, tok["access_token"])
        result.qty = qty
        audit.write(signal, broker, sub.broker_user_id, result, intent)
        # bridge to your OMS: real order row (only actual attempts)
        if result.status in (ResultStatus.PLACED, ResultStatus.REJECTED):
            self._orders.record(signal, intent, result, profile.mode)

        if result.status == ResultStatus.PLACED:
            tag = "PAPER" if profile.mode == Mode.PAPER else "LIVE"
            await self._notify.notify(uid, "order", f"[{tag}] {signal.side.value} {qty} {signal.symbol}")
        return result

    # -- helper --------------------------------------------------------------
    def _audit_ret(self, signal: Signal, sub: Subscriber, status: ResultStatus,
                   reason: str | None, intent: OrderIntent | None = None) -> ExecutionResult:
        res = ExecutionResult(sub.user_id, sub.broker, status, reason=reason)
        audit.write(signal, sub.broker, sub.broker_user_id, res, intent)
        return res


def _expired(iso: str) -> bool:
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")) <= datetime.now(timezone.utc)
    except Exception:
        return True  # unpar. -> treat as expired (safe)


# ---------------------------------------------------------------------------
# Default engine wired with reference impls — runs end-to-end in PAPER mode.
# Swap AllowAllRiskGuard for your RiskGuard and LogNotifier for Resend/push.
# ---------------------------------------------------------------------------
_engine: ExecutionEngine | None = None


def get_engine() -> ExecutionEngine:
    global _engine
    if _engine is None:
        _engine = ExecutionEngine(
            subscribers=SupabaseSubscriberStore(),
            profiles=SupabaseProfileStore(),
            sizer=CapitalFractionSizer(),
            risk=RiskSettingsGuard(),      # reads your risk_settings table
            notifier=PlatformNotifier(),   # platform Resend email + Telegram push
            order_store=SupabaseOrderStore(),  # writes to your orders table
        )
    return _engine
