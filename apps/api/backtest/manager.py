import asyncio
import logging
import time
import uuid
from datetime import UTC, datetime

from backtest.data_loader import backtest_data_loader
from backtest.models import (
    BacktestConfig,
    BacktestResult,
    BacktestStatus,
    ReplaySpeed,
    TradeRecord,
)
from backtest.performance import performance_analytics
from backtest.replay_engine import replay_engine
from execution.manager import ExecutionManager
from paper.models import PaperConfig
from paper.paper_broker import PaperBroker
from portfolio.manager import portfolio_manager
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
            status=BacktestStatus.RUNNING,
            config=config,
            start_equity=config.initial_capital,
            end_equity=config.initial_capital,
            started_at=datetime.now(UTC).isoformat(),
        )
        self._current_run = result
        self._bt_user_id = bt_user_id

        try:
            paper_broker = await self._setup_paper_broker(bt_user_id, config.initial_capital, exec_mgr)

            strategy = await self._setup_strategy(config)
            self._current_strategy = strategy

            candles = await backtest_data_loader.load(
                symbol=config.symbol,
                exchange=config.exchange,
                interval=config.interval,
                days=config.days,
                source=config.data_source,
                file_path=config.file_path,
            )
            if not candles:
                raise ValueError("No candle data loaded")

            replay_engine.configure(bt_user_id, config.speed)

            start_time = time.monotonic()

            await strategy.on_start()

            if config.speed == ReplaySpeed.MAX:
                for idx, raw in enumerate(candles):
                    signal = await strategy.on_candle(
                        backtest_data_loader.to_candle(raw),
                    )
                    if signal and signal.orders:
                        for order in signal.orders:
                            req = replay_engine._order_to_request(order)
                            await exec_mgr.place_order(req)

                    snapshot = await self._collect_snapshot(bt_user_id, idx)
                    snapshots.append(snapshot)

                    if idx > 0 and idx % 100 == 0:
                        await asyncio.sleep(0)
            else:
                await replay_engine.run(
                    strategy=strategy,
                    raw_candles=candles,
                    exec_mgr=exec_mgr,
                    snapshots=snapshots,
                )

            await strategy.on_stop()

            if config.close_positions_on_end and candles:
                await self._close_open_positions(bt_user_id, candles[-1], exec_mgr)
                snapshots.append(await self._collect_snapshot(bt_user_id, len(candles)))

            elapsed = time.monotonic() - start_time

            trades = performance_analytics.build_trades_from_snapshots(snapshots, config.symbol)

            result = performance_analytics.calculate(
                result=result,
                snapshots=snapshots,
                initial_capital=config.initial_capital,
                trades=trades,
                candles_analyzed=len(candles),
            )
            result.status = BacktestStatus.COMPLETED
            result.completed_at = datetime.now(UTC).isoformat()
            result.duration_seconds = round(elapsed, 2)

            self._cleanup(bt_user_id, exec_mgr)

            self._current_run = result
            return result

        except asyncio.CancelledError:
            result.status = BacktestStatus.CANCELLED
            result.completed_at = datetime.now(UTC).isoformat()
            self._cleanup(bt_user_id, exec_mgr)
            self._current_run = result
            return result

        except Exception as e:
            logger.exception("Backtest run failed: %s", e)
            result.status = BacktestStatus.FAILED
            result.error = str(e)
            result.completed_at = datetime.now(UTC).isoformat()
            self._cleanup(bt_user_id, exec_mgr)
            self._current_run = result
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

    async def _setup_paper_broker(
        self, bt_user_id: str, capital: float, exec_mgr: ExecutionManager,
    ) -> PaperBroker:
        adapter_key = f"{bt_user_id}:{BACKTEST_BROKER}"

        if adapter_key not in exec_mgr._adapters:
            broker = PaperBroker(bt_user_id)
            broker.update_config(PaperConfig(initial_capital=capital))
            await broker.connect()
            exec_mgr._adapters[adapter_key] = broker
        return exec_mgr._adapters[adapter_key]

    async def _setup_strategy(self, config: BacktestConfig):
        strategy_cls = get_strategy(config.strategy_type)
        if not strategy_cls:
            raise ValueError(f"Unknown strategy: {config.strategy_type}")
        return strategy_cls(config.strategy_params)

    async def _collect_snapshot(self, bt_user_id: str, index: int) -> dict:
        snapshot = {
            "index": index,
            "timestamp": datetime.now(UTC).isoformat(),
            "equity": 0.0,
            "positions": [],
            "pnl": {},
        }
        try:
            portfolio = await portfolio_manager.get_portfolio(bt_user_id, BACKTEST_BROKER)
            snapshot["equity"] = portfolio.pnl.current_equity if portfolio.pnl else 0.0
            snapshot["positions"] = [
                {
                    "symbol": p.symbol,
                    "quantity": p.quantity,
                    "unrealised_pnl": p.unrealised_pnl,
                    "realised_pnl": p.realised_pnl,
                    "average_buy_price": p.average_buy_price,
                    "average_sell_price": p.average_sell_price,
                    "last_price": p.last_price,
                }
                for p in portfolio.positions.values()
            ]
            if portfolio.pnl:
                snapshot["pnl"] = {
                    "realised": portfolio.pnl.realised_pnl,
                    "unrealised": portfolio.pnl.unrealised_pnl,
                    "daily": portfolio.pnl.daily_pnl,
                    "overall": portfolio.pnl.overall_pnl,
                }
        except Exception as e:
            logger.debug("Snapshot error at index %d: %s", index, e)
        return snapshot

    async def _close_open_positions(
        self, bt_user_id: str, last_candle: dict, exec_mgr: ExecutionManager,
    ):
        try:
            portfolio = await portfolio_manager.get_portfolio(bt_user_id, BACKTEST_BROKER)
            for pos in portfolio.positions.values():
                if pos.quantity == 0:
                    continue
                side = "SELL" if pos.quantity > 0 else "BUY"
                req = replay_engine._order_to_request(
                    self._make_close_order(pos.symbol, side, abs(pos.quantity)),
                )
                await exec_mgr.place_order(req)
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

    def _cleanup(self, bt_user_id: str, exec_mgr: ExecutionManager) -> None:
        adapter_key = f"{bt_user_id}:{BACKTEST_BROKER}"
        exec_mgr._adapters.pop(adapter_key, None)
        portfolio_manager.invalidate_cache(bt_user_id, BACKTEST_BROKER)
        self._current_strategy = None


backtest_manager = BacktestManager()
