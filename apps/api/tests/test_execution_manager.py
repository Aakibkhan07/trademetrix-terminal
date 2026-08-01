import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from execution.manager import ExecutionManager, ExecutionRequest
from core.models import NormalizedOrder, OrderResult
from execution.models import ExecutionState, ExecutionResult
from risk.models import RiskDecision


@pytest.fixture(autouse=True)
def reset_singleton():
    ExecutionManager._instance = None
    ExecutionManager._adapter_locks = {}
    yield


@pytest.fixture
def req():
    return ExecutionRequest(
        user_id="user-1", broker="angelone",
        symbol="NIFTY", exchange="NFO",
        side="BUY", order_type="MARKET", product="MIS",
        quantity=10, price=150.0, source="manual",
    )


@pytest.mark.asyncio
async def test_place_order_happy_path(req):
    with (
        patch.object(ExecutionManager, "_build_normalized_order") as mock_build,
        patch("execution.manager.validate_order") as mock_validate,
        patch("execution.manager.risk_manager") as mock_risk,
        patch.object(ExecutionManager, "_get_adapter") as mock_adapter,
        patch.object(ExecutionManager, "_insert_order_atomic") as mock_insert,
        patch.object(ExecutionManager, "_execute_with_retry") as mock_exec,
        patch.object(ExecutionManager, "_update_order_in_db"),
        patch("execution.manager.log_execution_event"),
        patch("execution.manager.log_validation_failure"),
    ):
        mock_build.return_value = NormalizedOrder(symbol="NIFTY", exchange="NFO", side="BUY", order_type="MARKET", product="MIS", quantity=10, price=150.0)
        mock_validate.return_value = MagicMock(valid=True)
        mock_risk.evaluate = AsyncMock(return_value=MagicMock(decision=RiskDecision.APPROVED))
        mock_adapter.return_value = AsyncMock()
        mock_insert.return_value = {"id": "order-1"}
        mock_exec.return_value = OrderResult(success=True, broker_order_id="brk-1", filled_qty=10, status="filled")

        mgr = ExecutionManager()
        result = await mgr.place_order(req)

        assert result.success is True
        assert result.state == ExecutionState.FILLED
        assert result.broker_order_id == "brk-1"


@pytest.mark.asyncio
async def test_place_order_build_failure(req):
    with (
        patch.object(ExecutionManager, "_build_normalized_order") as mock_build,
    ):
        mock_build.return_value = None

        mgr = ExecutionManager()
        result = await mgr.place_order(req)

        assert result.success is False
        assert result.error_code == "ORDER_BUILD_FAILED"


@pytest.mark.asyncio
async def test_place_order_validation_failure(req):
    with (
        patch.object(ExecutionManager, "_build_normalized_order") as mock_build,
        patch("execution.manager.validate_order") as mock_validate,
        patch("execution.manager.log_validation_failure"),
    ):
        mock_build.return_value = NormalizedOrder(symbol="NIFTY", exchange="NFO", side="BUY", order_type="MARKET", product="MIS", quantity=10, price=150.0)
        mock_validate.return_value = MagicMock(valid=False, errors=["Invalid symbol"])

        mgr = ExecutionManager()
        result = await mgr.place_order(req)

        assert result.success is False
        assert result.error_code == "VALIDATION_FAILED"


@pytest.mark.asyncio
async def test_place_order_risk_rejection(req):
    with (
        patch.object(ExecutionManager, "_build_normalized_order") as mock_build,
        patch("execution.manager.validate_order") as mock_validate,
        patch("execution.manager.risk_manager") as mock_risk,
        patch("execution.manager.log_validation_failure"),
    ):
        mock_build.return_value = NormalizedOrder(symbol="NIFTY", exchange="NFO", side="BUY", order_type="MARKET", product="MIS", quantity=10, price=150.0)
        mock_validate.return_value = MagicMock(valid=True)
        mock_risk.evaluate = AsyncMock(return_value=MagicMock(decision=RiskDecision.REJECTED, message="Daily loss cap exceeded"))

        mgr = ExecutionManager()
        result = await mgr.place_order(req)

        assert result.success is False
        assert result.error_code == "RISK_REJECTED"


@pytest.mark.asyncio
async def test_place_order_broker_unavailable(req):
    with (
        patch.object(ExecutionManager, "_build_normalized_order") as mock_build,
        patch("execution.manager.validate_order") as mock_validate,
        patch("execution.manager.risk_manager") as mock_risk,
        patch.object(ExecutionManager, "_get_adapter") as mock_adapter,
    ):
        mock_build.return_value = NormalizedOrder(symbol="NIFTY", exchange="NFO", side="BUY", order_type="MARKET", product="MIS", quantity=10, price=150.0)
        mock_validate.return_value = MagicMock(valid=True)
        mock_risk.evaluate = AsyncMock(return_value=MagicMock(decision=RiskDecision.APPROVED))
        mock_adapter.return_value = None

        mgr = ExecutionManager()
        result = await mgr.place_order(req)

        assert result.success is False
        assert result.error_code == "BROKER_UNAVAILABLE"


@pytest.mark.asyncio
async def test_place_order_duplicate_existing_found(req):
    with (
        patch.object(ExecutionManager, "_build_normalized_order") as mock_build,
        patch("execution.manager.validate_order") as mock_validate,
        patch("execution.manager.risk_manager") as mock_risk,
        patch.object(ExecutionManager, "_get_adapter") as mock_adapter,
        patch.object(ExecutionManager, "_insert_order_atomic") as mock_insert,
        patch.object(ExecutionManager, "_check_existing_order") as mock_check,
    ):
        mock_build.return_value = NormalizedOrder(symbol="NIFTY", exchange="NFO", side="BUY", order_type="MARKET", product="MIS", quantity=10, price=150.0)
        mock_validate.return_value = MagicMock(valid=True)
        mock_risk.evaluate = AsyncMock(return_value=MagicMock(decision=RiskDecision.APPROVED))
        mock_adapter.return_value = AsyncMock()
        mock_insert.return_value = None
        mock_check.return_value = {"broker_order_id": "brk-1", "status": "FILLED"}

        mgr = ExecutionManager()
        result = await mgr.place_order(req)

        assert result.success is True
        assert result.broker_order_id == "brk-1"
        assert result.message == "DUPLICATE_REQUEST"


