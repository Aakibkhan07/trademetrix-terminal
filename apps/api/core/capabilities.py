from datetime import UTC, datetime

from pydantic import BaseModel

from core.models import UserProfile


class Capabilities(BaseModel):
    tier: str = "free"
    max_active_strategies: int = 1
    trailing_sl_allowed: bool = False
    reentry_squareoff_allowed: bool = False
    builder_allowed: bool = False
    custom_strategy_dev_allowed: bool = False
    backtest_allowed: bool = False
    backtest_years: int = 0
    daily_loss_floor: float = 2000.0
    live_trading_allowed: bool = False
    paper_crypto_forex_allowed: bool = False


FREE = Capabilities()

MONTHLY = Capabilities(
    tier="monthly",
    max_active_strategies=2,
    backtest_allowed=True,
    backtest_years=1,
    live_trading_allowed=True,
    paper_crypto_forex_allowed=True,
)

QUARTERLY = Capabilities(
    tier="quarterly",
    max_active_strategies=4,
    trailing_sl_allowed=True,
    backtest_allowed=True,
    backtest_years=2,
    daily_loss_floor=3000.0,
    live_trading_allowed=True,
    paper_crypto_forex_allowed=True,
)

HALFYEARLY = Capabilities(
    tier="halfyearly",
    max_active_strategies=8,
    trailing_sl_allowed=True,
    reentry_squareoff_allowed=True,
    builder_allowed=True,
    backtest_allowed=True,
    backtest_years=5,
    daily_loss_floor=5000.0,
    live_trading_allowed=True,
    paper_crypto_forex_allowed=True,
)

YEARLY = Capabilities(
    tier="yearly",
    max_active_strategies=15,
    trailing_sl_allowed=True,
    reentry_squareoff_allowed=True,
    builder_allowed=True,
    custom_strategy_dev_allowed=True,
    backtest_allowed=True,
    backtest_years=5,
    daily_loss_floor=10000.0,
    live_trading_allowed=True,
    paper_crypto_forex_allowed=True,
)

SUPER_ADMIN = Capabilities(
    tier="super_admin",
    max_active_strategies=999,
    trailing_sl_allowed=True,
    reentry_squareoff_allowed=True,
    builder_allowed=True,
    custom_strategy_dev_allowed=True,
    backtest_allowed=True,
    backtest_years=5,
    daily_loss_floor=100000.0,
    live_trading_allowed=True,
    paper_crypto_forex_allowed=True,
)

CAP_MAP: dict[str, Capabilities] = {
    "monthly": MONTHLY,
    "quarterly": QUARTERLY,
    "halfyearly": HALFYEARLY,
    "yearly": YEARLY,
}


async def _fetch_subscription_row(user_id: str) -> dict | None:
    """Fetch the most recent subscription row for a user.

    Returns the row dict, or None if no subscription exists.
    """
    from core.db import async_supabase, get_supabase
    from core.safe_query import async_safe_execute
    supabase = get_supabase()
    try:
        rows = await async_safe_execute(
            supabase.table("subscriptions")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(1)
        )
        return rows[0] if rows else None
    except Exception:
        return None


async def _resolve_subscription_tier(user_id: str) -> str | None:
    """Resolve active subscription tier with safety-net expiry check.

    Returns the tier string (e.g. 'monthly') or None if no valid subscription
    exists.  The safety net catches cases where current_period_end has passed
    but no webhook arrived to mark the subscription expired.
    """
    row = await _fetch_subscription_row(user_id)
    if not row:
        return None

    status = row.get("status", "")
    period_end = row.get("current_period_end")

    if status in ("active", "cancelled") and period_end:
        try:
            end = datetime.fromisoformat(period_end.replace("Z", "+00:00"))
            if end < datetime.now(UTC):
                logger = __import__("logging").getLogger(__name__)
                logger.info(
                    "Subscription %s current_period_end %s is in the past — expired (safety net)",
                    row.get("razorpay_subscription_id", ""), period_end,
                )
                return None
        except (ValueError, TypeError):
            pass

    if status == "active":
        return row.get("tier")

    if status == "cancelled":
        return row.get("tier")

    return None


async def get_active_subscription(user_id: str) -> str | None:
    return await _resolve_subscription_tier(user_id)


async def resolve_capabilities(user: UserProfile) -> Capabilities:
    if user.role == "super_admin":
        return SUPER_ADMIN
    tier = await get_active_subscription(user.id)
    if tier and tier in CAP_MAP:
        return CAP_MAP[tier]
    return FREE


async def resolve_capabilities_by_id(user_id: str) -> Capabilities:
    from core.db import async_supabase, get_supabase
    from core.safe_query import async_safe_single
    supabase = get_supabase()
    profile = await async_safe_single(
        supabase.table("profiles").select("id, role").eq("id", user_id)
    )
    if profile and profile.get("role") == "super_admin":
        return SUPER_ADMIN
    tier = await get_active_subscription(user_id)
    if tier and tier in CAP_MAP:
        return CAP_MAP[tier]
    return FREE
