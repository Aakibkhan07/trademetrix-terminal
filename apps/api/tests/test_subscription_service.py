from typing import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from application.services.subscription_service import SubscriptionService


@pytest.fixture
def mock_razorpay() -> Generator[MagicMock, None, None]:
    with patch("application.services.subscription_service.RazorpayClient") as m:
        instance = m.return_value
        instance.create_subscription = AsyncMock()
        instance.cancel_subscription = AsyncMock()
        yield instance


@pytest.fixture
def svc(mock_razorpay) -> SubscriptionService:
    return SubscriptionService()


@pytest.fixture
def mock_db() -> Generator[dict, None, None]:
    with (
        patch("application.services.subscription_service.get_supabase") as mock_get,
        patch("application.services.subscription_service.async_supabase") as mock_async,
        patch("application.services.subscription_service.async_safe_single") as mock_single,
        patch("application.services.subscription_service.async_safe_execute") as mock_execute,
    ):
        mock_table = MagicMock()
        mock_get.return_value.table.return_value = mock_table
        mock_async.return_value = MagicMock(data=[{"id": "mock-id"}])
        yield {
            "get_supabase": mock_get,
            "async_supabase": mock_async,
            "async_safe_single": mock_single,
            "async_safe_execute": mock_execute,
            "table": mock_table,
        }


@pytest.fixture
def mock_settings() -> Generator[MagicMock, None, None]:
    with patch(
        "application.services.subscription_service.settings",
        MagicMock(spec=[
            "razorpay_webhook_secret", "razorpay_plan_monthly", "razorpay_plan_quarterly",
            "razorpay_plan_halfyearly", "razorpay_plan_yearly", "razorpay_key_id",
        ]),
    ) as m:
        m.razorpay_webhook_secret = "test_secret"
        m.razorpay_plan_monthly = "plan_monthly_123"
        m.razorpay_plan_quarterly = "plan_quarterly_123"
        m.razorpay_plan_halfyearly = "plan_halfyearly_123"
        m.razorpay_plan_yearly = "plan_yearly_123"
        m.razorpay_key_id = "rzp_key_id"
        yield m


class TestTierForPlan:
    def test_returns_tier_for_monthly_plan(self, svc, mock_settings) -> None:
        assert svc.tier_for_plan("plan_monthly_123") == "monthly"

    def test_returns_tier_for_quarterly_plan(self, svc, mock_settings) -> None:
        assert svc.tier_for_plan("plan_quarterly_123") == "quarterly"

    def test_returns_tier_for_halfyearly_plan(self, svc, mock_settings) -> None:
        assert svc.tier_for_plan("plan_halfyearly_123") == "halfyearly"

    def test_returns_tier_for_yearly_plan(self, svc, mock_settings) -> None:
        assert svc.tier_for_plan("plan_yearly_123") == "yearly"

    def test_returns_none_for_unknown_plan(self, svc, mock_settings) -> None:
        assert svc.tier_for_plan("unknown_plan") is None


class TestTotalCountForTier:
    def test_returns_1_for_monthly(self, svc) -> None:
        assert svc.total_count_for_tier("monthly") == 1

    def test_returns_3_for_quarterly(self, svc) -> None:
        assert svc.total_count_for_tier("quarterly") == 3

    def test_returns_6_for_halfyearly(self, svc) -> None:
        assert svc.total_count_for_tier("halfyearly") == 6

    def test_returns_12_for_yearly(self, svc) -> None:
        assert svc.total_count_for_tier("yearly") == 12

    def test_returns_1_for_unknown_tier(self, svc) -> None:
        assert svc.total_count_for_tier("unknown") == 1


