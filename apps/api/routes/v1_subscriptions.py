import logging

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from application.services.subscription_service import SubscriptionService
from core.deps import get_current_user
from core.models import SUBSCRIPTION_TIER_FEATURES, SubscriptionTier, UserProfile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])

svc = SubscriptionService()


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


@router.post("/webhook/")
async def handle_webhook(request: Request):
    body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")
    return await svc.handle_webhook(body, signature)


@router.get("/plans/")
async def list_plans():
    return await svc.list_plans(PLANS)


@router.post("/create/")
async def create_subscription(
    req: CreateSubscriptionRequest,
    current_user: UserProfile = Depends(get_current_user),
):
    return await svc.create_subscription(current_user.id, req.plan.value)


@router.get("/me/")
async def get_my_subscription(
    current_user: UserProfile = Depends(get_current_user),
):
    data = await svc.get_my_subscription(current_user.id)
    sub = data.get("subscription")
    if sub is None:
        return {"subscription": None}
    return {
        "subscription": SubscriptionResponse(
            id=sub["id"],
            tier=sub["tier"],
            status=sub["status"],
            razorpay_subscription_id=sub["razorpay_subscription_id"],
            current_period_start=sub.get("current_period_start"),
            current_period_end=sub.get("current_period_end"),
            trial_end=sub.get("trial_end"),
            created_at=sub["created_at"],
        )
    }


@router.post("/cancel/")
async def cancel_subscription(
    req: CancelSubscriptionRequest,
    current_user: UserProfile = Depends(get_current_user),
):
    return await svc.cancel_subscription(current_user.id, req.cancel_at_cycle_end)
