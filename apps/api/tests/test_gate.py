import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from core.models import NormalizedOrder, OrderResult


BASE_ORDER = dict(
    broker="angelone",
    symbol="NIFTY",
    side="BUY",
    quantity=10,
    price=150.0,
    exchange="NFO",
    product="MIS",
    order_type="MARKET",
)


@pytest.mark.asyncio
async def test_idempotency_duplicate_order():
    with (
        patch("engine.gate.async_safe_single") as mock_single,
        patch("engine.gate.get_supabase") as mock_sb,
    ):
        mock_single.return_value = {"id": "existing_order", "broker_order_id": "brk_001"}
        from engine.gate import execute_order
        result = await execute_order(
            user_id="test-user",
            order=NormalizedOrder(**BASE_ORDER, client_order_id="dup_001", source="manual", reason="test duplicate"),
        )
        assert result.status == "duplicate"
        assert result.message == "DUPLICATE_ORDER"


@pytest.mark.asyncio
async def test_kill_switch_rejects():
    with (
        patch("engine.gate.async_safe_single") as mock_single,
        patch("engine.gate.async_supabase") as mock_sb,
    ):
        mock_single.return_value = None
        mock_risk = MagicMock()
        mock_risk.check_order = AsyncMock(return_value={"allowed": False, "reason": "Kill switch is active"})
        mock_risk._load_settings = AsyncMock()
        with patch("engine.gate.RiskGuard", return_value=mock_risk):
            from engine.gate import execute_order
            result = await execute_order(
                user_id="test-user",
                order=NormalizedOrder(**BASE_ORDER, client_order_id="test_002", source="manual", reason="test kill switch"),
            )
            assert result.status == "rejected"
            assert result.message == "KILL_SWITCH"


@pytest.mark.asyncio
async def test_daily_loss_cap_rejects():
    with (
        patch("engine.gate.async_safe_single") as mock_single,
        patch("engine.gate.async_supabase") as mock_sb,
    ):
        mock_single.return_value = None
        mock_risk = MagicMock()
        mock_risk.check_order = AsyncMock(return_value={"allowed": False, "reason": "Daily loss limit exceeded"})
        mock_risk._load_settings = AsyncMock()
        with patch("engine.gate.RiskGuard", return_value=mock_risk):
            from engine.gate import execute_order
            result = await execute_order(
                user_id="test-user",
                order=NormalizedOrder(**BASE_ORDER, client_order_id="test_003", source="manual", reason="test loss cap"),
            )
            assert result.status == "rejected"
            assert result.message == "DAILY_LOSS_CAP"


@pytest.mark.asyncio
async def test_paper_mode_routes_to_paper():
    with (
        patch("engine.gate.async_safe_single") as mock_single,
        patch("engine.gate.async_supabase") as mock_sb,
        patch("execution.execution_manager") as mock_exec_mgr,
    ):
        mock_single.side_effect = [None, {"broker": "angelone"}]
        mock_risk = MagicMock()
        mock_risk.check_order = AsyncMock(return_value={"allowed": True})
        mock_risk._load_settings = AsyncMock(return_value=MagicMock(is_live=False))
        mock_exec_mgr.place_order = AsyncMock(return_value=MagicMock(success=True, broker_order_id="paper_abc123", message="Paper order placed", latency_ms=0.0, state=MagicMock(value="FILLED")))
        with patch("engine.gate.RiskGuard", return_value=mock_risk):
            from engine.gate import execute_order
            result = await execute_order(
                user_id="test-user",
                order=NormalizedOrder(**BASE_ORDER, client_order_id="test_005", source="manual", reason="test paper"),
            )
            assert result.status == "FILLED"
            assert "paper" in result.message.lower()
            assert result.broker_order_id.startswith("paper_")


@pytest.mark.asyncio
async def test_live_route_no_active_broker():
    with (
        patch("engine.gate.async_safe_single") as mock_single,
        patch("engine.gate.async_supabase") as mock_sb,
    ):
        mock_single.return_value = None
        mock_risk = MagicMock()
        mock_risk.check_order = AsyncMock(return_value={"allowed": True})
        mock_risk._load_settings = AsyncMock(return_value=MagicMock(is_live=True))
        with patch("engine.gate.RiskGuard", return_value=mock_risk):
            from engine.gate import execute_order
            result = await execute_order(
                user_id="test-user",
                order=NormalizedOrder(**BASE_ORDER, client_order_id="test_006", source="manual", reason="test live no broker"),
            )
            assert result.status == "rejected"
            assert "no active broker" in result.message.lower()


@pytest.mark.asyncio
async def test_mirror_client_order_id_deterministic():
    from engine.gate import generate_client_order_id
    cid1 = generate_client_order_id("u1", "NIFTY", "BUY", source="mirror", signal_id="sig_abc")
    cid2 = generate_client_order_id("u1", "NIFTY", "BUY", source="mirror", signal_id="sig_abc")
    cid3 = generate_client_order_id("u1", "NIFTY", "BUY", source="mirror", signal_id="sig_xyz")
    assert cid1 == cid2
    assert cid1 != cid3
    assert len(cid1) == 32


@pytest.mark.asyncio
async def test_manual_client_order_id_changes_with_timestamp():
    from engine.gate import generate_client_order_id
    cid1 = generate_client_order_id("u1", "NIFTY", "BUY", source="manual")
    time.sleep(1.1)
    cid2 = generate_client_order_id("u1", "NIFTY", "BUY", source="manual")
    assert cid1 != cid2
    assert len(cid1) == 32