class TestPlanIdForTier:
    def test_returns_plan_id_for_monthly(self, svc, mock_settings) -> None:
        assert svc.plan_id_for_tier("monthly") == "plan_monthly_123"

    def test_returns_plan_id_for_yearly(self, svc, mock_settings) -> None:
        assert svc.plan_id_for_tier("yearly") == "plan_yearly_123"

    def test_raises_for_unknown_tier(self, svc) -> None:
        with pytest.raises(Exception, match="Unknown plan tier"):
            svc.plan_id_for_tier("invalid_tier")

    def test_raises_when_plan_not_configured(self, svc, mock_settings) -> None:
        with patch("application.services.subscription_service.SUBSCRIPTION_TIER_PLANS", {"monthly": "nonexistent_attr"}):
            with pytest.raises(Exception, match="Plan not configured"):
                svc.plan_id_for_tier("monthly")


class TestVerifyWebhookSignature:
    def test_returns_true_when_secret_not_set(self, svc, mock_settings) -> None:
        mock_settings.razorpay_webhook_secret = ""
        assert svc.verify_webhook_signature(b"{}", "some_sig") is True

    def test_returns_true_for_valid_signature(self, svc, mock_settings) -> None:
        import hashlib
        import hmac
        body = b'{"event": "test"}'
        expected = hmac.new(b"test_secret", body, hashlib.sha256).hexdigest()
        sig = f"sha256={expected}"
        assert svc.verify_webhook_signature(body, sig) is True

    def test_returns_false_for_invalid_signature(self, svc, mock_settings) -> None:
        assert svc.verify_webhook_signature(b"{}", "sha256=invalid") is False


@pytest.mark.asyncio
class TestIsEventProcessed:
    async def test_returns_true_when_event_exists(self, svc, mock_db) -> None:
        mock_db["async_safe_single"].return_value = {"id": 1}
        result = await svc.is_event_processed("evt_123")
        assert result is True

    async def test_returns_false_when_event_not_found(self, svc, mock_db) -> None:
        mock_db["async_safe_single"].return_value = None
        result = await svc.is_event_processed("evt_unknown")
        assert result is False


@pytest.mark.asyncio
class TestMarkEventProcessed:
    async def test_inserts_event_record(self, svc, mock_db) -> None:
        await svc.mark_event_processed("evt_123", "subscription.activated")
        mock_db["async_supabase"].assert_awaited_once()

    async def test_handles_exception_gracefully(self, svc, mock_db) -> None:
        mock_db["async_supabase"].side_effect = Exception("DB error")
        await svc.mark_event_processed("evt_123", "test")


@pytest.mark.asyncio
class TestCreateSubscription:
    async def test_creates_subscription_successfully(self, svc, mock_db, mock_settings) -> None:
        mock_db["async_safe_execute"].return_value = []
        svc.razorpay.create_subscription.return_value = {
            "id": "sub_123",
            "short_url": "https://rzp.io/abc",
        }
        result = await svc.create_subscription("user-1", "monthly")
        assert result["subscription_id"] == "sub_123"
        assert result["short_url"] == "https://rzp.io/abc"
        assert result["tier"] == "monthly"
        svc.razorpay.create_subscription.assert_awaited_once()
        mock_db["async_supabase"].assert_awaited_once()

    async def test_raises_on_existing_active_subscription(self, svc, mock_db) -> None:
        mock_db["async_safe_execute"].return_value = [{"id": "sub_1"}]
        with pytest.raises(Exception, match="Active or pending subscription already exists"):
            await svc.create_subscription("user-1", "monthly")

    async def test_raises_on_razorpay_error(self, svc, mock_db, mock_settings) -> None:
        mock_db["async_safe_execute"].return_value = []
        svc.razorpay.create_subscription.return_value = {
            "error": {"description": "Insufficient balance"}
        }
        with pytest.raises(Exception, match="Insufficient balance"):
            await svc.create_subscription("user-1", "monthly")


@pytest.mark.asyncio
class TestGetMySubscription:
    async def test_returns_subscription(self, svc, mock_db) -> None:
        mock_db["async_safe_single"].return_value = {
            "id": "sub_1",
            "tier": "monthly",
            "status": "active",
            "razorpay_subscription_id": "rzp_sub_1",
            "current_period_start": "2025-01-01T00:00:00",
            "current_period_end": "2025-02-01T00:00:00",
            "trial_end": None,
            "created_at": "2025-01-01T00:00:00",
        }
        result = await svc.get_my_subscription("user-1")
        assert result["subscription"]["id"] == "sub_1"
        assert result["subscription"]["tier"] == "monthly"

    async def test_returns_none_when_no_subscription(self, svc, mock_db) -> None:
        mock_db["async_safe_single"].return_value = None
        result = await svc.get_my_subscription("user-1")
        assert result["subscription"] is None


