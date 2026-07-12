import hashlib
import hmac
import json
import logging
from datetime import UTC, datetime
from typing import Any, cast

from fastapi import HTTPException, status

from core.config import settings
from core.db import async_supabase, get_supabase
from core.models import SUBSCRIPTION_TIER_PLANS, SubscriptionStatus
from core.safe_query import async_safe_execute, async_safe_single
from payments.razorpay import RazorpayClient

logger = logging.getLogger(__name__)


class SubscriptionService:
    def __init__(self) -> None:
        self.razorpay = RazorpayClient()

    @staticmethod
    def tier_for_plan(plan_id: str) -> str | None:
        mapping = {
            settings.razorpay_plan_monthly: "monthly",
            settings.razorpay_plan_quarterly: "quarterly",
            settings.razorpay_plan_halfyearly: "halfyearly",
            settings.razorpay_plan_yearly: "yearly",
        }
        return mapping.get(plan_id)

    @staticmethod
    def total_count_for_tier(tier: str) -> int:
        return {"monthly": 1, "quarterly": 3, "halfyearly": 6, "yearly": 12}.get(tier, 1)

    @staticmethod
    def plan_id_for_tier(tier: str) -> str:
        env_key = SUBSCRIPTION_TIER_PLANS.get(tier)
        if not env_key:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown plan tier: {tier}")
        plan_id = getattr(settings, env_key, "")
        if not plan_id:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Plan not configured")
        return plan_id

    @staticmethod
    def verify_webhook_signature(body: bytes, signature: str) -> bool:
        if not settings.razorpay_webhook_secret:
            logger.warning("RAZORPAY_WEBHOOK_SECRET not set — skipping signature verification")
            return True
        expected = hmac.new(settings.razorpay_webhook_secret.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(f"sha256={expected}", signature)

    @staticmethod
    async def is_event_processed(event_id: str) -> bool:
        row = await async_safe_single(
            get_supabase().table("processed_webhooks")
            .select("id")
            .eq("event_id", event_id)
            .limit(1)
        )
        return row is not None

    @staticmethod
    async def mark_event_processed(event_id: str, event_type: str) -> None:
        now = datetime.now(UTC).isoformat()
        try:
            await async_supabase(lambda: get_supabase().table("processed_webhooks").insert({
                "event_id": event_id,
                "event_type": event_type,
                "processed_at": now,
            }).execute())
        except Exception as e:
            logger.warning("Failed to record processed event %s: %s", event_id, e)

    @staticmethod
    async def update_subscription_row(razorpay_sub_id: str, updates: dict) -> None:
        updates["updated_at"] = datetime.now(UTC).isoformat()
        try:
            await async_supabase(lambda: get_supabase().table("subscriptions").update(updates).eq("razorpay_subscription_id", razorpay_sub_id).execute())
        except Exception as e:
            logger.error("Failed to update subscription %s: %s", razorpay_sub_id, e)
            raise

    @staticmethod
    async def insert_subscription_row(data: dict) -> dict | None:
        now = datetime.now(UTC).isoformat()
        data.setdefault("created_at", now)
        data.setdefault("updated_at", now)
        try:
            result = await async_supabase(lambda: get_supabase().table("subscriptions").insert(data).execute())
            return cast(dict[str, Any], result.data[0]) if result and result.data else None
        except Exception as e:
            logger.error("Failed to insert subscription: %s", e)
            raise

    async def handle_webhook(self, body_bytes: bytes, signature: str) -> dict:
        if not self.verify_webhook_signature(body_bytes, signature):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook signature")

        try:
            payload = json.loads(body_bytes)
        except json.JSONDecodeError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON body")

        event = payload.get("event", "")
        event_id = payload.get("id", "")

        if not event or not event_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing event or id")

        if await self.is_event_processed(event_id):
            logger.info("Webhook event %s (%s) already processed — skipping", event_id, event)
            return {"status": "already_processed"}

        sub_entity = payload.get("payload", {}).get("subscription", {}).get("entity", {})
        if not sub_entity:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing subscription entity")

        razorpay_sub_id = sub_entity.get("id", "")
        plan_id = sub_entity.get("plan_id", "")

        tier = self.tier_for_plan(plan_id)
        if not tier:
            logger.warning("Unknown plan_id %s in webhook event %s", plan_id, event_id)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown plan_id: {plan_id}")

        current_start = sub_entity.get("current_start")
        current_end = sub_entity.get("current_end")

        def _ts(val: Any) -> str | None:
            if val:
                return datetime.fromtimestamp(int(val), tz=UTC).isoformat()
            return None

        period_start = _ts(current_start)
        period_end = _ts(current_end)

        if event == "subscription.activated":
            if not current_end:
                period_end = _ts(sub_entity.get("end_at"))
            await self.update_subscription_row(razorpay_sub_id, {
                "status": SubscriptionStatus.active.value,
                "tier": tier,
                "current_period_start": period_start,
                "current_period_end": period_end,
            })
            logger.info("Subscription %s activated — tier %s (period: %s → %s)", razorpay_sub_id, tier, period_start, period_end)

        elif event == "subscription.authenticated":
            if not current_end:
                period_end = _ts(sub_entity.get("end_at"))
            await self.update_subscription_row(razorpay_sub_id, {
                "status": SubscriptionStatus.active.value,
                "tier": tier,
                "current_period_start": period_start,
                "current_period_end": period_end,
            })
            logger.info("Subscription %s authenticated — activated as %s", razorpay_sub_id, tier)

        elif event == "subscription.charged":
            if current_end:
                await self.update_subscription_row(razorpay_sub_id, {
                    "current_period_end": period_end,
                    "current_period_start": period_start,
                })
                logger.info("Subscription %s charged — period extended to %s", razorpay_sub_id, period_end)

        elif event in ("subscription.pending", "subscription.halted"):
            new_status = SubscriptionStatus.halted.value
            await self.update_subscription_row(razorpay_sub_id, {
                "status": new_status,
            })
            logger.warning("Subscription %s halted — payment issue", razorpay_sub_id)

        elif event == "subscription.cancelled":
            await self.update_subscription_row(razorpay_sub_id, {
                "status": SubscriptionStatus.cancelled.value,
                "current_period_end": period_end,
            })
            logger.info("Subscription %s cancelled — access until %s", razorpay_sub_id, period_end)

        elif event == "subscription.completed":
            await self.update_subscription_row(razorpay_sub_id, {
                "status": SubscriptionStatus.completed.value,
                "current_period_end": period_end,
            })
            logger.info("Subscription %s completed — downgrading to free", razorpay_sub_id)

        else:
            logger.info("Unhandled webhook event type: %s", event)

        await self.mark_event_processed(event_id, event)

        return {
            "status": "processed",
            "event": event,
            "subscription_id": razorpay_sub_id,
            "tier": tier,
        }

    async def list_plans(self, plans_list: list) -> dict:
        return {"plans": [p.model_dump() for p in plans_list]}

    async def create_subscription(self, user_id: str, tier: str) -> dict:
        existing = await async_safe_execute(
            get_supabase().table("subscriptions")
            .select("*")
            .eq("user_id", user_id)
            .in_("status", ("created", "authenticated", "active"))
        )
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Active or pending subscription already exists")

        plan_id = self.plan_id_for_tier(tier)
        total_count = self.total_count_for_tier(tier)

        result = await self.razorpay.create_subscription(
            plan_id=plan_id,
            total_count=total_count,
            customer_notify=True,
            quantity=1,
            trial_period_days=1,
            notes={"user_id": user_id, "tier": tier},
        )

        if result.get("error"):
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=result["error"].get("description", "Razorpay error"))

        sub_id = result.get("id")
        short_url = result.get("short_url", "")

        now = datetime.now(UTC).isoformat()

        await async_supabase(lambda: get_supabase().table("subscriptions").insert({
            "user_id": user_id,
            "razorpay_subscription_id": sub_id,
            "razorpay_plan_id": plan_id,
            "tier": tier,
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
            "tier": tier,
            "key_id": settings.razorpay_key_id,
        }

    async def get_my_subscription(self, user_id: str) -> dict:
        row = await async_safe_single(
            get_supabase().table("subscriptions")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(1)
        )
        if not row:
            return {"subscription": None}
        return {
            "subscription": {
                "id": row["id"],
                "tier": row["tier"],
                "status": row["status"],
                "razorpay_subscription_id": row["razorpay_subscription_id"],
                "current_period_start": row.get("current_period_start"),
                "current_period_end": row.get("current_period_end"),
                "trial_end": row.get("trial_end"),
                "created_at": row["created_at"],
            }
        }

    async def cancel_subscription(self, user_id: str, cancel_at_cycle_end: bool) -> dict:
        row = await async_safe_single(
            get_supabase().table("subscriptions")
            .select("*")
            .eq("user_id", user_id)
            .in_("status", ("created", "authenticated", "active"))
            .limit(1)
        )
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active subscription found")

        razorpay_id = row["razorpay_subscription_id"]
        result = await self.razorpay.cancel_subscription(razorpay_id, cancel_at_cycle_end)

        if result.get("error"):
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=result["error"].get("description", "Razorpay error"))

        new_status = SubscriptionStatus.cancelled.value if cancel_at_cycle_end else SubscriptionStatus.halted.value
        now = datetime.now(UTC).isoformat()

        await async_supabase(lambda: get_supabase().table("subscriptions").update({
            "status": new_status,
            "updated_at": now,
        }).eq("id", row["id"]).execute())

        return {"status": new_status, "razorpay_subscription_id": razorpay_id}
