"""
Stores — ALIGNED to your real tables:
  strategy_assignments  (strategy_key, active, mirror_enabled, required_tier)
  broker_credentials    (is_active, broker, additional_params)
  profiles              (capital, subscription_tier)
  risk_settings         (is_live, max_capital, max_position_size, max_daily_loss,
                         kill_switch_enabled)

Signal.strategy_id is treated as the strategy_key. Only assignments that are
active AND mirror_enabled (your fan-out flag) are dispatched.
"""

from __future__ import annotations

from functools import lru_cache

from supabase import create_client, Client

from ..config import get_settings
from .models import Subscriber, UserTradingProfile, Mode


@lru_cache(maxsize=1)
def _sb() -> Client:
    s = get_settings()
    return create_client(s.supabase_url, s.supabase_service_key)


class SupabaseSubscriberStore:
    async def live_subscribers(self, strategy_id: str) -> list[Subscriber]:
        sb = _sb()

        # 1) users assigned to this strategy, active + mirror (fan-out) on
        subs = (
            sb.table("strategy_assignments")
            .select("user_id")
            .eq("strategy_key", strategy_id)
            .eq("active", True)
            .eq("mirror_enabled", True)
            .execute()
        )
        user_ids = [r["user_id"] for r in (subs.data or [])]
        if not user_ids:
            return []

        # 2) their active broker credential(s). Expiry is re-checked in the
        #    engine so expired users still get a reconnect nudge.
        creds = (
            sb.table("broker_credentials")
            .select("user_id, broker, additional_params")
            .in_("user_id", user_ids)
            .eq("is_active", True)
            .execute()
        )
        out: list[Subscriber] = []
        for r in (creds.data or []):
            extra = r.get("additional_params") or {}
            out.append(
                Subscriber(
                    user_id=r["user_id"],
                    broker=r["broker"],
                    broker_user_id=extra.get("broker_user_id"),
                )
            )
        return out


class SupabaseProfileStore:
    async def profile(self, user_id: str) -> UserTradingProfile:
        sb = _sb()

        prof = (
            sb.table("profiles")
            .select("capital, subscription_tier")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
        pr = prof.data[0] if prof.data else {}

        risk = (
            sb.table("risk_settings")
            .select("is_live, max_capital, max_position_size, max_daily_loss, kill_switch_enabled")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        rk = risk.data[0] if risk.data else {}

        capital = float(pr.get("capital") or rk.get("max_capital") or 0)
        # LIVE only when risk_settings says so — default PAPER (safe)
        mode = Mode.LIVE if rk.get("is_live") else Mode.PAPER

        return UserTradingProfile(
            user_id=user_id,
            mode=mode,
            capital=capital,
            risk_fraction=0.01,          # tune, or derive from max_position_size
            max_lots=10,
            tier=pr.get("subscription_tier"),
        )


class LogNotifier:
    async def notify(self, user_id: str, kind: str, message: str) -> None:
        print(f"[notify:{kind}] user={user_id} :: {message}")