@pytest.mark.asyncio
class TestCancelSubscription:
    async def test_cancels_subscription(self, svc, mock_db) -> None:
        mock_db["async_safe_single"].return_value = {
            "id": "sub_1",
            "razorpay_subscription_id": "rzp_sub_1",
            "status": "active",
        }
        svc.razorpay.cancel_subscription.return_value = {"id": "rzp_sub_1"}
        result = await svc.cancel_subscription("user-1", cancel_at_cycle_end=True)
        assert result["status"] == "cancelled"
        svc.razorpay.cancel_subscription.assert_awaited_once_with("rzp_sub_1", True)

    async def test_halts_when_cancel_at_cycle_end_false(self, svc, mock_db) -> None:
        mock_db["async_safe_single"].return_value = {
            "id": "sub_1",
            "razorpay_subscription_id": "rzp_sub_1",
            "status": "active",
        }
        svc.razorpay.cancel_subscription.return_value = {"id": "rzp_sub_1"}
        result = await svc.cancel_subscription("user-1", cancel_at_cycle_end=False)
        assert result["status"] == "halted"

    async def test_raises_not_found(self, svc, mock_db) -> None:
        mock_db["async_safe_single"].return_value = None
        with pytest.raises(Exception, match="No active subscription found"):
            await svc.cancel_subscription("user-1", cancel_at_cycle_end=True)

    async def test_raises_on_razorpay_error(self, svc, mock_db) -> None:
        mock_db["async_safe_single"].return_value = {
            "id": "sub_1",
            "razorpay_subscription_id": "rzp_sub_1",
            "status": "active",
        }
        svc.razorpay.cancel_subscription.return_value = {
            "error": {"description": "Razorpay failure"}
        }
        with pytest.raises(Exception, match="Razorpay failure"):
            await svc.cancel_subscription("user-1", cancel_at_cycle_end=True)


def _build_webhook_payload(event: str, event_id: str = "evt_1", plan_id: str = "plan_monthly_123", **extra) -> bytes:
    import json
    payload = {
        "event": event,
        "id": event_id,
        "payload": {
            "subscription": {
                "entity": {
                    "id": "rzp_sub_1",
                    "plan_id": plan_id,
                    "notes": {"user_id": "user-1"},
                    "current_start": 1700000000,
                    "current_end": 1700086400,
                    **extra,
                }
            }
        }
    }
    return json.dumps(payload).encode()


