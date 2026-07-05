import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from core.config import settings
from core.db import async_supabase, get_supabase
from core.deps import get_current_user
from core.models import SUBSCRIPTION_TIER_FEATURES, SUBSCRIPTION_TIER_ORDER, SUBSCRIPTION_TIER_PLANS, SUBSCRIPTION_TIER_PRICES, SubscriptionStatus, SubscriptionTier, UserProfile
from core.safe_query import async_safe_execute, async_safe_single
from payments.razorpay import RazorpayClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])

razorpay = RazorpayClient()


class CreateSubscriptionRequest(BaseModel):
    plan: SubscriptionTier


class CancelSubscriptionRequest(BaseModel):
    cancel_at_cycle_end: bool = True


class PlanInfo(BaseModel):
    id: str
    name: str
    tier: str
    price: int
    features: list[str]
    most_popular: bool = False


class SubscriptionResponse(BaseModel):
    id: str
    tier: str
    status: str
    razorpay_subscription_id: str
    current_period_start: str | None = None
    current_period_end: str | None = None
    trial_end: str | None = None
    created_at: str


PLANS = [
    PlanInfo(id="monthly", name="Monthly", tier="monthly", price=15500, features=SUBSCRIPTION_TIER_FEATURES["monthly"]),
    PlanInfo(id="quarterly", name="Quarterly", tier="quarterly", price=35500, features=SUBSCRIPTION_TIER_FEATURES["quarterly"]),
    PlanInfo(id="halfyearly", name="Half Yearly", tier="halfyearly", price=69500, features=SUBSCRIPTION_TIER_FEATURES["halfyearly"], most_popular=True),
    PlanInfo(id="yearly", name="Yearly", tier="yearly", price=125000, features=SUBSCRIPTION_TIER_FEATURES["yearly"]),
]


def _tier_for_plan(plan_id: str) -> str | None:
    mapping = {
        settings.razorpay_plan_monthly: "monthly",
        settings.razorpay_plan_quarterly: "quarterly",
        settings.razorpay_plan_halfyearly: "halfyearly",
        settings.razorpay_plan_yearly: "yearly",
    }
    return mapping.get(plan_id)


def _total_count_for_tier(tier: str) -> int:
    counts = {"monthly": 1, "quarterly": 3, "halfyearly": 6, "yearly": 12}
    return counts.get(tier, 1)


def _plan_id_for_tier(tier: str) -> str:
    env_key = SUBSCRIPTION_TIER_PLANS.get(tier)
    if not env_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown plan tier: {tier}")
    plan_id = getattr(settings, env_key, "")
    if not plan_id:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Plan not configured")
    return plan_id


@router.get("/plans/")
async def list_plans():
    return {"plans": [p.model_dump() for p in PLANS]}


@router.post("/create/")
async def create_subscription(
    req: CreateSubscriptionRequest,
    current_user: UserProfile = Depends(get_current_user),
):
    existing = await async_safe_execute(
        get_supabase().table("subscriptions")
        .select("*")
        .eq("user_id", current_user.id)
        .in_("status", ("created", "authenticated", "active"))
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Active or pending subscription already exists")

    plan_id = _plan_id_for_tier(req.plan.value)
    total_count = _total_count_for_tier(req.plan.value)

    result = await razorpay.create_subscription(
        plan_id=plan_id,
        total_count=total_count,
        customer_notify=True,
        quantity=1,
        trial_period_days=1,
        notes={"user_id": current_user.id, "tier": req.plan.value},
    )

    if result.get("error"):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=result["error"].get("description", "Razorpay error"))

    sub_id = result.get("id")
    short_url = result.get("short_url", "")

    now = datetime.now(UTC).isoformat()

    await async_supabase(lambda: get_supabase().table("subscriptions").insert({
        "user_id": current_user.id,
        "razorpay_subscription_id": sub_id,
        "razorpay_plan_id": plan_id,
        "tier": req.plan.value,
        "status": SubscriptionStatus.created.value,
        "current_period_start": None,
        "current_period_end": None,
        "trial_end": None,
        "created_at": now,
        "updated_at": now,
    }).execute())

    return {
        "subscription_id": sub_id,
        "short_url": short_url,
        "tier": req.plan.value,
        "key_id": settings.razorpay_key_id,
    }


@router.get("/me/")
async def get_my_subscription(
    current_user: UserProfile = Depends(get_current_user),
):
    row = await async_safe_single(
        get_supabase().table("subscriptions")
        .select("*")
        .eq("user_id", current_user.id)
        .order("created_at", desc=True)
        .limit(1)
    )
    if not row:
        return {"subscription": None}

    return {
        "subscription": SubscriptionResponse(
            id=row["id"],
            tier=row["tier"],
            status=row["status"],
            razorpay_subscription_id=row["razorpay_subscription_id"],
            current_period_start=row.get("current_period_start"),
            current_period_end=row.get("current_period_end"),
            trial_end=row.get("trial_end"),
            created_at=row["created_at"],
        )
    }


@router.post("/cancel/")
async def cancel_subscription(
    req: CancelSubscriptionRequest,
    current_user: UserProfile = Depends(get_current_user),
):
    row = await async_safe_single(
        get_supabase().table("subscriptions")
        .select("*")
        .eq("user_id", current_user.id)
        .in_("status", ("created", "authenticated", "active"))
        .limit(1)
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active subscription found")

    razorpay_id = row["razorpay_subscription_id"]
    result = await razorpay.cancel_subscription(razorpay_id, req.cancel_at_cycle_end)

    if result.get("error"):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=result["error"].get("description", "Razorpay error"))

    new_status = SubscriptionStatus.cancelled.value if req.cancel_at_cycle_end else SubscriptionStatus.halted.value
    now = datetime.now(UTC).isoformat()

    await async_supabase(lambda: get_supabase().table("subscriptions").update({
        "status": new_status,
        "updated_at": now,
    }).eq("id", row["id"]).execute())

    return {"status": new_status, "razorpay_subscription_id": razorpay_id}
