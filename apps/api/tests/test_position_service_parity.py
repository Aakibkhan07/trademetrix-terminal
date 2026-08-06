"""W2 parity suite: every positions consumer reuses the canonical PositionService.

Covers the four data-source paths and proves the historical response envelopes
are preserved byte-for-byte:
- Engine  : get_user_positions / get_user_positions_list  -> {"positions": [...]}
- Portfolio: get_positions_with_broker                    -> {"positions": [...], "broker": ...}
- Paper   : get_paper_positions                           -> {"positions": [...], "count": n} (open only)
- Admin   : list_all_positions                            -> {"positions": [...], "count": n} (snapshot + profiles)

Also asserts EngineService.get_positions == PositionService resolution (the W2
delegation contract).
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from application.services.admin_service import AdminService
from application.services.engine_service import EngineService
from application.services.position_service import position_service


@pytest.fixture
def paper_engine():
    from execution_engine import pnl_engine, portfolio_engine, position_manager, trade_manager
    from execution_engine.events import ExecutionDomain, LoggingSink, execution_bus
    from execution_engine.init import reset_execution_engine
    from execution_engine.metrics import execution_metrics

    reset_execution_engine()
    execution_bus.reset_subscribers()
    execution_bus.subscribe(ExecutionDomain.ORDER, LoggingSink())
    execution_bus.clear()
    trade_manager.ledger.clear()
    for mgr in (position_manager, pnl_engine, portfolio_engine):
        mgr.clear()
    for mgr in (trade_manager, position_manager, pnl_engine, portfolio_engine, execution_metrics):
        mgr._installed = False
    from execution_engine.events import _ENGINE_BRIDGE_WIRED, _LEGACY_BRIDGE_WIRED
    _LEGACY_BRIDGE_WIRED = False
    _ENGINE_BRIDGE_WIRED = False
    yield
    execution_bus.clear()


# ── Paper consumer ────────────────────────────────────────────────────────
class TestPaperConsumer:
    @pytest.mark.asyncio
    async def test_paper_positions_open_only_envelope(self, paper_engine) -> None:
        from execution_engine.init import init_execution_engine
        from execution.event_bus import execution_event_bus
        from execution.models import ExecutionEvent

        user = "w2-paper-user"
        init_execution_engine()

        def payload(req_id, qty, price, fill_qty):
            return {
                "order_id": req_id, "quantity": qty, "price": price,
                "fill": {"order_id": req_id, "filled_quantity": fill_qty, "filled_price": price},
                "is_paper": True, "strategy_id": "w2", "source": "smoke",
            }

        async def pub(etype, req_id, side, qty, price, fill_qty):
            await execution_event_bus.publish(ExecutionEvent(
                event_type=etype, execution_request_id=req_id, user_id=user,
                broker="paper", symbol="NIFTY", side=side, message="w2 parity inject",
                payload=payload(req_id, qty, price, fill_qty),
            ))

        import asyncio

        await pub("PaperOrderPartiallyFilled", "p-part", "SELL", 2, 110.0, 2)
        await pub("PaperOrderFilled", "p-buy", "BUY", 10, 100.0, 10)
        await pub("PaperOrderFilled", "p-sell", "SELL", 8, 110.0, 8)
        await asyncio.sleep(0.2)

        body = position_service.get_paper_positions(user)

        assert set(body.keys()) == {"positions", "count"}
        assert body["count"] == len(body["positions"]) == 0  # flat net -> no open positions

        from execution_engine import position_manager

        raw = position_manager.get_positions(user, broker="paper")
        assert len(raw) == 1
        assert body["count"] == len([p for p in raw if p.is_open])

    def test_paper_positions_envelope_is_route_shaped(self) -> None:
        assert position_service.get_paper_positions("w2-nobody") == {"positions": [], "count": 0}


# ── Engine consumer ───────────────────────────────────────────────────────
class TestEngineConsumer:
    @pytest.mark.asyncio
    async def test_engine_service_delegates_to_position_service(self) -> None:
        """EngineService.get_positions must equal PositionService resolution."""
        expected = [{"symbol": "NIFTY", "quantity": 5}]

        with (
            patch("application.services.position_service.async_safe_single", return_value=None),
            patch("application.services.position_service.get_active_broker", return_value="fyers"),
            patch("application.services.engine_service.EngineService.get_engine_for",
                  AsyncMock(return_value=MagicMock(get_positions=AsyncMock(return_value=[
                      MagicMock(model_dump=MagicMock(return_value=p)) for p in expected
                  ])))),
        ):
            got = await EngineService().get_positions("w2-user")

        assert got == expected

    @pytest.mark.asyncio
    async def test_get_user_positions_envelope(self) -> None:
        with (
            patch("application.services.position_service.async_safe_single", return_value=None),
            patch("application.services.position_service.get_active_broker", return_value="fyers"),
            patch("application.services.engine_service.EngineService.get_engine_for",
                  AsyncMock(return_value=MagicMock(get_positions=AsyncMock(return_value=[
                      MagicMock(model_dump=MagicMock(return_value={"symbol": "NIFTY"}))
                  ])))),
        ):
            body = await position_service.get_user_positions("w2-user")

        assert body == {"positions": [{"symbol": "NIFTY"}]}

    @pytest.mark.asyncio
    async def test_paper_run_branch_uses_portfolio_manager(self) -> None:
        fake_pos = MagicMock()
        fake_pos.model_dump.return_value = {"symbol": "NIFTY", "quantity": 3}

        with (
            patch("application.services.position_service.async_safe_single",
                  return_value={"mode": "PAPER", "broker": "paper"}),
            patch("portfolio.manager.portfolio_manager.refresh", AsyncMock()),
            patch("portfolio.manager.portfolio_manager.get_positions", AsyncMock(return_value=[fake_pos])),
        ):
            body = await position_service.get_user_positions("w2-user")

        assert body == {"positions": [{"symbol": "NIFTY", "quantity": 3}]}

    @pytest.mark.asyncio
    async def test_paper_run_branch_fails_open_to_empty(self) -> None:
        with (
            patch("application.services.position_service.async_safe_single",
                  return_value={"mode": "PAPER", "broker": "paper"}),
            patch("portfolio.manager.portfolio_manager.refresh", AsyncMock(side_effect=RuntimeError("db down"))),
        ):
            body = await position_service.get_user_positions("w2-user")

        assert body == {"positions": []}


# ── Portfolio consumer ────────────────────────────────────────────────────
class TestPortfolioConsumer:
    @pytest.mark.asyncio
    async def test_with_explicit_broker_envelope(self) -> None:
        fake_pos = MagicMock()
        fake_pos.model_dump.return_value = {"symbol": "NIFTY", "quantity": 4}

        with (
            patch("portfolio.manager.portfolio_manager.refresh", AsyncMock()),
            patch("portfolio.manager.portfolio_manager.get_positions", AsyncMock(return_value=[fake_pos])),
        ):
            body = await position_service.get_positions_with_broker("w2-user", broker="fyers")

        assert body == {"positions": [{"symbol": "NIFTY", "quantity": 4}], "broker": "fyers"}

    @pytest.mark.asyncio
    async def test_resolves_active_broker_when_omitted(self) -> None:
        with (
            patch("application.services.position_service.get_active_broker", return_value="fyers"),
            patch("portfolio.manager.portfolio_manager.refresh", AsyncMock()),
            patch("portfolio.manager.portfolio_manager.get_positions", AsyncMock(return_value=[])),
        ):
            body = await position_service.get_positions_with_broker("w2-user")

        assert body == {"positions": [], "broker": "fyers"}

    @pytest.mark.asyncio
    async def test_no_broker_envelope(self) -> None:
        with patch("application.services.position_service.get_active_broker", return_value=None):
            body = await position_service.get_positions_with_broker("w2-user")

        assert body == {"positions": [], "broker": None}


# ── Admin consumer ────────────────────────────────────────────────────────
class TestAdminConsumer:
    def _fake_table(self):
        table = MagicMock()
        table.select.return_value.order.return_value = table
        table.eq.return_value = table
        table.in_.return_value = table
        return table

    @pytest.mark.asyncio
    async def test_list_all_positions_envelope_and_profiles(self) -> None:
        snapshots = [
            {"id": "p1", "user_id": "u1", "symbol": "NIFTY", "exchange": "NSE", "quantity": 5,
             "buy_quantity": 5, "sell_quantity": 0, "average_buy_price": 100.0,
             "average_sell_price": 0.0, "unrealised_pnl": 50.0, "realised_pnl": 0.0,
             "m2m": 50.0, "product": "NRML", "instrument_type": "OPT", "strike_price": 24450,
             "expiry_date": "2026-08-06", "option_type": "CE", "snapshot_at": "2026-08-06T10:00:00Z"},
            {"id": "p1", "user_id": "u1", "symbol": "NIFTY", "exchange": "NSE", "quantity": 5,
             "buy_quantity": 5, "sell_quantity": 0, "average_buy_price": 90.0,
             "average_sell_price": 0.0, "unrealised_pnl": 60.0, "realised_pnl": 0.0,
             "m2m": 60.0, "product": "NRML", "instrument_type": "OPT", "strike_price": 24450,
             "expiry_date": "2026-08-06", "option_type": "CE", "snapshot_at": "2026-08-06T11:00:00Z"},
        ]

        with (
            patch("application.services.position_service.get_supabase") as mock_get,
            patch("application.services.position_service.async_safe_execute") as mock_exec,
        ):
            table = self._fake_table()
            mock_get.return_value.table.return_value = table
            mock_exec.side_effect = [
                snapshots,
                [{"id": "u1", "email": "a@b.com", "full_name": "User A"}],
            ]

            body = await position_service.list_all_positions()

        assert set(body.keys()) == {"positions", "count"}
        assert body["count"] == 1
        assert body["positions"][0]["email"] == "a@b.com"
        assert body["positions"][0]["full_name"] == "User A"
        assert body["positions"][0]["strike_price"] == 24450
        assert body["positions"][0]["option_type"] == "CE"
        assert body["positions"][0]["quantity"] == 5

    @pytest.mark.asyncio
    async def test_admin_service_delegates_to_position_service(self) -> None:
        with (
            patch("application.services.position_service.get_supabase") as mock_get,
            patch("application.services.position_service.async_safe_execute", return_value=[]),
        ):
            table = self._fake_table()
            mock_get.return_value.table.return_value = table
            body = await AdminService().list_positions(user_id="u1")

        assert body == {"positions": [], "count": 0}