@pytest.mark.asyncio
class TestHandleWebhook:
    async def test_processes_activated_event(self, svc, mock_db, mock_settings) -> None:
        mock_db["async_safe_single"].return_value = None
        body = _build_webhook_payload("subscription.activated")
        import hashlib
        import hmac
        expected = hmac.new(b"test_secret", body, hashlib.sha256).hexdigest()
        result = await svc.handle_webhook(body, f"sha256={expected}")
        assert result["status"] == "processed"
        assert result["event"] == "subscription.activated"
        assert result["tier"] == "monthly"

    async def test_processes_authenticated_event(self, svc, mock_db, mock_settings) -> None:
        mock_db["async_safe_single"].return_value = None
        body = _build_webhook_payload("subscription.authenticated")
        import hashlib
        import hmac
        expected = hmac.new(b"test_secret", body, hashlib.sha256).hexdigest()
        result = await svc.handle_webhook(body, f"sha256={expected}")
        assert result["status"] == "processed"
        assert result["event"] == "subscription.authenticated"

    async def test_processes_charged_event(self, svc, mock_db, mock_settings) -> None:
        mock_db["async_safe_single"].return_value = None
        body = _build_webhook_payload("subscription.charged", current_end=1700172800)
        import hashlib
        import hmac
        expected = hmac.new(b"test_secret", body, hashlib.sha256).hexdigest()
        result = await svc.handle_webhook(body, f"sha256={expected}")
        assert result["status"] == "processed"
        assert result["event"] == "subscription.charged"

    async def test_processes_halted_event(self, svc, mock_db, mock_settings) -> None:
        mock_db["async_safe_single"].return_value = None
        body = _build_webhook_payload("subscription.halted")
        import hashlib
        import hmac
        expected = hmac.new(b"test_secret", body, hashlib.sha256).hexdigest()
        result = await svc.handle_webhook(body, f"sha256={expected}")
        assert result["status"] == "processed"
        assert result["event"] == "subscription.halted"

    async def test_processes_cancelled_event(self, svc, mock_db, mock_settings) -> None:
        mock_db["async_safe_single"].return_value = None
        body = _build_webhook_payload("subscription.cancelled")
        import hashlib
        import hmac
        expected = hmac.new(b"test_secret", body, hashlib.sha256).hexdigest()
        result = await svc.handle_webhook(body, f"sha256={expected}")
        assert result["status"] == "processed"
        assert result["event"] == "subscription.cancelled"

    async def test_processes_completed_event(self, svc, mock_db, mock_settings) -> None:
        mock_db["async_safe_single"].return_value = None
        body = _build_webhook_payload("subscription.completed")
        import hashlib
        import hmac
        expected = hmac.new(b"test_secret", body, hashlib.sha256).hexdigest()
        result = await svc.handle_webhook(body, f"sha256={expected}")
        assert result["status"] == "processed"
        assert result["event"] == "subscription.completed"

    async def test_returns_already_processed(self, svc, mock_db, mock_settings) -> None:
        mock_db["async_safe_single"].return_value = {"id": 1}
        body = _build_webhook_payload("subscription.activated")
        import hashlib
        import hmac
        expected = hmac.new(b"test_secret", body, hashlib.sha256).hexdigest()
        result = await svc.handle_webhook(body, f"sha256={expected}")
        assert result["status"] == "already_processed"

    async def test_raises_on_bad_signature(self, svc, mock_settings) -> None:
        body = b'{"event": "test", "id": "evt_1"}'
        with pytest.raises(Exception, match="Invalid webhook signature"):
            await svc.handle_webhook(body, "sha256=bad_sig")

    async def test_raises_on_invalid_json(self, svc, mock_settings) -> None:
        body = b"not json"
        import hashlib
        import hmac
        expected = hmac.new(b"test_secret", body, hashlib.sha256).hexdigest()
        with pytest.raises(Exception, match="Invalid JSON body"):
            await svc.handle_webhook(body, f"sha256={expected}")

    async def test_raises_on_missing_event(self, svc, mock_settings) -> None:
        body = b'{"id": "evt_1"}'
        import hashlib
        import hmac
        expected = hmac.new(b"test_secret", body, hashlib.sha256).hexdigest()
        with pytest.raises(Exception, match="Missing event or id"):
            await svc.handle_webhook(body, f"sha256={expected}")

    async def test_raises_on_missing_subscription_entity(self, svc, mock_settings) -> None:
        body = b'{"event": "subscription.activated", "id": "evt_1", "payload": {"subscription": {}}}'
        import hashlib
        import hmac
        expected = hmac.new(b"test_secret", body, hashlib.sha256).hexdigest()
        with pytest.raises(Exception, match="Missing subscription entity"):
            await svc.handle_webhook(body, f"sha256={expected}")

    async def test_pending_event_marks_halted(self, svc, mock_db, mock_settings) -> None:
        mock_db["async_safe_single"].return_value = None
        body = _build_webhook_payload("subscription.pending")
        import hashlib
        import hmac
        expected = hmac.new(b"test_secret", body, hashlib.sha256).hexdigest()
        result = await svc.handle_webhook(body, f"sha256={expected}")
        assert result["status"] == "processed"
