import asyncio
import logging
import time
import uuid
from datetime import UTC, datetime

from backtest.data_loader import backtest_data_loader
from backtest.execution import BacktestBroker, BacktestExecutionConfig
from backtest.models import (
    BacktestConfig,
    BacktestResult,
    BacktestStatus,
    EquityPoint,
    ReplaySpeed,
    TradeRecord,
)
from backtest.performance import performance_analytics
from backtest.replay_engine import replay_engine
from execution.manager import ExecutionManager
from execution.models import ExecutionRequest
from risk.manager import risk_manager
from risk.models import RiskDecision
from strategies import get_strategy

logger = logging.getLogger(__name__)

BACKTEST_BROKER = "paper"


class BacktestManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._current_run: BacktestResult | None = None
        self._current_strategy = None
        self._bt_user_id = ""
        self._history: list[BacktestResult] = []

    @property
    def current_run(self) -> BacktestResult | None:
        return self._current_run

    async def run(self, config: BacktestConfig) -> BacktestResult:
        run_id = uuid.uuid4().hex[:12]
        bt_user_id = f"backtest:{run_id}"
        exec_mgr = ExecutionManager()
        snapshots: list[dict] = []

        result = BacktestResult(
            run_id=run_id,
            user_id=config.user_id,
            status=BacktestStatus.RUNNING,
            config=config,
            start_equity=config.initial_capital,
            end_equity=config.initial_capital,
            started_at=datetime.now(UTC).isoformat(),
        )
        self._current_run = result
        self._bt_user_id = bt_user_id

        try:
            broker = await self._setup_backtest_broker(bt_user_id, config, exec_mgr)

            strategy = await self._setup_strategy(config)
            self._current_strategy = strategy

            candles = await backtest_data_loader.load(
                symbol=config.symbol,
                exchange=config.exchange,
                interval=config.interval,
                days=config.days,
                source=config.data_source,
                file_path=config.file_path,
                user_id=config.user_id,
            )
            if not candles:
                raise ValueError("No candle data loaded")

            broker.set_candles(candles)
            replay_engine.configure(bt_user_id, config.speed)

            start_time = time.monotonic()

            await strategy.on_start()

            if config.speed == ReplaySpeed.MAX:
                for idx, raw in enumerate(candles):
                    await broker.on_candle(idx)
                    signal = await strategy.on_candle(
                        backtest_data_loader.to_candle(raw),
                    )
                    if signal and signal.orders:
                        for order in signal.orders:
                            await self._place_via_broker(broker, order, config, bt_user_id)

                    snapshot = await self._collect_snapshot(broker, idx)
                    snapshots.append(snapshot)

                    if idx > 0 and idx % 100 == 0:
                        await asyncio.sleep(0)
            else:
                await replay_engine.run(
                    strategy=strategy,
                    raw_candles=candles,
                    exec_mgr=exec_mgr,
                    snapshots=snapshots,
                    broker=broker,
                    risk_check=config.risk_enabled,
                    bt_user_id=bt_user_id,
                )

            await strategy.on_stop()

            if config.close_positions_on_end and candles:
                await self._close_open_positions(broker, candles[-1])
                snapshots.append(await self._collect_snapshot(broker, len(candles)))

            elapsed = time.monotonic() - start_time

            trades = performance_analytics.build_trades_from_snapshots(snapshots, config.symbol)

            result = performance_analytics.calculate(
                result=result,
                snapshots=snapshots,
                initial_capital=config.initial_capital,
                trades=trades,
                candles_analyzed=len(candles),
                benchmark_candles=candles,
            )
            result.status = BacktestStatus.COMPLETED
            result.completed_at = datetime.now(UTC).isoformat()
            result.duration_seconds = round(elapsed, 2)

            self._cleanup(bt_user_id, exec_mgr)

            self._current_run = result
            self._history.append(result)
            await self._persist_run(result)
            return result

        except asyncio.CancelledError:
            result.status = BacktestStatus.CANCELLED
            result.completed_at = datetime.now(UTC).isoformat()
            self._cleanup(bt_user_id, exec_mgr)
            self._current_run = result
            self._history.append(result)
            return result

        except Exception as e:
            logger.exception("Backtest run failed: %s", e)
            result.status = BacktestStatus.FAILED
            result.error = str(e)
            result.completed_at = datetime.now(UTC).isoformat()
            self._cleanup(bt_user_id, exec_mgr)
            self._current_run = result
            self._history.append(result)
            return result

    async def pause(self) -> bool:
        if not replay_engine.is_running:
            return False
        await replay_engine.pause()
        if self._current_run:
            self._current_run.status = BacktestStatus.PAUSED
        return True

    async def resume(self) -> bool:
        if not replay_engine.is_paused:
            return False
        await replay_engine.resume()
        if self._current_run:
            self._current_run.status = BacktestStatus.RUNNING
        return True

    async def stop(self) -> bool:
        await replay_engine.stop()
        if self._current_strategy:
            try:
                await self._current_strategy.on_stop()
            except Exception as e:
                logger.warning("Backtest strategy on_stop failed: %s", e)
        if self._current_run:
            self._current_run.status = BacktestStatus.CANCELLED
            self._current_run.completed_at = datetime.now(UTC).isoformat()
        return True

    def list_runs(self, strategy_id: str | None = None) -> list[dict]:
        runs = self._history[:]
        if strategy_id:
            runs = [r for r in runs if r.config and r.config.strategy_type == strategy_id]
        return [
            {
                "run_id": r.run_id,
                "strategy_type": r.config.strategy_type if r.config else "",
                "symbol": r.config.symbol if r.config else "",
                "status": r.status.value,
                "total_trades": r.total_trades,
                "net_pnl": r.net_pnl,
                "win_rate": r.win_rate,
                "return_pct": r.return_pct,
                "sharpe_ratio": r.sharpe_ratio,
                "started_at": r.started_at,
                "completed_at": r.completed_at,
                "duration_seconds": r.duration_seconds,
            }
            for r in reversed(runs)
        ]

    async def get_run(self, run_id: str) -> BacktestResult | None:
        for r in self._history:
            if r.run_id == run_id:
                return r
        try:
            from core.db import async_supabase, get_supabase

            supabase = get_supabase()
            result = await async_supabase(
                lambda: supabase.table("backtest_runs")
                .select("*").eq("id", run_id).limit(1).execute(),
            )
            rows = result.data or []
            if not rows:
                return None
            return self._row_to_result(rows[0])
        except Exception as e:
            logger.debug("Backtest run read skipped: %s", e)
            return None

    async def _persist_run(self, result: BacktestResult) -> None:
        try:
            from core.db import async_supabase, get_supabase

            supabase = get_supabase()
            row = {
                "id": result.run_id,
                "user_id": result.user_id or (result.config.user_id if result.config else ""),
                "strategy_type": result.config.strategy_type if result.config else "",
                "strategy_id": result.config.strategy_id if result.config else "",
                "symbol": result.config.symbol if result.config else "",
                "interval": result.config.interval if result.config else "",
                "days": result.config.days if result.config else 0,
                "config": result.config.model_dump(mode="json") if result.config else {},
                "summary": result.model_dump(
                    mode="json", exclude={"trades", "equity_curve", "config"},
                ),
                "trades": [t.model_dump(mode="json") for t in result.trades],
                "equity_curve": [e.model_dump(mode="json") for e in result.equity_curve],
            }
            await async_supabase(
                lambda: supabase.table("backtest_runs")
                .upsert(row, on_conflict="id").execute(),
            )
        except Exception as e:
            logger.warning("Backtest run persist skipped: %s", e)

    def _row_to_result(self, row: dict) -> BacktestResult:
        result = BacktestResult(**row.get("summary", {}))
        config = row.get("config") or {}
        if config:
            try:
                result.config = BacktestConfig(**config)
            except Exception as e:
                logger.debug("Run config restore failed: %s", e)
        for t in row.get("trades", []):
            try:
                result.trades.append(TradeRecord(**t))
            except Exception as e:
                logger.debug("Run trade restore failed: %s", e)
        for p in row.get("equity_curve", []):
            try:
                result.equity_curve.append(EquityPoint(**p))
            except Exception as e:
                logger.debug("Run equity restore failed: %s", e)
        return result

    def get_status(self) -> dict:
        if not self._current_run:
            return {"status": BacktestStatus.IDLE.value}

        return {
            "run_id": self._current_run.run_id,
            "status": self._current_run.status.value,
            "progress_pct": replay_engine.progress_pct,
            "current_candle": replay_engine.current_index,
            "total_candles": replay_engine._total_candles,
            "total_trades": self._current_run.total_trades,
            "started_at": self._current_run.started_at,
            "speed": self._current_run.config.speed.value if self._current_run.config else ReplaySpeed.MAX.value,
        }

    async def _setup_backtest_broker(
        self, bt_user_id: str, config: BacktestConfig, exec_mgr: ExecutionManager,
    ) -> BacktestBroker:
        adapter_key = f"{bt_user_id}:{BACKTEST_BROKER}"

        if adapter_key not in exec_mgr._adapters:
            broker = BacktestBroker(bt_user_id)
            broker.update_config(self._broker_config(config))
            await broker.connect()
            exec_mgr._adapters[adapter_key] = broker
        return exec_mgr._adapters[adapter_key]

    def _broker_config(self, config: BacktestConfig) -> BacktestExecutionConfig:
        return BacktestExecutionConfig(
            initial_capital=config.initial_capital,
            slippage_pct=config.slippage_pct,
            latency_candles=config.latency_candles,
            partial_fill_probability=config.partial_fill_probability,
            seed=config.seed,
            cost_config=config.cost,
        )

    async def _place_via_broker(
        self, broker: BacktestBroker, order, config: BacktestConfig, bt_user_id: str,
    ):
        """Place an order through the backtest broker with optional risk dry-run."""
        if config.risk_enabled:
            try:
                req = self._order_to_request(order, bt_user_id)
                risk_result = await risk_manager.evaluate(req, dry_run=True)
                if risk_result.decision == RiskDecision.REJECTED:
                    return None
            except Exception as e:
                logger.debug("Backtest risk check skipped: %s", e)
        return await broker.place_order(order)

    def _order_to_request(self, order, bt_user_id: str) -> ExecutionRequest:
        return ExecutionRequest(
            user_id=bt_user_id,
            broker="paper",
            symbol=order.symbol,
            exchange=order.exchange.value if hasattr(order.exchange, "value") else "NSE",
            side=order.side.value if hasattr(order.side, "value") else "BUY",
            order_type=order.order_type.value if hasattr(order.order_type, "value") else "MARKET",
            product=order.product.value if hasattr(order.product, "value") else "INTRADAY",
            quantity=order.quantity,
            price=order.price,
            trigger_price=order.trigger_price,
            strategy_id=order.strategy_id,
            source="backtest",
            is_paper=True,
        )

    async def _setup_strategy(self, config: BacktestConfig):
        strategy_cls = get_strategy(config.strategy_type)
        if not strategy_cls:
            raise ValueError(f"Unknown strategy: {config.strategy_type}")
        return strategy_cls(config.strategy_params)

    async def _collect_snapshot(self, broker: BacktestBroker, index: int) -> dict:
        snapshot = {
            "index": index,
            "timestamp": datetime.now(UTC).isoformat(),
            "equity": broker.equity(),
            "positions": [],
            "pnl": {},
        }
        try:
            positions = await broker.get_positions()
            snapshot["positions"] = [
                {
                    "symbol": p["symbol"],
                    "quantity": p["quantity"],
                    "unrealised_pnl": p["unrealised_pnl"],
                    "realised_pnl": p["realised_pnl"],
                    "average_buy_price": p["average_buy_price"],
                    "average_sell_price": p["average_sell_price"],
                    "last_price": p["last_price"],
                }
                for p in positions
            ]
            snapshot["pnl"] = {
                "realised": broker.realized_pnl,
                "unrealised": broker.equity() - broker.cash,
                "daily": broker.realized_pnl,
                "overall": broker.realized_pnl + broker.equity() - broker.cash,
            }
        except Exception as e:
            logger.debug("Snapshot error at index %d: %s", index, e)
        return snapshot

    async def _close_open_positions(
        self, broker: BacktestBroker, last_candle: dict,
    ):
        try:
            positions = broker.positions()
            for symbol, pos in positions.items():
                qty = pos.get("quantity", 0)
                if qty == 0:
                    continue
                side = "SELL" if qty > 0 else "BUY"
                order = self._make_close_order(symbol, side, abs(qty))
                order.instrument_type = last_candle.get("instrument_type", order.instrument_type)
                await broker.place_order(order)
        except Exception as e:
            logger.debug("Close positions error: %s", e)

    def _make_close_order(self, symbol: str, side: str, quantity: int):
        from core.models import NormalizedOrder, OrderSide, OrderType, ProductType, Exchange

        return NormalizedOrder(
            symbol=symbol,
            exchange=Exchange.NSE,
            side=OrderSide(side),
            order_type=OrderType.MARKET,
            product=ProductType.INTRADAY,
            quantity=quantity,
        )

    async def _fast_run(self, config: BacktestConfig) -> BacktestResult:
        """Lean execution path for the optimizer: broker-direct, no replay/
        pause machinery, snapshot list kept for equity/drawdown only."""
        run_id = uuid.uuid4().hex[:12]
        bt_user_id = f"backtest:{run_id}"
        exec_mgr = ExecutionManager()
        snapshots: list[dict] = []

        result = BacktestResult(
            run_id=run_id,
            status=BacktestStatus.RUNNING,
            config=config,
            start_equity=config.initial_capital,
            end_equity=config.initial_capital,
            started_at=datetime.now(UTC).isoformat(),
        )

        try:
            broker = await self._setup_backtest_broker(bt_user_id, config, exec_mgr)
            strategy = await self._setup_strategy(config)

            candles = await backtest_data_loader.load(
                symbol=config.symbol,
                exchange=config.exchange,
                interval=config.interval,
                days=config.days,
                source=config.data_source,
                file_path=config.file_path,
                user_id=config.user_id,
            )
            if not candles:
                raise ValueError("No candle data loaded")
            if config.candle_slice:
                candles = candles[config.candle_slice[0]:config.candle_slice[1]]

            broker.set_candles(candles)
            await strategy.on_start()

            for idx, raw in enumerate(candles):
                await broker.on_candle(idx)
                signal = await strategy.on_candle(backtest_data_loader.to_candle(raw))
                if signal and signal.orders:
                    for order in signal.orders:
                        await self._place_via_broker(broker, order, config, bt_user_id)
                snapshots.append(await self._collect_snapshot(broker, idx))

            await strategy.on_stop()

            if config.close_positions_on_end and candles:
                await self._close_open_positions(broker, candles[-1])
                snapshots.append(await self._collect_snapshot(broker, len(candles)))

            trades = [
                TradeRecord(**t) for t in broker.trades
            ]
            result = performance_analytics.calculate(
                result=result,
                snapshots=snapshots,
                initial_capital=config.initial_capital,
                trades=trades,
                candles_analyzed=len(candles),
                benchmark_candles=candles,
            )
            result.status = BacktestStatus.COMPLETED
            result.completed_at = datetime.now(UTC).isoformat()
            result.duration_seconds = 0.0

            self._cleanup(bt_user_id, exec_mgr)
            await self._persist_run(result)
            return result

        except Exception as e:
            logger.exception("Fast backtest failed: %s", e)
            result.status = BacktestStatus.FAILED
            result.error = str(e)
            result.completed_at = datetime.now(UTC).isoformat()
            self._cleanup(bt_user_id, exec_mgr)
            return result

    def _cleanup(self, bt_user_id: str, exec_mgr: ExecutionManager) -> None:
        adapter_key = f"{bt_user_id}:{BACKTEST_BROKER}"
        exec_mgr._adapters.pop(adapter_key, None)
        self._current_strategy = None


backtest_manager = BacktestManager()
