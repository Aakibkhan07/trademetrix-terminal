"""Tests for fail-closed behavior in risk and validation modules."""
import pytest
from unittest.mock import patch

from execution.validation import _validate_trading_session, _check_margin
from risk.rules import MarketClosedRule, TradingWindowRule
from risk.manager import RiskManager, RiskConfig
from risk.kill_switch import KillSwitch
from execution.models import ExecutionRequest
from core.models import NormalizedOrder, OrderSide, OrderType, ProductType, Exchange
from risk.models import RiskDecision


@pytest.mark.asyncio
async def test_validate_trading_session_fail_closed():
    with patch("execution.validation.market_status_service.is_market_open", side_effect=Exception("Service down")):
        result = await _validate_trading_session()
        assert result is False


@pytest.mark.asyncio
async def test_check_margin_fail_closed():
    order = NormalizedOrder(
        symbol="RELIANCE",
        exchange=Exchange.NSE,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        product=ProductType.INTRADAY,
        quantity=10,
        broker="zerodha",
    )
    with patch("execution.validation.get_supabase", side_effect=Exception("DB down")):
        result = await _check_margin("user123", order)
        assert result is False


@pytest.mark.asyncio
async def test_market_closed_rule_fail_closed():
    rule = MarketClosedRule()
    req = ExecutionRequest(
        user_id="user123", broker="zerodha", symbol="RELIANCE",
        side="BUY", quantity=10,
    )
    config = RiskConfig(user_id="user123")
    with patch("risk.rules.market_status_service.is_market_open", side_effect=Exception("Service down")):
        result = await rule.evaluate(req, config)
        assert result.decision == RiskDecision.REJECTED
        assert "fail-closed" in result.reason


@pytest.mark.asyncio
async def test_trading_window_rule_fail_closed():
    rule = TradingWindowRule()
    req = ExecutionRequest(
        user_id="user123", broker="zerodha", symbol="RELIANCE",
        side="BUY", quantity=10,
    )
    config = RiskConfig(user_id="user123", trading_start="abc", trading_end="xyz")
    result = await rule.evaluate(req, config)
    assert result.decision == RiskDecision.REJECTED
    assert "fail-closed" in result.reason


@pytest.mark.asyncio
async def test_load_config_fail_closed():
    mgr = RiskManager()
    with patch("risk.manager.async_safe_single", side_effect=Exception("DB error")):
        config = await mgr._load_config("user123")
        assert config.kill_switch_enabled is True
        assert config.max_open_positions == 0
        assert config.max_trades_per_day == 0
        assert config.daily_loss_limit == 0
        assert config.allow_warning is False


@pytest.mark.asyncio
async def test_kill_switch_recover():
    ks = KillSwitch()
    mock_rows = [
        {"user_id": "user1", "event": "EMERGENCY_STOP", "created_at": "2025-01-01T00:00:00"},
    ]
    with (
        patch.object(ks, "_emergency_stops", {}),
        patch("risk.kill_switch.safe_execute", return_value=mock_rows),
        patch("risk.kill_switch.safe_single", return_value=None),
    ):
        await ks.recover()
        assert ks._emergency_stops.get("user1") is True


@pytest.mark.asyncio
async def test_kill_switch_recover_with_release():
    ks = KillSwitch()
    mock_rows = [
        {"user_id": "user1", "event": "EMERGENCY_STOP", "created_at": "2025-01-01T00:00:00"},
    ]
    with (
        patch.object(ks, "_emergency_stops", {}),
        patch("risk.kill_switch.safe_execute", return_value=mock_rows),
        patch("risk.kill_switch.safe_single", return_value={"id": "123"}),
    ):
        await ks.recover()
        assert ks._emergency_stops.get("user1") is None


@pytest.mark.asyncio
async def test_kill_switch_recover_handles_error():
    ks = KillSwitch()
    with patch("risk.kill_switch.safe_execute", side_effect=Exception("DB error")):
        await ks.recover()
        assert not ks._emergency_stops