@pytest.mark.asyncio
async def test_place_order_insert_failed_no_existing(req):
    with (
        patch.object(ExecutionManager, "_build_normalized_order") as mock_build,
        patch("execution.manager.validate_order") as mock_validate,
        patch("execution.manager.risk_manager") as mock_risk,
        patch.object(ExecutionManager, "_get_adapter") as mock_adapter,
        patch.object(ExecutionManager, "_insert_order_atomic") as mock_insert,
        patch.object(ExecutionManager, "_check_existing_order") as mock_check,
    ):
        mock_build.return_value = NormalizedOrder(symbol="NIFTY", exchange="NFO", side="BUY", order_type="MARKET", product="MIS", quantity=10, price=150.0)
        mock_validate.return_value = MagicMock(valid=True)
        mock_risk.evaluate = AsyncMock(return_value=MagicMock(decision=RiskDecision.APPROVED))
        mock_adapter.return_value = AsyncMock()
        mock_insert.return_value = None
        mock_check.return_value = None

        mgr = ExecutionManager()
        result = await mgr.place_order(req)

        assert result.success is False
        assert result.error_code == "INSERT_FAILED"


@pytest.mark.asyncio
async def test_place_order_partial_fill(req):
    with (
        patch.object(ExecutionManager, "_build_normalized_order") as mock_build,
        patch("execution.manager.validate_order") as mock_validate,
        patch("execution.manager.risk_manager") as mock_risk,
        patch.object(ExecutionManager, "_get_adapter") as mock_adapter,
        patch.object(ExecutionManager, "_insert_order_atomic") as mock_insert,
        patch.object(ExecutionManager, "_execute_with_retry") as mock_exec,
        patch.object(ExecutionManager, "_update_order_in_db"),
        patch("execution.manager.log_execution_event"),
        patch("execution.manager.log_validation_failure"),
    ):
        mock_build.return_value = NormalizedOrder(symbol="NIFTY", exchange="NFO", side="BUY", order_type="MARKET", product="MIS", quantity=10, price=150.0)
        mock_validate.return_value = MagicMock(valid=True)
        mock_risk.evaluate = AsyncMock(return_value=MagicMock(decision=RiskDecision.APPROVED))
        mock_adapter.return_value = AsyncMock()
        mock_insert.return_value = {"id": "order-1"}
        mock_exec.return_value = OrderResult(success=True, broker_order_id="brk-1", filled_qty=5, status="PARTIALLY_FILLED")

        mgr = ExecutionManager()
        result = await mgr.place_order(req)

        assert result.success is True
        assert result.state == ExecutionState.PARTIALLY_FILLED


@pytest.mark.asyncio
async def test_place_order_broker_rejection(req):
    with (
        patch.object(ExecutionManager, "_build_normalized_order") as mock_build,
        patch("execution.manager.validate_order") as mock_validate,
        patch("execution.manager.risk_manager") as mock_risk,
        patch.object(ExecutionManager, "_get_adapter") as mock_adapter,
        patch.object(ExecutionManager, "_insert_order_atomic") as mock_insert,
        patch.object(ExecutionManager, "_execute_with_retry") as mock_exec,
        patch("execution.manager.log_execution_event"),
        patch("execution.manager.log_validation_failure"),
    ):
        mock_build.return_value = NormalizedOrder(symbol="NIFTY", exchange="NFO", side="BUY", order_type="MARKET", product="MIS", quantity=10, price=150.0)
        mock_validate.return_value = MagicMock(valid=True)
        mock_risk.evaluate = AsyncMock(return_value=MagicMock(decision=RiskDecision.APPROVED))
        mock_adapter.return_value = AsyncMock()
        mock_insert.return_value = {"id": "order-1"}
        mock_exec.return_value = OrderResult(success=False, message="Insufficient margin")

        mgr = ExecutionManager()
        result = await mgr.place_order(req)

        assert result.success is False
        assert result.error_code == "ORDER_REJECTED"


@pytest.mark.asyncio
async def test_place_order_exception_handling(req):
    with (
        patch.object(ExecutionManager, "_build_normalized_order") as mock_build,
        patch("execution.manager.validate_order") as mock_validate,
        patch("execution.manager.risk_manager") as mock_risk,
        patch.object(ExecutionManager, "_get_adapter") as mock_adapter,
        patch.object(ExecutionManager, "_insert_order_atomic") as mock_insert,
        patch.object(ExecutionManager, "_execute_with_retry") as mock_exec,
        patch("execution.manager.log_execution_event"),
    ):
        mock_build.return_value = NormalizedOrder(symbol="NIFTY", exchange="NFO", side="BUY", order_type="MARKET", product="MIS", quantity=10, price=150.0)
        mock_validate.return_value = MagicMock(valid=True)
        mock_risk.evaluate = AsyncMock(return_value=MagicMock(decision=RiskDecision.APPROVED))
        mock_adapter.return_value = AsyncMock()
        mock_insert.return_value = {"id": "order-1"}
        mock_exec.side_effect = RuntimeError("Connection lost")

        mgr = ExecutionManager()
        result = await mgr.place_order(req)

        assert result.success is False
        assert result.error_code == "EXECUTION_FAILED"
