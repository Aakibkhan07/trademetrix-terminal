from typing import Generator
from unittest.mock import MagicMock, patch

import pytest

from application.services.admin_service import AdminService


@pytest.fixture
def svc() -> AdminService:
    return AdminService()


@pytest.fixture
def mock_db() -> Generator[dict, None, None]:
    with (
        patch("application.services.admin_service.get_supabase") as mock_get,
        patch("application.services.admin_service.async_supabase") as mock_async,
        patch("application.services.admin_service.async_safe_single") as mock_single,
        patch("application.services.admin_service.async_safe_execute") as mock_execute,
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


@pytest.mark.asyncio
class TestListUsers:
    @patch("application.services.admin_service.resolve_capabilities_by_id")
    async def test_returns_user_list(self, mock_caps, svc, mock_db) -> None:
        mock_db["async_safe_execute"].side_effect = [
            [{"id": "u1", "email": "a@b.com", "full_name": "User A", "is_admin": False, "role": "", "subscription_tier": "free", "created_at": "2025-01-01"}],
            [],
        ]
        mock_caps.return_value = MagicMock(max_active_strategies=1)
        result = await svc.list_users()
        assert len(result["users"]) == 1
        assert result["users"][0]["email"] == "a@b.com"


@pytest.mark.asyncio
class TestListAssignments:
    async def test_returns_assignments(self, svc, mock_db) -> None:
        mock_db["async_safe_execute"].return_value = [{"id": "a1", "user_id": "u1", "strategy_key": "trend_rider"}]
        result = await svc.list_assignments()
        assert len(result["assignments"]) == 1

    async def test_filters_by_user_id(self, svc, mock_db) -> None:
        mock_db["async_safe_execute"].return_value = [{"id": "a1"}]
        result = await svc.list_assignments(user_id="u1")
        assert len(result["assignments"]) == 1

    async def test_returns_empty(self, svc, mock_db) -> None:
        mock_db["async_safe_execute"].return_value = None
        result = await svc.list_assignments()
        assert result["assignments"] == []


@pytest.mark.asyncio
class TestAssignStrategy:
    @patch("application.services.admin_service.list_strategies", return_value=["trend_rider", "smc_sniper"])
    @patch("application.services.admin_service.get_strategy_tier", return_value="free")
    @patch("application.services.admin_service.resolve_capabilities_by_id")
    @patch("application.services.admin_service.record_audit")
    async def test_assigns_strategy(self, mock_audit, mock_caps, mock_tier, mock_list, svc, mock_db) -> None:
        mock_db["async_safe_single"].side_effect = [
            {"id": "u1", "subscription_tier": "free"},
            None,  # no active existing
            None,  # no inactive existing
        ]
        mock_db["async_safe_execute"].return_value = []
        mock_caps.return_value = MagicMock(tier="free", max_active_strategies=5)
        result = await svc.assign_strategy("u1", "trend_rider", "admin-1")
        assert result["message"] == "Strategy assigned"
        assert result["user_id"] == "u1"

    @patch("application.services.admin_service.list_strategies", return_value=["trend_rider"])
    async def test_raises_on_unknown_key(self, mock_list, svc) -> None:
        with pytest.raises(Exception, match="Unknown strategy_key"):
            await svc.assign_strategy("u1", "nonexistent", "admin-1")

    @patch("application.services.admin_service.list_strategies", return_value=["trend_rider"])
    async def test_raises_on_user_not_found(self, mock_list, svc, mock_db) -> None:
        mock_db["async_safe_single"].return_value = None
        with pytest.raises(Exception, match="User not found"):
            await svc.assign_strategy("u1", "trend_rider", "admin-1")

    @patch("application.services.admin_service.list_strategies", return_value=["smc_sniper"])
    @patch("application.services.admin_service.get_strategy_tier", return_value="enterprise")
    @patch("application.services.admin_service.resolve_capabilities_by_id")
    async def test_raises_on_tier_too_low(self, mock_caps, mock_tier, mock_list, svc, mock_db) -> None:
        mock_db["async_safe_single"].return_value = {"id": "u1", "subscription_tier": "free"}
        mock_caps.return_value = MagicMock(tier="free", max_active_strategies=1)
        with pytest.raises(Exception, match="below required"):
            await svc.assign_strategy("u1", "smc_sniper", "admin-1")

    @patch("application.services.admin_service.list_strategies", return_value=["trend_rider"])
    @patch("application.services.admin_service.get_strategy_tier", return_value="free")
    @patch("application.services.admin_service.resolve_capabilities_by_id")
    @patch("application.services.admin_service.record_audit")
    async def test_returns_noop_for_existing_active(self, mock_audit, mock_caps, mock_tier, mock_list, svc, mock_db) -> None:
        mock_db["async_safe_single"].return_value = {"id": "a1", "active": True}
        mock_caps.return_value = MagicMock(tier="free", max_active_strategies=5)
        result = await svc.assign_strategy("u1", "trend_rider", "admin-1")
        assert "no-op" in result["message"]

    @patch("application.services.admin_service.list_strategies", return_value=["trend_rider"])
    @patch("application.services.admin_service.get_strategy_tier", return_value="free")
    @patch("application.services.admin_service.resolve_capabilities_by_id")
    @patch("application.services.admin_service.record_audit")
    async def test_reassigns_inactive(self, mock_audit, mock_caps, mock_tier, mock_list, svc, mock_db) -> None:
        mock_db["async_safe_single"].side_effect = [
            {"id": "u1", "subscription_tier": "free"},
            None,  # no active existing
            {"id": "a1", "active": False},
        ]
        mock_db["async_safe_execute"].return_value = []
        mock_caps.return_value = MagicMock(tier="free", max_active_strategies=5)
        result = await svc.assign_strategy("u1", "trend_rider", "admin-1")
        assert "Reassigned" in result["message"]

    @patch("application.services.admin_service.list_strategies", return_value=["trend_rider"])
    @patch("application.services.admin_service.get_strategy_tier", return_value="free")
    @patch("application.services.admin_service.resolve_capabilities_by_id")
    async def test_raises_on_limit_exceeded(self, mock_caps, mock_tier, mock_list, svc, mock_db) -> None:
        mock_db["async_safe_single"].return_value = {"id": "u1", "subscription_tier": "free"}
        mock_db["async_safe_execute"].return_value = [{"id": "a1"}]
        mock_caps.return_value = MagicMock(tier="free", max_active_strategies=1)
        with pytest.raises(Exception, match="allows 1 active strategies"):
            await svc.assign_strategy("u1", "trend_rider", "admin-1")


@pytest.mark.asyncio
class TestUnassignStrategy:
    @patch("application.services.admin_service.record_audit")
    async def test_unassigns_strategy(self, mock_audit, svc, mock_db) -> None:
        mock_db["async_safe_single"].return_value = {"id": "a1", "user_id": "u1", "strategy_key": "trend_rider"}
        result = await svc.unassign_strategy("a1", "admin-1")
        assert result["message"] == "Strategy unassigned (deactivated)"

    async def test_raises_not_found(self, svc, mock_db) -> None:
        mock_db["async_safe_single"].return_value = None
        with pytest.raises(Exception, match="Assignment not found"):
            await svc.unassign_strategy("a1", "admin-1")


@pytest.mark.asyncio
class TestUpdateUserTier:
    @patch("application.services.admin_service.record_audit")
    async def test_updates_tier(self, mock_audit, svc, mock_db) -> None:
        mock_db["async_safe_single"].return_value = {
            "id": "u1", "email": "a@b.com", "full_name": "A", "is_admin": False,
            "subscription_tier": "free", "created_at": "2025-01-01",
        }
        result = await svc.update_user_tier("u1", "pro", "admin-1")
        assert result["subscription_tier"] == "pro"

    async def test_raises_on_invalid_tier(self, svc) -> None:
        with pytest.raises(Exception, match="Invalid tier"):
            await svc.update_user_tier("u1", "mega", "admin-1")

    async def test_raises_on_user_not_found(self, svc, mock_db) -> None:
        mock_db["async_safe_single"].return_value = None
        with pytest.raises(Exception, match="User not found"):
            await svc.update_user_tier("nonexistent", "pro", "admin-1")

    @patch("application.services.admin_service.record_audit")
    async def test_downgrade_deactivates_stale(self, mock_audit, svc, mock_db) -> None:
        mock_db["async_safe_single"].return_value = {
            "id": "u1", "email": "a@b.com", "full_name": "A", "is_admin": False,
            "subscription_tier": "enterprise", "created_at": "2025-01-01",
        }
        mock_db["async_safe_execute"].return_value = [
            {"id": "a1", "strategy_key": "smc_sniper", "required_tier": "enterprise"},
        ]
        with patch("application.services.admin_service.TIER_ORDER", {"free": 0, "starter": 1, "pro": 2, "enterprise": 3}):
            with patch("application.services.admin_service.CAP_MAP", {}):
                with patch("application.services.admin_service.FREE") as mock_free:
                    mock_free.max_active_strategies = 1
                    result = await svc.update_user_tier("u1", "free", "admin-1")
        assert result["subscription_tier"] == "free"

    @patch("application.services.admin_service.record_audit")
    async def test_noop_when_same_tier(self, mock_audit, svc, mock_db) -> None:
        mock_db["async_safe_single"].return_value = {
            "id": "u1", "email": "a@b.com", "full_name": "A",
            "subscription_tier": "pro",
        }
        result = await svc.update_user_tier("u1", "pro", "admin-1")
        assert "No change" in result["message"]


@pytest.mark.asyncio
class TestListBrokers:
    async def test_returns_broker_list(self, svc, mock_db) -> None:
        mock_db["async_safe_execute"].side_effect = [
            [{"id": "c1", "user_id": "u1", "broker": "fyers", "is_active": True, "encrypted_access_token": "tok", "created_at": "", "updated_at": ""}],
            [{"id": "u1", "email": "a@b.com", "full_name": "A", "is_admin": False}],
        ]
        result = await svc.list_brokers()
        assert len(result["brokers"]) == 1

    async def test_returns_empty(self, svc, mock_db) -> None:
        mock_db["async_safe_execute"].return_value = None
        result = await svc.list_brokers()
        assert result["brokers"] == []


@pytest.mark.asyncio
class TestListOrders:
    async def test_returns_orders(self, svc, mock_db) -> None:
        mock_db["async_safe_execute"].side_effect = [
            [{"id": "o1", "user_id": "u1", "symbol": "NIFTY", "side": "BUY", "quantity": 50, "price": 18500.0, "is_paper": True, "status": "filled", "broker": "fyers", "broker_order_id": "b1", "exchange": "NFO", "order_type": "MARKET", "product": "MIS", "message": "", "filled_quantity": 50, "filled_at": "", "created_at": ""}],
            [{"id": "u1", "email": "a@b.com", "full_name": "A"}],
        ]
        result = await svc.list_orders()
        assert result["count"] == 1

    async def test_returns_empty(self, svc, mock_db) -> None:
        mock_db["async_safe_execute"].return_value = None
        result = await svc.list_orders()
        assert result["orders"] == []

    async def test_filters_by_user_id(self, svc, mock_db) -> None:
        mock_db["async_safe_execute"].return_value = []
        result = await svc.list_orders(user_id="u1")
        assert result["count"] == 0


@pytest.mark.asyncio
class TestGetAuditLog:
    async def test_returns_audit_entries(self, svc, mock_db) -> None:
        mock_db["async_safe_execute"].return_value = [{"id": 1, "action": "assign_strategy", "user_id": "u1"}]
        result = await svc.get_audit_log()
        assert result["count"] == 1

    async def test_returns_empty(self, svc, mock_db) -> None:
        mock_db["async_safe_execute"].return_value = None
        result = await svc.get_audit_log()
        assert result["entries"] == []


@pytest.mark.asyncio
class TestGetStats:
    @patch("application.services.admin_service.resolve_capabilities_by_id")
    @patch("application.services.admin_service.get_strategy_catalog", return_value=["s1", "s2"])
    async def test_returns_stats(self, mock_cat, mock_caps, svc, mock_db) -> None:
        mock_db["async_safe_execute"].side_effect = [
            [{"id": "u1", "is_admin": True, "subscription_tier": "pro", "created_at": ""},
             {"id": "u2", "is_admin": False, "subscription_tier": "free", "created_at": ""}],
            [{"id": "a1"}],
        ]
        mock_caps.return_value = MagicMock(tier="pro")
        result = await svc.get_stats()
        assert result["total_users"] == 2
        assert result["total_admins"] == 1
        assert result["total_strategies"] == 2
        assert result["active_assignments"] == 1


@pytest.mark.asyncio
class TestCreateAdmin:
    @patch("application.services.admin_service.record_audit")
    async def test_creates_admin(self, mock_audit, svc, mock_db) -> None:
        mock_db["async_safe_single"].return_value = {"id": "u1", "email": "a@b.com", "is_admin": False, "role": ""}
        result = await svc.create_admin("a@b.com", "admin", "admin-1")
        assert "promoted" in result["message"]

    async def test_raises_on_invalid_role(self, svc) -> None:
        with pytest.raises(Exception, match="Invalid role"):
            await svc.create_admin("a@b.com", "ceo", "admin-1")

    async def test_raises_on_user_not_found(self, svc, mock_db) -> None:
        mock_db["async_safe_single"].return_value = None
        with pytest.raises(Exception, match="User not found"):
            await svc.create_admin("nonexistent@b.com", "admin", "admin-1")


@pytest.mark.asyncio
class TestUpdateAdminRole:
    @patch("application.services.admin_service.record_audit")
    async def test_updates_role(self, mock_audit, svc, mock_db) -> None:
        mock_db["async_safe_single"].return_value = {"id": "u2", "is_admin": True, "role": "admin"}
        result = await svc.update_admin_role("u2", "support", "admin-1")
        assert "support" in result["message"]

    async def test_raises_on_invalid_role(self, svc) -> None:
        with pytest.raises(Exception, match="Invalid role"):
            await svc.update_admin_role("u2", "ceo", "admin-1")

    async def test_raises_on_self_change(self, svc) -> None:
        with pytest.raises(Exception, match="cannot change your own"):
            await svc.update_admin_role("admin-1", "support", "admin-1")


@pytest.mark.asyncio
class TestRemoveAdmin:
    @patch("application.services.admin_service.record_audit")
    async def test_removes_admin(self, mock_audit, svc, mock_db) -> None:
        mock_db["async_safe_single"].return_value = {"id": "u2", "role": "admin"}
        result = await svc.remove_admin("u2", "admin-1")
        assert result["message"] == "Admin access removed"

    async def test_raises_on_self_remove(self, svc) -> None:
        with pytest.raises(Exception, match="cannot remove yourself"):
            await svc.remove_admin("admin-1", "admin-1")

    async def test_raises_on_user_not_found(self, svc, mock_db) -> None:
        mock_db["async_safe_single"].return_value = None
        with pytest.raises(Exception, match="Admin user not found"):
            await svc.remove_admin("nonexistent", "admin-1")
