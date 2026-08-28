"""
RiskGuard — ALIGNED to your existing `risk_settings` table.

RiskSettingsGuard reads:
  risk_settings(user_id, max_capital, max_position_size, max_open_positions,
                max_daily_loss, max_drawdown_pct, kill_switch_enabled, is_live)

Enforced now: kill_switch_enabled, max_position_size, max_capital (notional).
TODO hooks (need your live P&L / positions source): max_daily_loss,
max_drawdown_pct, max_open_positions — wire to your pnl store and enable.

AllowAllRiskGuard is kept only for PAPER smoke tests.
"""

from __future__ import annotations

from functools import lru_cache

from supabase import create_client, Client

from ..config import get_settings
from .models import UserTradingProfile, OrderIntent


@lru_cache(maxsize=1)
def _sb() -> Client:
    s = get_settings()
    return create_client(s.supabase_url, s.supabase_service_key)


class AllowAllRiskGuard:
    async def check(self, profile: UserTradingProfile, intent: OrderIntent) -> tuple[bool, str | None]:
        return True, None


class RiskSettingsGuard:
    async def check(self, profile: UserTradingProfile, intent: OrderIntent) -> tuple[bool, str | None]:
        res = (
            _sb()
            .table("risk_settings")
            .select("max_capital, max_position_size, max_daily_loss, max_drawdown_pct, "
                    "max_open_positions, kill_switch_enabled")
            .eq("user_id", profile.user_id)
            .limit(1)
            .execute()
        )
        rk = res.data[0] if res.data else {}

        # hard stop
        if rk.get("kill_switch_enabled"):
            return False, "kill_switch_enabled"

        notional = intent.qty * (intent.est_price or 0)

        mps = rk.get("max_position_size")
        if mps and notional > float(mps):
            return False, "max_position_size_exceeded"

        mc = rk.get("max_capital")
        if mc and notional > float(mc):
            return False, "max_capital_exceeded"

        # --- TODO: enable once wired to your live P&L / positions ------------
        # today_pnl = await pnl_store.today(profile.user_id)
        # if rk.get("max_daily_loss") and today_pnl <= -float(rk["max_daily_loss"]):
        #     return False, "max_daily_loss_hit"
        # open_pos = await positions.count(profile.user_id)
        # if rk.get("max_open_positions") and open_pos >= int(rk["max_open_positions"]):
        #     return False, "max_open_positions"

        return True, None
