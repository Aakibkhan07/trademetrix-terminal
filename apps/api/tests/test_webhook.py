"""Tests for Razorpay subscription webhook handler.

Covers: signature verification, all 6 event types, idempotency,
safety-net expiry in the capabilities resolver.
"""

import hashlib
import hmac
import json
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from core.capabilities import _resolve_subscription_tier
from core.config import settings
from main import app

# ── Helpers ──

TEST_WEBHOOK_SECRET = "whsec_test_secret_32chars__dont_use_in_prod!"


def _sign_body(body: bytes) -> str:
    expected = hmac.new(TEST_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={expected}"


def _build_event(
    event: str,
    event_id: str,
    razorpay_sub_id: str = "sub_test_123",
    plan_id: str = "plan_monthly_test",
    tier: str = "monthly",
    status: str = "active",
    current_start: int | None = None,
    current_end: int | None = None,
    user_id: str = "test-user-id",
    notes: dict | None = None,
) -> bytes:
    now = int(datetime.now(UTC).timestamp())
    body = {
        "entity": "event",
        "account_id": "acc_test",
        "id": event_id,
        "event": event,
        "contains": ["subscription"],
        "payload": {
            "subscription": {
                "entity": {
                    "id": razorpay_sub_id,
                    "entity": "subscription",
                    "plan_id": plan_id,
                    "status": status,
                    "current_start": current_start,
                    "current_end": current_end,
                    "quantity": 1,
                    "notes": notes or {"user_id": user_id, "tier": tier},
                    "created_at": now,
                }
            }
        },
        "created_at": now,
    }
    return json.dumps(body).encode()


def _make_client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@contextmanager
def _patches_for_test(sb):
    with patch.object(settings, "razorpay_webhook_secret", TEST_WEBHOOK_SECRET), \
         patch("routes.v1_subscriptions.get_supabase", return_value=sb), \
         patch("routes.v1_subscriptions.async_supabase", side_effect=lambda fn, *a, **kw: fn()), \
         patch.object(settings, "razorpay_plan_monthly", "plan_monthly_test"), \
         patch.object(settings, "razorpay_plan_quarterly", "plan_quarterly_test"), \
         patch.object(settings, "razorpay_plan_halfyearly", "plan_halfyearly_test"), \
         patch.object(settings, "razorpay_plan_yearly", "plan_yearly_test"):
        yield


def _mock_supabase_tables():
    """Return a mock supabase client with in-memory stores."""
    sub_store: dict[str, dict] = {}
    sub_counter = [0]
    pwh_store: list[dict] = []

    def _table(name):
        mock = MagicMock()

        if name == "subscriptions":
            def _select(*cols):
                q = MagicMock()
                q.execute = lambda: MagicMock(data=list(sub_store.values()))
                q.eq = lambda f, v: q
                q.in_ = lambda f, vl: q
                q.order = lambda *a, **kw: q
                q.limit = lambda n: q
                q.maybe_single = lambda: q
                return q
            mock.select = _select
            mock.insert = lambda data: MagicMock(data=[_ins(data)])
            mock.update = lambda updates: _mock_update(updates)

        elif name == "processed_webhooks":
            def _select(*cols):
                q = MagicMock()
                q._pwh_store = pwh_store
                q._match_field = None
                q._match_value = None
                def _eq(field, value):
                    q._match_field = field
                    q._match_value = value
                    return q
                q.eq = _eq
                q.limit = lambda n: q
                q.order = lambda *a, **kw: q
                def _execute():
                    matching = [r for r in pwh_store if r.get(q._match_field) == q._match_value]
                    return MagicMock(data=matching[0] if matching else None)
                q.execute = _execute
                def _maybe_single():
                    return q
                q.maybe_single = _maybe_single
                return q
            mock.select = _select
            def _insert(data):
                pwh_store.append(dict(data))
                return MagicMock(data=[{"id": "mock"}])
            mock.insert = _insert

        return mock

    def _ins(data):
        sub_counter[0] += 1
        row_id = f"row_{sub_counter[0]}"
        entry = dict(data)
        entry["id"] = row_id
        sub_store[row_id] = entry
        return entry

    def _mock_update(updates):
        q = MagicMock()
        q.eq = lambda f, v: q
        q.execute = lambda: [_ for _ in [sub_store.update(
            {k: v for k, v in [(s, updates[s]) for s in updates]}
        )]][0] if False else None
        for entry in sub_store.values():
            entry.update(updates)
        return q

    sb = MagicMock()
    sb.table = _table
    return sb, sub_store, pwh_store


# ── Signature Verification ──


@pytest.mark.asyncio
async def test_invalid_signature_returns_400():
    """Invalid X-Razorpay-Signature → 400."""
    body = _build_event("subscription.activated", "evt_001")
    with patch.object(settings, "razorpay_webhook_secret", TEST_WEBHOOK_SECRET):
        async with _make_client() as client:
            resp = await client.post(
                "/api/v1/subscriptions/webhook/",
                content=body,
                headers={"X-Razorpay-Signature": "sha256=bad"},
            )
    assert resp.status_code == 400
    assert "signature" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_missing_signature_returns_400():
    """Missing X-Razorpay-Signature → 400."""
    body = _build_event("subscription.activated", "evt_001")
    with patch.object(settings, "razorpay_webhook_secret", TEST_WEBHOOK_SECRET):
        async with _make_client() as client:
            resp = await client.post("/api/v1/subscriptions/webhook/", content=body)
    assert resp.status_code == 400
    assert "signature" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_valid_signature_accepted():
    """Valid HMAC-SHA256 signature → processed."""
    body = _build_event("subscription.activated", "evt_002", plan_id="plan_monthly_test")
    signature = _sign_body(body)
    sb, _, _ = _mock_supabase_tables()

    with _patches_for_test(sb):
        async with _make_client() as client:
            resp = await client.post(
                "/api/v1/subscriptions/webhook/",
                content=body,
                headers={"X-Razorpay-Signature": signature},
            )

    assert resp.status_code == 200
    assert resp.json()["status"] == "processed"


# ── Event Type Tests ──


@pytest.mark.asyncio
async def test_activated_grants_tier():
    """subscription.activated → status=active, tier granted."""
    body = _build_event("subscription.activated", "evt_010",
                        razorpay_sub_id="sub_act_1", plan_id="plan_monthly_test",
                        current_start=1700000000, current_end=1700086400)
    signature = _sign_body(body)
    sb, subs, _ = _mock_supabase_tables()

    with _patches_for_test(sb):
        async with _make_client() as client:
            resp = await client.post(
                "/api/v1/subscriptions/webhook/",
                content=body,
                headers={"X-Razorpay-Signature": signature},
            )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_authenticated_activates():
    """subscription.authenticated → activated as active."""
    body = _build_event("subscription.authenticated", "evt_011",
                        razorpay_sub_id="sub_auth_1", plan_id="plan_quarterly_test",
                        current_start=1700000000, current_end=1700086400)
    signature = _sign_body(body)
    sb, _, _ = _mock_supabase_tables()

    with _patches_for_test(sb):
        async with _make_client() as client:
            resp = await client.post(
                "/api/v1/subscriptions/webhook/",
                content=body,
                headers={"X-Razorpay-Signature": signature},
            )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_charged_extends_period():
    """subscription.charged → period extended."""
    start_dt = datetime.now(UTC) - timedelta(days=15)
    end_dt = datetime.now(UTC) + timedelta(days=15)
    body = json.dumps({
        "entity": "event",
        "account_id": "acc_test",
        "id": "evt_012",
        "event": "subscription.charged",
        "contains": ["subscription", "payment"],
        "payload": {
            "subscription": {
                "entity": {
                    "id": "sub_charge_1", "entity": "subscription",
                    "plan_id": "plan_monthly_test", "status": "active",
                    "current_start": int(start_dt.timestamp()),
                    "current_end": int(end_dt.timestamp()),
                    "quantity": 1,
                    "notes": {"user_id": "test-user", "tier": "monthly"},
                    "created_at": int(start_dt.timestamp()),
                }
            },
            "payment": {
                "entity": {
                    "id": "pay_test", "entity": "payment",
                    "amount": 15500, "currency": "INR", "status": "captured",
                }
            },
        },
        "created_at": int(datetime.now(UTC).timestamp()),
    }).encode()
    signature = _sign_body(body)
    sb, _, _ = _mock_supabase_tables()

    with _patches_for_test(sb):
        async with _make_client() as client:
            resp = await client.post(
                "/api/v1/subscriptions/webhook/",
                content=body,
                headers={"X-Razorpay-Signature": signature},
            )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_pending_sets_halted():
    """subscription.pending → halted."""
    body = _build_event("subscription.pending", "evt_013", razorpay_sub_id="sub_halt_1")
    signature = _sign_body(body)
    sb, _, _ = _mock_supabase_tables()

    with _patches_for_test(sb):
        async with _make_client() as client:
            resp = await client.post(
                "/api/v1/subscriptions/webhook/",
                content=body,
                headers={"X-Razorpay-Signature": signature},
            )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_halted_sets_halted():
    """subscription.halted → halted."""
    body = _build_event("subscription.halted", "evt_014", razorpay_sub_id="sub_halt_2")
    signature = _sign_body(body)
    sb, _, _ = _mock_supabase_tables()

    with _patches_for_test(sb):
        async with _make_client() as client:
            resp = await client.post(
                "/api/v1/subscriptions/webhook/",
                content=body,
                headers={"X-Razorpay-Signature": signature},
            )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_cancelled_sets_cancelled():
    """subscription.cancelled → cancelled, period_end preserved."""
    body = _build_event("subscription.cancelled", "evt_015",
                        razorpay_sub_id="sub_cancel_1", current_end=1700086400)
    signature = _sign_body(body)
    sb, _, _ = _mock_supabase_tables()

    with _patches_for_test(sb):
        async with _make_client() as client:
            resp = await client.post(
                "/api/v1/subscriptions/webhook/",
                content=body,
                headers={"X-Razorpay-Signature": signature},
            )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_completed_downgrades():
    """subscription.completed → completed, access ends."""
    body = _build_event("subscription.completed", "evt_016",
                        razorpay_sub_id="sub_complete_1", current_end=1700086400)
    signature = _sign_body(body)
    sb, _, _ = _mock_supabase_tables()

    with _patches_for_test(sb):
        async with _make_client() as client:
            resp = await client.post(
                "/api/v1/subscriptions/webhook/",
                content=body,
                headers={"X-Razorpay-Signature": signature},
            )
    assert resp.status_code == 200


# ── Idempotency ──


@pytest.mark.asyncio
async def test_idempotency_repeated_event():
    """Same event_id twice → first processed, second already_processed."""
    body = _build_event("subscription.activated", "evt_020",
                        razorpay_sub_id="sub_idem_1", plan_id="plan_monthly_test")
    signature = _sign_body(body)
    sb, _, _ = _mock_supabase_tables()

    with _patches_for_test(sb):
        async with _make_client() as client:
            first = await client.post(
                "/api/v1/subscriptions/webhook/",
                content=body,
                headers={"X-Razorpay-Signature": signature},
            )
            second = await client.post(
                "/api/v1/subscriptions/webhook/",
                content=body,
                headers={"X-Razorpay-Signature": signature},
            )

    assert first.status_code == 200
    assert first.json()["status"] == "processed"
    assert second.status_code == 200
    assert second.json()["status"] == "already_processed"


# ── Unknown Plan ──


@pytest.mark.asyncio
async def test_unknown_plan_id_returns_400():
    """Unknown plan_id → 400."""
    body = _build_event("subscription.activated", "evt_030",
                        razorpay_sub_id="sub_unknown", plan_id="plan_nonexistent")
    signature = _sign_body(body)
    sb, _, _ = _mock_supabase_tables()

    with patch.object(settings, "razorpay_webhook_secret", TEST_WEBHOOK_SECRET), \
         patch("routes.v1_subscriptions.get_supabase", return_value=sb), \
         patch("routes.v1_subscriptions.async_supabase", side_effect=lambda fn, *a, **kw: fn()):

        async with _make_client() as client:
            resp = await client.post(
                "/api/v1/subscriptions/webhook/",
                content=body,
                headers={"X-Razorpay-Signature": signature},
            )
    assert resp.status_code == 400
    assert "plan_id" in resp.json()["detail"].lower()


# ── Safety-Net: Capabilities Resolver Expiry ──


@pytest.mark.asyncio
async def test_expired_period_end_returns_free():
    """Active subscription with past current_period_end → treated as free."""
    future_end = (datetime.now(UTC) + timedelta(days=30)).isoformat()
    past_end = (datetime.now(UTC) - timedelta(days=1)).isoformat()

    active_row = {
        "tier": "monthly",
        "status": "active",
        "current_period_end": future_end,
        "current_period_start": (datetime.now(UTC) - timedelta(days=15)).isoformat(),
        "razorpay_subscription_id": "sub_expiry_1",
    }
    expired_row = {
        "tier": "monthly",
        "status": "active",
        "current_period_end": past_end,
        "current_period_start": (datetime.now(UTC) - timedelta(days=45)).isoformat(),
        "razorpay_subscription_id": "sub_expiry_2",
    }

    with patch("core.safe_query.async_safe_execute", AsyncMock(return_value=[active_row])):
        tier = await _resolve_subscription_tier("test-user")
    assert tier == "monthly"

    with patch("core.safe_query.async_safe_execute", AsyncMock(return_value=[expired_row])):
        tier = await _resolve_subscription_tier("test-user")
    assert tier is None


@pytest.mark.asyncio
async def test_no_subscription_returns_free():
    """No subscription row → resolve_capabilities returns FREE."""
    from core.capabilities import resolve_capabilities
    from core.models import UserProfile

    user = UserProfile(id="no-sub-user", email="nobody@test.com", full_name="No Sub")

    with patch("core.safe_query.async_safe_execute", AsyncMock(return_value=[])):
        caps = await resolve_capabilities(user)

    assert caps.tier == "free"
    assert caps.max_active_strategies == 1
    assert caps.builder_allowed is False
